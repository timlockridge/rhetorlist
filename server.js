const express = require('express');
const fs = require('fs').promises;
const path = require('path');
const { exec, spawn } = require('child_process');
const multer = require('multer');
const imageProcessor = require('./lib/image-processor');

const app = express();
const PORT = 4000;

const FEED_PATH = path.join(__dirname, 'public', 'feed.json');

function getPublicationYear(publicationDate) {
    return publicationDate.split('-')[2];
}

function isCurrentYear(publicationDate) {
    const currentYear = String(new Date().getFullYear());
    return getPublicationYear(publicationDate) === currentYear;
}

function buildFeedItem(book) {
    const link = book.publisherURL;
    return {
        id: link,
        content_html: `<h1>New Book Added:</h1><p>${book.title} by ${book.author}. Published on ${book.publicationDate}.</p><p>Link to book: <a href="${link}">${link}</a></p>`,
        url: link
    };
}

async function addBookToFeedIfCurrentYear(book) {
    if (!isCurrentYear(book.publicationDate)) {
        return;
    }

    const feedContent = await fs.readFile(FEED_PATH, 'utf8');
    const feed = JSON.parse(feedContent);
    const items = Array.isArray(feed.items) ? feed.items : [];

    if (items.some((item) => item.id === book.publisherURL || item.url === book.publisherURL)) {
        return;
    }

    items.unshift(buildFeedItem(book));
    feed.items = items;

    await fs.writeFile(FEED_PATH, JSON.stringify(feed, null, 2), 'utf8');
}

// Configure multer for file uploads
const upload = multer({
    dest: '/tmp/uploads/',
    limits: { fileSize: 10 * 1024 * 1024 }, // 10MB limit
    fileFilter: (req, file, cb) => {
        const allowed = /jpeg|jpg|png|webp|avif/i;
        const ext = path.extname(file.originalname).toLowerCase();
        if (allowed.test(ext.substring(1))) {
            cb(null, true);
        } else {
            cb(new Error('Invalid file type. Only JPG, PNG, WebP, and AVIF are allowed.'));
        }
    }
});

// Middleware
app.use(express.json());

// Serve static files from public folder (production files)
app.use(express.static(path.join(__dirname, 'public')));

// Also serve book-manager.html from root
app.get('/book-manager.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'book-manager.html'));
});

// API endpoint to save book descriptions
app.post('/api/save', async (req, res) => {
    try {
        const { yearFile, bookIndex, description } = req.body;

        // Validate input
        if (!yearFile || bookIndex === undefined || !Array.isArray(description)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid request data'
            });
        }

        // Construct file path - JSON files are in public folder
        const filePath = path.join(__dirname, 'public', yearFile);

        // Read current JSON file
        const fileContent = await fs.readFile(filePath, 'utf8');
        const books = JSON.parse(fileContent);

        // Validate book index
        if (bookIndex < 0 || bookIndex >= books.length) {
            return res.status(400).json({
                success: false,
                error: 'Invalid book index'
            });
        }

        // Update book with description
        const updatedBook = { ...books[bookIndex] };

        // Filter out empty paragraphs
        const nonEmptyParagraphs = description.filter(p => p && p.trim() !== '');

        if (nonEmptyParagraphs.length > 0) {
            updatedBook.description = nonEmptyParagraphs;
        } else {
            // Remove description field if empty
            delete updatedBook.description;
        }

        // Update books array
        books[bookIndex] = updatedBook;

        // Write back to file with pretty formatting
        await fs.writeFile(filePath, JSON.stringify(books, null, 2), 'utf8');

        res.json({
            success: true,
            message: `Successfully saved description to ${yearFile}`,
            book: updatedBook
        });

    } catch (error) {
        console.error('Error saving file:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API endpoint to create a new book
app.post('/api/books/create', async (req, res) => {
    try {
        const { yearFile, book } = req.body;

        // Validate required fields
        const requiredFields = ['title', 'author', 'publicationDate', 'publisher', 'publisherURL', 'openAccess'];
        for (const field of requiredFields) {
            if (!book || !book[field] || book[field].toString().trim() === '') {
                return res.status(400).json({
                    success: false,
                    error: `Missing required field: ${field}`,
                    field: field
                });
            }
        }

        // Validate date format (MM-DD-YYYY)
        const dateRegex = /^\d{2}-\d{2}-\d{4}$/;
        if (!dateRegex.test(book.publicationDate)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid publication date format. Use MM-DD-YYYY',
                field: 'publicationDate'
            });
        }

        // Validate openAccess value
        if (book.openAccess !== 'yes' && book.openAccess !== 'no') {
            return res.status(400).json({
                success: false,
                error: 'Open access must be "yes" or "no"',
                field: 'openAccess'
            });
        }

        // Construct file path
        const filePath = path.join(__dirname, 'public', yearFile);

        // Read current JSON file
        const fileContent = await fs.readFile(filePath, 'utf8');
        const books = JSON.parse(fileContent);

        // Create new book with defaults for optional fields
        const newBook = {
            title: book.title,
            author: book.author,
            publicationDate: book.publicationDate,
            publisher: book.publisher,
            publisherURL: book.publisherURL,
            openAccess: book.openAccess,
            coverImage: book.coverImage || '',
            description: book.description || []
        };

        // Add book to array
        books.push(newBook);
        const bookIndex = books.length - 1;

        // Write back to file
        await fs.writeFile(filePath, JSON.stringify(books, null, 2), 'utf8');

        await addBookToFeedIfCurrentYear(newBook);

        res.json({
            success: true,
            message: `Successfully added book to ${yearFile}`,
            book: newBook,
            bookIndex: bookIndex
        });

    } catch (error) {
        console.error('Error creating book:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API endpoint to update an existing book
app.put('/api/books/update', async (req, res) => {
    try {
        const { yearFile, bookIndex, updates } = req.body;

        // Validate input
        if (!yearFile || bookIndex === undefined || !updates) {
            return res.status(400).json({
                success: false,
                error: 'Missing required parameters: yearFile, bookIndex, or updates'
            });
        }

        // Construct file path
        const filePath = path.join(__dirname, 'public', yearFile);

        // Read current JSON file
        const fileContent = await fs.readFile(filePath, 'utf8');
        const books = JSON.parse(fileContent);

        // Validate book index
        if (bookIndex < 0 || bookIndex >= books.length) {
            return res.status(400).json({
                success: false,
                error: 'Invalid book index'
            });
        }

        // Validate date format if being updated
        if (updates.publicationDate) {
            const dateRegex = /^\d{2}-\d{2}-\d{4}$/;
            if (!dateRegex.test(updates.publicationDate)) {
                return res.status(400).json({
                    success: false,
                    error: 'Invalid publication date format. Use MM-DD-YYYY',
                    field: 'publicationDate'
                });
            }
        }

        // Validate openAccess value if being updated
        if (updates.openAccess && updates.openAccess !== 'yes' && updates.openAccess !== 'no') {
            return res.status(400).json({
                success: false,
                error: 'Open access must be "yes" or "no"',
                field: 'openAccess'
            });
        }

        // Merge updates into existing book
        const updatedBook = { ...books[bookIndex], ...updates };
        books[bookIndex] = updatedBook;

        // Write back to file
        await fs.writeFile(filePath, JSON.stringify(books, null, 2), 'utf8');

        res.json({
            success: true,
            message: `Successfully updated book in ${yearFile}`,
            book: updatedBook
        });

    } catch (error) {
        console.error('Error updating book:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API endpoint to upload cover image
app.post('/api/covers/upload', upload.single('cover'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({
                success: false,
                error: 'No file uploaded'
            });
        }

        res.json({
            success: true,
            filename: req.file.filename,
            originalFilename: req.file.originalname,
            tempPath: req.file.path
        });
    } catch (error) {
        console.error('Error uploading cover:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API endpoint to find matching books for uploaded cover
app.post('/api/covers/match', async (req, res) => {
    try {
        const { originalFilename } = req.body;

        if (!originalFilename) {
            return res.status(400).json({
                success: false,
                error: 'Missing originalFilename parameter'
            });
        }

        // Every year file in public/, newest first
        const jsonFiles = (await fs.readdir(path.join(__dirname, 'public')))
            .filter((f) => /^20\d\d\.json$/.test(f))
            .sort()
            .reverse()
            .map((f) => path.join('public', f));

        // Call Python matcher
        const python = spawn('python3', [
            'lib/cover-matcher.py',
            originalFilename,
            ...jsonFiles
        ]);

        let output = '';
        let errorOutput = '';

        python.stdout.on('data', (data) => { output += data; });
        python.stderr.on('data', (data) => { errorOutput += data; });

        python.on('close', (code) => {
            if (code !== 0) {
                console.error('Python matcher error:', errorOutput);
                return res.status(500).json({
                    success: false,
                    error: 'Failed to match cover: ' + errorOutput
                });
            }

            try {
                const matches = JSON.parse(output);
                res.json({ success: true, matches });
            } catch (err) {
                console.error('JSON parse error:', err);
                res.status(500).json({
                    success: false,
                    error: 'Failed to parse matches'
                });
            }
        });
    } catch (error) {
        console.error('Error matching cover:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API endpoint to process and finalize cover image
app.post('/api/covers/process', async (req, res) => {
    try {
        const { tempFilename, yearFile, bookIndex, finalFilename } = req.body;

        if (!tempFilename || !yearFile || bookIndex === undefined) {
            return res.status(400).json({
                success: false,
                error: 'Missing required parameters'
            });
        }

        const tempPath = path.join('/tmp/uploads', tempFilename);
        const coversDir = path.join(__dirname, 'public', 'covers');

        // Read book data to generate filename if not provided
        let coverFilename = finalFilename;
        if (!coverFilename) {
            const filePath = path.join(__dirname, 'public', yearFile);
            const fileContent = await fs.readFile(filePath, 'utf8');
            const books = JSON.parse(fileContent);

            if (bookIndex < 0 || bookIndex >= books.length) {
                return res.status(400).json({
                    success: false,
                    error: 'Invalid book index'
                });
            }

            const book = books[bookIndex];
            const year = book.publicationDate.split('-')[2];
            coverFilename = await imageProcessor.generateCoverFilename(
                book.author, year, coversDir
            );
        }

        const destPath = path.join(coversDir, coverFilename);

        // Process image with ImageMagick
        const processed = await imageProcessor.processImage(tempPath, destPath);

        // Update JSON with cover path
        const filePath = path.join(__dirname, 'public', yearFile);
        const fileContent = await fs.readFile(filePath, 'utf8');
        const books = JSON.parse(fileContent);
        books[bookIndex].coverImage = `covers/${coverFilename}`;
        await fs.writeFile(filePath, JSON.stringify(books, null, 2), 'utf8');

        // Delete temp file
        try {
            await fs.unlink(tempPath);
        } catch (err) {
            console.warn('Failed to delete temp file:', err);
        }

        res.json({
            success: true,
            coverImage: `covers/${coverFilename}`,
            processed: {
                newSize: processed.dimensions,
                fileSize: processed.fileSize
            }
        });
    } catch (error) {
        console.error('Error processing cover:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// API endpoint to delete temporary uploaded file
app.delete('/api/covers/temp/:filename', async (req, res) => {
    try {
        const { filename } = req.params;
        const tempPath = path.join('/tmp/uploads', filename);

        await fs.unlink(tempPath);
        res.json({ success: true });
    } catch (error) {
        console.error('Error deleting temp file:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// ===== DISCOVERY: candidate queue produced by discovery/discover.py =====
const DISCOVERY_DIR = path.join(__dirname, 'discovery');
const CANDIDATES_PATH = path.join(DISCOVERY_DIR, 'candidates.json');
const DISCOVERY_STATE_PATH = path.join(DISCOVERY_DIR, 'state.json');
const DISCOVERY_UA = 'rhetorlist-discovery/1.0 (+https://rhetorlist.net; mailto:timlockridge@gmail.com)';
let discoveryRun = null; // { startedAt, log } while a run is in progress

async function readJsonOr(filePath, fallback) {
    try {
        return JSON.parse(await fs.readFile(filePath, 'utf8'));
    } catch (err) {
        if (err.code === 'ENOENT') return fallback;
        throw err;
    }
}

// Year files that exist in public/, newest first (book manager builds its menus from this)
app.get('/api/years', async (req, res) => {
    try {
        const files = (await fs.readdir(path.join(__dirname, 'public')))
            .filter((f) => /^20\d\d\.json$/.test(f))
            .sort()
            .reverse();
        res.json({ success: true, years: files });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// Pending candidates plus the last run's summary
app.get('/api/candidates', async (req, res) => {
    try {
        const candidates = await readJsonOr(CANDIDATES_PATH, []);
        const state = await readJsonOr(DISCOVERY_STATE_PATH, {});
        res.json({
            success: true,
            candidates: candidates.filter((c) => c.status === 'new'),
            lastRun: state.lastRun || null,
            lastStats: state.lastStats || null,
            running: Boolean(discoveryRun)
        });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// Mark a candidate added or dismissed so it leaves the queue and never comes back
app.post('/api/candidates/status', async (req, res) => {
    try {
        const { id, status } = req.body;
        if (!id || !['new', 'added', 'dismissed'].includes(status)) {
            return res.status(400).json({ success: false, error: 'Need id and a status of new, added or dismissed' });
        }
        const candidates = await readJsonOr(CANDIDATES_PATH, []);
        const candidate = candidates.find((c) => c.id === id);
        if (!candidate) {
            return res.status(404).json({ success: false, error: 'Candidate not found' });
        }
        candidate.status = status;
        candidate.statusChanged = new Date().toISOString();
        await fs.writeFile(CANDIDATES_PATH, JSON.stringify(candidates, null, 2), 'utf8');

        const state = await readJsonOr(DISCOVERY_STATE_PATH, { lastRun: null, seen: {} });
        state.seen = state.seen || {};
        state.seen[id] = status === 'new' ? 'candidate' : status;
        await fs.writeFile(DISCOVERY_STATE_PATH, JSON.stringify(state, null, 2), 'utf8');

        res.json({ success: true, remaining: candidates.filter((c) => c.status === 'new').length });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// Run discovery/discover.py and wait for it (a full run takes a few minutes)
app.post('/api/discover', async (req, res) => {
    if (discoveryRun) {
        return res.status(409).json({ success: false, error: 'A discovery run is already in progress' });
    }
    const args = [path.join(DISCOVERY_DIR, 'discover.py')];
    if (req.body && req.body.classify) args.push('--classify');
    if (req.body && req.body.noEnrich) args.push('--no-enrich');

    discoveryRun = { startedAt: new Date().toISOString(), log: '' };
    const child = spawn('python3', args, { cwd: __dirname });
    const timer = setTimeout(() => child.kill('SIGTERM'), 20 * 60 * 1000);
    child.stdout.on('data', (d) => { discoveryRun.log += d.toString(); });
    child.stderr.on('data', (d) => { discoveryRun.log += d.toString(); });
    child.on('error', (err) => {
        clearTimeout(timer);
        const log = discoveryRun ? discoveryRun.log : '';
        discoveryRun = null;
        res.status(500).json({ success: false, error: `Could not start python3: ${err.message}`, log });
    });
    child.on('close', async (code) => {
        clearTimeout(timer);
        const log = discoveryRun ? discoveryRun.log : '';
        discoveryRun = null;
        if (res.headersSent) return;
        const state = await readJsonOr(DISCOVERY_STATE_PATH, {});
        res.json({
            success: code === 0,
            exitCode: code,
            log: log.split('\n').slice(-40).join('\n'),
            lastRun: state.lastRun || null,
            lastStats: state.lastStats || null
        });
    });
});

// Download a cover image from a URL into the same temp folder uploads use,
// so the normal "process when the book is saved" flow applies
app.post('/api/covers/fetch', async (req, res) => {
    try {
        const { url } = req.body;
        if (!url || !/^https?:\/\//i.test(url)) {
            return res.status(400).json({ success: false, error: 'A full http(s) image URL is required' });
        }
        const response = await fetch(url, { headers: { 'User-Agent': DISCOVERY_UA, Accept: 'image/*' } });
        if (!response.ok) {
            return res.status(502).json({ success: false, error: `Image server answered ${response.status}` });
        }
        const type = (response.headers.get('content-type') || '').toLowerCase();
        const ext = type.includes('png') ? '.png' : type.includes('webp') ? '.webp' :
                    type.includes('avif') ? '.avif' : type.includes('jpeg') || type.includes('jpg') ? '.jpg' : null;
        if (!ext) {
            return res.status(415).json({ success: false, error: `Not an image we can process (${type || 'unknown type'})` });
        }
        const buffer = Buffer.from(await response.arrayBuffer());
        if (buffer.length > 10 * 1024 * 1024) {
            return res.status(413).json({ success: false, error: 'Image is larger than 10MB' });
        }
        await fs.mkdir('/tmp/uploads', { recursive: true });
        const filename = `fetched-${Date.now()}-${Math.random().toString(36).slice(2, 8)}${ext}`;
        await fs.writeFile(path.join('/tmp/uploads', filename), buffer);
        res.json({ success: true, filename, size: buffer.length, contentType: type });
    } catch (error) {
        console.error('Error fetching cover:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Function to open URL in default browser
function openBrowser(url) {
    const command = process.platform === 'darwin' ? 'open' :
                    process.platform === 'win32' ? 'start' : 'xdg-open';
    exec(`${command} ${url}`);
}

// Function to get process info using the specified port
function getPortProcess(port) {
    return new Promise((resolve) => {
        if (process.platform === 'win32') {
            // Windows: Get PID from netstat, then get process name
            exec(`netstat -ano | findstr :${port}`, (error, stdout) => {
                if (error || !stdout) {
                    resolve(null);
                    return;
                }

                const pid = stdout.trim().split(/\s+/).pop();
                exec(`tasklist /FI "PID eq ${pid}" /FO CSV /NH`, (err, out) => {
                    if (err || !out) {
                        resolve({ pid });
                        return;
                    }
                    const processName = out.split(',')[0].replace(/"/g, '');
                    resolve({ pid, name: processName });
                });
            });
        } else {
            // macOS/Linux: Get PID and process name
            exec(`lsof -ti:${port}`, (error, stdout) => {
                if (error || !stdout) {
                    resolve(null);
                    return;
                }

                const pid = stdout.trim();
                exec(`ps -p ${pid} -o comm=`, (err, out) => {
                    const processName = err ? 'unknown' : out.trim();
                    resolve({ pid, name: processName });
                });
            });
        }
    });
}

// Function to kill a process by PID
function killProcess(pid) {
    return new Promise((resolve, reject) => {
        const killCommand = process.platform === 'win32'
            ? `taskkill /PID ${pid} /F`
            : `kill -9 ${pid}`;

        exec(killCommand, (error) => {
            if (error) {
                reject(error);
            } else {
                resolve();
            }
        });
    });
}

// Function to prompt user and handle port conflict
async function handlePortConflict(port) {
    const processInfo = await getPortProcess(port);

    if (!processInfo) {
        // No process found on this port
        return true;
    }

    console.log(`\n⚠️  Port ${port} is already in use!`);
    console.log(`Process: ${processInfo.name || 'unknown'} (PID: ${processInfo.pid})\n`);

    // Use readline to ask user
    const readline = require('readline').createInterface({
        input: process.stdin,
        output: process.stdout
    });

    return new Promise((resolve) => {
        readline.question('Do you want to kill this process and continue? (y/n): ', async (answer) => {
            readline.close();

            if (answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes') {
                try {
                    await killProcess(processInfo.pid);
                    console.log(`✓ Killed process ${processInfo.pid}\n`);
                    resolve(true);
                } catch (error) {
                    console.log(`✗ Failed to kill process: ${error.message}\n`);
                    resolve(false);
                }
            } else {
                console.log('Exiting...\n');
                resolve(false);
            }
        });
    });
}

// Start server with port cleanup
async function startServer() {
    // Check and handle port conflict
    const canStart = await handlePortConflict(PORT);

    if (!canStart) {
        console.log('Server startup cancelled.');
        process.exit(1);
    }

    app.listen(PORT, () => {
        console.log(`
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   Rhetorlist Description Editor                         ║
║                                                          ║
║   Server running at: http://localhost:${PORT}           ║
║                                                          ║
║   Opening browser windows...                            ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
        `);

        // Open both pages in browser
        setTimeout(() => {
            openBrowser(`http://localhost:${PORT}`);
            openBrowser(`http://localhost:${PORT}/book-manager.html`);
        }, 500);
    });
}

// Start the server
startServer();

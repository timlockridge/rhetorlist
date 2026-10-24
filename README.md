# Rhetorlist

Tracking new books in Rhetoric & Writing, Composition Studies, Technical Communication, and related disciplines. Vist [rhetorlist.net](https://rhetorlist.net).

## Project Structure

### Production Files (`public/`)
The `public/` folder contains all files for the production website:
- `index.html` - Main page
- `search.html` - Search page
- `about.html` - About page
- `submit.html` - Submission page
- `*.json` - **Book data files (single source of truth)**
- `css/` - Stylesheets
- `js/` - JavaScript files
- `covers/` - Book cover images
- `feed.json` - JSON feed
- `rhetorlist-og.png` - Open Graph image

**To deploy**: Upload the contents of the `public/` folder to your web server.

### Development Files (Root)
Files in the root directory are for local development only:
- `book-manager.html` - Web-based tool for adding and editing books
- `server.js` - Node.js server (serves public folder + book manager)
- `package.json` - Node.js dependencies
- `manage_urls.py` - Python script to scan for dead links and update publisher URLs
- `match-and-process-covers.sh` - Script for processing book covers

**Important**: The book manager and scripts write directly to `public/*.json` - no syncing needed!

## Using the Book Manager

The book manager lets you add or edit books, update descriptions, and manage cover images.

### Setup
1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the server:
   ```bash
   npm start
   ```

3. Open in browser:
   ```
   http://localhost:4000/book-manager.html
   ```

### How to Use
1. Add a new book or select an existing one
2. Update metadata, descriptions, and cover images as needed
3. Save to update the JSON file directly in `public/`

### After Editing
When you've finished editing, deploy the `public/` folder to your production server. Changes are saved directly to the JSON files in `public/`. (I'm doing this with Github actions, described below.)

### Feed Updates
When you add a new book with a publication date in the current year, the server also prepends an entry to `public/feed.json`.

### Cover Flow
1. Upload a cover image in the book manager
2. The server matches it against books without covers
3. The server resizes/optimizes the image and saves it to `public/covers/`
4. The matching book entry is updated with the new `coverImage` path

## Finding New Books (Discovery)

Instead of visiting each publisher's site, `discovery/discover.py` pulls new titles from sources that publishers maintain for machine access and turns them into a review queue:

- **Crossref** – book DOIs registered by Utah State / UP Colorado, WAC Clearinghouse, Ohio State, Penn State, South Carolina, Michigan State, the presses distributed through JSTOR (Pittsburgh, Alabama, SIU, SUNY, Mississippi…), and keyword searches against Routledge, Peter Lang, Springer/Palgrave, Cambridge, Bloomsbury and Michigan.
- **Parlor Press** – the store's product sitemap, with per-title metadata when the store is not throttling.
- **Open Library** – presses with no DOI programme (SIU Press, NCTE).
- **Publisher RSS** – news feeds, listed separately when a post mentions the field.

Every record is checked against `public/*.json` (normalised title, main title + author surname, fuzzy match), scored for relevance with the keyword lists in `discovery/sources.json`, and written to:

- `discovery/candidates.json` – the live queue the book manager reads
- `discovery/candidates.md` – the same queue as a readable report, plus "probably not in field" titles for a quick scan and a list of sites that still need a manual look
- `discovery/state.json` – last run time and every id already seen, so dismissed or added books never come back

### Running it

```bash
python3 discovery/discover.py
```

Only Python 3's standard library is needed. Useful options:

- `--dry-run` – fetch and print the report without writing anything
- `--source wac --source parlor` – run selected sources only (ids are in `sources.json`)
- `--since 2025-06-01` – earliest publication date to consider (default: 1 January of last year)
- `--no-enrich` – skip the one page view per shortlisted title that picks up descriptions and covers
- `--classify` – also ask Claude to judge each shortlisted title (needs `pip install anthropic` and an `ANTHROPIC_API_KEY`)

The first run records Parlor Press's whole catalogue as a baseline; new Parlor titles appear from the second run on. Run it weekly, or press **Run discovery** inside the book manager.

### Reviewing candidates

Start the server (`npm start`) and choose **Review Candidates** in the book manager. Each candidate shows its cover, metadata, relevance bucket and links to the book page and a publisher-site search. **Load into form** fills the add-book form (title, author, date, publisher, URL, open access, description) and downloads the cover into the normal cover flow; check the publisher URL, then **Create Book** as usual, which also retires the candidate. **Dismiss** removes a candidate for good.

Sources are configured in `discovery/sources.json`. To add a publisher, look up its Crossref member id (`https://api.crossref.org/members?query=<name>`) and add an entry; `mode: "all"` for small presses, `mode: "keywords"` for large ones.

## File Management

- **Single source of truth**: All JSON files live in `public/`
- **Editor writes directly**: No copying or syncing required
- **Deploy**: Just upload the `public/` folder contents to your server

## Deployment

GitHub Actions automatically uses `git subtree` to push the `public/` folder contents to a `production` branch when you push to `main`.

**First time setup on server:**
```bash
cd /var/www/html
git clone -b production --single-branch https://github.com/yourusername/yourrepo.git .
```

**To update (simple git pull!):**
```bash
cd /var/www/html
git pull
```

**How it works:**
- You edit locally and push to `main` branch
- GitHub Action uses `git subtree push --prefix public origin production` to update the production branch
- The `production` branch contains ONLY production files (no dev files!)
- Server only tracks `production` branch, so `git pull` always gets the latest production files
- Unlike force-push, subtree maintains proper git history so pulls work cleanly

## Development Scripts

- `discovery/discover.py` - Find newly published books and build the review queue (see above)
- `manage_urls.py` - Manage publisher URLs in JSON files
- `match-and-process-covers.sh` - Process and match book cover images
- `deploy.sh` - Deploy public folder to production server

## Dependencies

- Node.js (for the local server)
- npm packages: `express`, `multer`
- Python 3 (for cover matching)
- ImageMagick (for cover resizing/optimization)

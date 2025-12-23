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

- `manage_urls.py` - Manage publisher URLs in JSON files
- `match-and-process-covers.sh` - Process and match book cover images
- `deploy.sh` - Deploy public folder to production server

## Dependencies

- Node.js (for the local server)
- npm packages: `express`, `multer`
- Python 3 (for cover matching)
- ImageMagick (for cover resizing/optimization)

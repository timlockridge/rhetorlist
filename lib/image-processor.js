const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);
const fs = require('fs').promises;
const path = require('path');

const TARGET_WIDTH = 400;
const QUALITY = 85;

/**
 * Get image dimensions using ImageMagick
 * @param {string} imagePath - Path to the image file
 * @returns {Promise<string>} Dimensions in format "WxH"
 */
async function getImageDimensions(imagePath) {
    const cmd = `magick identify -format "%wx%h" "${imagePath}"`;
    const { stdout } = await execAsync(cmd);
    return stdout.trim();
}

/**
 * Process image with ImageMagick: resize, optimize, strip metadata
 * @param {string} sourcePath - Source image path
 * @param {string} destPath - Destination path for processed image
 * @param {Object} options - Processing options
 * @param {number} options.width - Target width (default: 400)
 * @param {number} options.quality - JPG quality (default: 85)
 * @returns {Promise<Object>} Processing results with path, dimensions, fileSize
 */
async function processImage(sourcePath, destPath, options = {}) {
    const width = options.width || TARGET_WIDTH;
    const quality = options.quality || QUALITY;

    // Build ImageMagick command
    const cmd = `magick "${sourcePath}" \\
        -auto-orient \\
        -colorspace sRGB \\
        -resize ${width}x \\
        -strip \\
        -quality ${quality} \\
        "${destPath}"`;

    await execAsync(cmd);

    // Get file stats and dimensions
    const stats = await fs.stat(destPath);
    const dimensions = await getImageDimensions(destPath);

    return {
        path: destPath,
        dimensions: dimensions,
        fileSize: Math.round(stats.size / 1024) + 'KB'
    };
}

/**
 * Generate cover filename based on author and year
 * Handles conflicts by adding a-z suffix
 * @param {string} author - Author name
 * @param {string} year - Publication year
 * @param {string} coversDir - Directory where covers are stored
 * @returns {Promise<string>} Generated filename (e.g., "smith2025.jpg" or "smith2025a.jpg")
 */
async function generateCoverFilename(author, year, coversDir) {
    // Extract first author's last name
    const firstAuthor = author.split(' and ')[0].split(',')[0];
    const lastName = firstAuthor.split(' ').pop()
        .toLowerCase()
        .replace(/[^a-z0-9]/g, '');

    const baseName = `${lastName}${year}`;

    // Check for conflicts, add a-z suffix if needed
    let finalName = baseName;
    const basePath = path.join(coversDir, `${baseName}.jpg`);

    try {
        await fs.access(basePath);
        // File exists, need to find available suffix
        for (let i = 97; i <= 122; i++) { // a-z ASCII codes
            const suffix = String.fromCharCode(i);
            const testPath = path.join(coversDir, `${baseName}${suffix}.jpg`);
            try {
                await fs.access(testPath);
                // File exists, try next suffix
            } catch {
                // File doesn't exist, use this suffix
                finalName = `${baseName}${suffix}`;
                break;
            }
        }
    } catch {
        // Base filename doesn't exist, use it
    }

    return `${finalName}.jpg`;
}

/**
 * Check if ImageMagick is installed
 * @returns {Promise<boolean>} True if ImageMagick is available
 */
async function checkImageMagick() {
    try {
        await execAsync('magick -version');
        return true;
    } catch (error) {
        return false;
    }
}

module.exports = {
    processImage,
    getImageDimensions,
    generateCoverFilename,
    checkImageMagick
};

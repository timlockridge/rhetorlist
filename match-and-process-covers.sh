#!/bin/bash

# Combined Cover Matching and Processing Script for Rhetorlist
# Automatically matches, processes, and adds cover images to JSON files

# Configuration
TO_PROCESS_DIR="./to-process"
COVERS_DIR="./covers"
JSON_FILES=("2025.json" "2024.json" "2023.json" "2022.json" "2021.json" "2020.json" "2019.json" "2018.json")
TARGET_WIDTH=400
QUALITY=85

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo "========================================="
echo "Smart Cover Matcher & Processor"
echo "========================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed.${NC}"
    exit 1
fi

# Check if ImageMagick is installed
if ! command -v magick &> /dev/null; then
    echo -e "${RED}Error: ImageMagick is not installed.${NC}"
    echo "Please install it with: brew install imagemagick"
    exit 1
fi

# Create covers directory if needed
mkdir -p "$COVERS_DIR"

# Check if we have images to process
shopt -s nullglob
images=("$TO_PROCESS_DIR"/*.{jpg,jpeg,png,JPG,JPEG,PNG,webp,WEBP,avif,AVIF})
shopt -u nullglob

if [ ${#images[@]} -eq 0 ]; then
    echo -e "${YELLOW}No images found in $TO_PROCESS_DIR${NC}"
    echo "Add some cover images and try again!"
    exit 0
fi

echo -e "Found ${BOLD}${#images[@]}${NC} image(s) to process"
echo ""

# Counter for processed images
processed_count=0
skipped_count=0

# Process each image
for image_path in "${images[@]}"; do
    filename=$(basename "$image_path")
    name_without_ext="${filename%.*}"
    extension="${filename##*.}"

    echo "========================================="
    echo -e "${BLUE}${BOLD}Processing: $filename${NC}"
    echo "========================================="
    echo ""

    # Try to find matching book using Python
    match_result=$(IMAGE_FILENAME="$filename" python3 << 'PYTHON_EOF'
import json
import sys
import os
import re

def normalize_text(text):
    """Normalize text for matching: lowercase, alphanumeric only"""
    # First, split camelCase words (e.g., "RhetoricalReception" -> "Rhetorical Reception")
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Then convert to lowercase and keep only alphanumeric + spaces
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()

def extract_words(text):
    """Extract meaningful words from text"""
    normalized = normalize_text(text)
    # Filter out very short words (likely not meaningful)
    words = [w for w in normalized.split() if len(w) > 2]
    return set(words)

def calculate_match_score(filename_words, title_words, author_words):
    """Calculate how well filename matches title and author"""
    score = 0

    # Count matching words in title
    title_matches = len(filename_words & title_words)
    score += title_matches * 3  # Weight title matches higher

    # Count matching words in author
    author_matches = len(filename_words & author_words)
    score += author_matches * 2  # Weight author matches

    # Bonus for multiple matches
    if title_matches > 1:
        score += 2
    if author_matches > 0 and title_matches > 0:
        score += 3  # Bonus for matching both

    return score

# Get filename from environment
filename = os.environ.get('IMAGE_FILENAME', '')
name_without_ext = os.path.splitext(filename)[0]
filename_words = extract_words(name_without_ext)

# Load all JSON files and find books without covers
best_match = None
best_score = 0
best_book_index = -1

json_files = ['2025.json', '2024.json', '2023.json', '2022.json', '2021.json', '2020.json', '2019.json', '2018.json']

for json_file in json_files:
    if not os.path.exists(json_file):
        continue

    try:
        with open(json_file, 'r') as f:
            books = json.load(f)

        for idx, book in enumerate(books):
            # Skip books that already have covers
            if 'coverImage' in book and book.get('coverImage', '').strip():
                continue

            title = book.get('title', '')
            author = book.get('author', '')

            title_words = extract_words(title)
            author_words = extract_words(author)

            score = calculate_match_score(filename_words, title_words, author_words)

            if score > best_score:
                best_score = score
                best_book_index = idx
                best_match = {
                    'title': title,
                    'author': author,
                    'pubdate': book.get('publicationDate', ''),
                    'publisher': book.get('publisher', ''),
                    'json_file': json_file,
                    'book_index': idx,
                    'score': score
                }
    except Exception as e:
        print(f"Error reading {json_file}: {e}", file=sys.stderr)

# Output result
if best_match and best_score >= 3:  # Minimum threshold for suggesting a match
    print(f"MATCH_FOUND")
    print(f"TITLE:{best_match['title']}")
    print(f"AUTHOR:{best_match['author']}")
    print(f"PUBDATE:{best_match['pubdate']}")
    print(f"PUBLISHER:{best_match['publisher']}")
    print(f"JSON_FILE:{best_match['json_file']}")
    print(f"BOOK_INDEX:{best_match['book_index']}")
    print(f"SCORE:{best_match['score']}")
else:
    print("NO_MATCH")

PYTHON_EOF
)

    # Parse Python output
    if echo "$match_result" | grep -q "^MATCH_FOUND"; then
        # Extract match details
        match_title=$(echo "$match_result" | grep "^TITLE:" | cut -d':' -f2-)
        match_author=$(echo "$match_result" | grep "^AUTHOR:" | cut -d':' -f2-)
        match_pubdate=$(echo "$match_result" | grep "^PUBDATE:" | cut -d':' -f2-)
        match_publisher=$(echo "$match_result" | grep "^PUBLISHER:" | cut -d':' -f2-)
        match_json_file=$(echo "$match_result" | grep "^JSON_FILE:" | cut -d':' -f2-)
        match_book_index=$(echo "$match_result" | grep "^BOOK_INDEX:" | cut -d':' -f2-)

        echo -e "${GREEN}Possible match found!${NC}"
        echo ""
        echo -e "${BOLD}Image filename:${NC} $filename"
        echo ""
        echo -e "${BOLD}Suggested book:${NC}"
        echo -e "  ${BLUE}Title:${NC} $match_title"
        echo -e "  ${BLUE}Author:${NC} $match_author"
        echo -e "  ${BLUE}Publisher:${NC} $match_publisher"
        echo -e "  ${BLUE}Date:${NC} $match_pubdate"
        echo ""

        read -p "Does this match? (y/n/s=skip/q=quit): " choice

        if [[ "$choice" =~ ^[Yy]$ ]]; then
            # Extract year from publication date (format: MM-DD-YYYY)
            year=$(echo "$match_pubdate" | cut -d'-' -f3)

            # Extract first author's last name
            first_author=$(echo "$match_author" | sed 's/ and .*//' | sed 's/,.*//' | awk '{print $NF}')
            last_name=$(echo "$first_author" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]//g')

            # Build base filename: lastname+year
            base_name="${last_name}${year}"

            # Check for conflicts and add letter suffix if needed
            final_name="$base_name"
            if [ -f "$COVERS_DIR/${base_name}.jpg" ]; then
                suffix='a'
                while [ -f "$COVERS_DIR/${base_name}${suffix}.jpg" ]; do
                    suffix=$(echo "$suffix" | tr 'a-y' 'b-z')
                    if [ "$suffix" = "z" ]; then
                        echo -e "${RED}Error: Too many conflicts${NC}"
                        break
                    fi
                done
                final_name="${base_name}${suffix}"
                echo -e "${YELLOW}Note: Using ${final_name}.jpg to avoid conflict${NC}"
            fi

            output_file="$COVERS_DIR/${final_name}.jpg"
            cover_image_path="covers/${final_name}.jpg"

            # Process the image with ImageMagick
            echo -e "${GREEN}Processing image...${NC}"

            # Show input format
            input_format=$(magick identify -format "%m" "$image_path")
            echo "  Input format: $input_format"

            # Get original dimensions
            original_width=$(magick identify -format "%w" "$image_path")
            original_height=$(magick identify -format "%h" "$image_path")
            echo "  Original size: ${original_width}x${original_height}px"

            # Process: resize, optimize, and convert to JPG
            # (automatically converts webp, png, etc. to JPG based on output extension)
            magick "$image_path" \
                -auto-orient \
                -colorspace sRGB \
                -resize "${TARGET_WIDTH}x" \
                -strip \
                -quality $QUALITY \
                "$output_file"

            if [ $? -eq 0 ]; then
                # Get new dimensions and file size
                new_width=$(magick identify -format "%w" "$output_file")
                new_height=$(magick identify -format "%h" "$output_file")
                new_size=$(du -h "$output_file" | cut -f1)
                echo "  New size: ${new_width}x${new_height}px (${new_size})"

                # Update JSON file with coverImage path
                echo -e "${GREEN}Updating JSON file...${NC}"

                python3 << PYTHON_UPDATE_EOF
import json

json_file = '$match_json_file'
book_index = int('$match_book_index')
cover_path = '$cover_image_path'

try:
    with open(json_file, 'r') as f:
        books = json.load(f)

    # Add coverImage to the matched book
    books[book_index]['coverImage'] = cover_path

    # Write back to file with nice formatting
    with open(json_file, 'w') as f:
        json.dump(books, f, indent=2, ensure_ascii=False)

    print(f"Updated {json_file}")
except Exception as e:
    print(f"Error updating JSON: {e}", file=sys.stderr)
    sys.exit(1)

PYTHON_UPDATE_EOF

                if [ $? -eq 0 ]; then
                    # Delete the original
                    rm "$image_path"

                    echo -e "${GREEN}✓ Complete!${NC}"
                    echo -e "  Cover saved: ${final_name}.jpg"
                    echo -e "  JSON updated: $match_json_file"
                    echo -e "  Original deleted"
                    ((processed_count++))
                else
                    echo -e "${RED}✗ Error updating JSON file${NC}"
                    ((skipped_count++))
                fi
            else
                echo -e "${RED}✗ Error processing image${NC}"
                ((skipped_count++))
            fi
            echo ""
        elif [[ "$choice" == "q" ]]; then
            echo "Quitting..."
            break
        else
            echo -e "${YELLOW}Skipped${NC}"
            ((skipped_count++))
            echo ""
        fi
    else
        echo -e "${YELLOW}No automatic match found.${NC}"
        echo -e "${BLUE}Filename:${NC} $filename"
        echo ""
        read -p "Skip this file? (y=skip/m=manual rename/q=quit): " choice

        if [[ "$choice" == "m" ]]; then
            read -p "Enter new filename (without extension): " manual_name
            if [ -n "$manual_name" ]; then
                sanitized_name=$(echo "$manual_name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
                new_path="$TO_PROCESS_DIR/${sanitized_name}.${extension}"
                mv "$image_path" "$new_path"
                echo -e "${GREEN}✓ Renamed to: ${sanitized_name}.${extension}${NC}"
                echo "  Run the script again to match this file."
            fi
        elif [[ "$choice" == "q" ]]; then
            echo "Quitting..."
            break
        else
            echo -e "${YELLOW}Skipped${NC}"
            ((skipped_count++))
        fi
        echo ""
    fi
done

# Summary
echo "========================================="
echo "Processing Complete!"
echo "========================================="
echo "Images processed: $processed_count"
echo "Images skipped: $skipped_count"
echo ""
if [ $processed_count -gt 0 ]; then
    echo -e "${GREEN}All cover images have been optimized and added to JSON files!${NC}"
fi
echo "========================================="

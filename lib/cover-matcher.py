#!/usr/bin/env python3
"""
Fuzzy matching for book covers
Usage: python3 cover-matcher.py <filename> <json_file1> [json_file2...]
Output: JSON array of matches to stdout
"""
import json
import sys
import os
import re
from typing import List, Dict


def normalize_text(text: str) -> str:
    """Normalize text: camelCase split, lowercase, alphanumeric only"""
    # First, split camelCase words (e.g., "RhetoricalReception" -> "Rhetorical Reception")
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Then convert to lowercase and keep only alphanumeric + spaces
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def extract_words(text: str) -> set:
    """Extract meaningful words (> 2 chars)"""
    normalized = normalize_text(text)
    # Filter out very short words (likely not meaningful)
    words = [w for w in normalized.split() if len(w) > 2]
    return set(words)


def calculate_match_score(filename_words: set, title_words: set, author_words: set) -> int:
    """Calculate match score with weighted components"""
    score = 0

    # Count matching words in title (3x weight)
    title_matches = len(filename_words & title_words)
    score += title_matches * 3

    # Count matching words in author (2x weight)
    author_matches = len(filename_words & author_words)
    score += author_matches * 2

    # Bonus for multiple matches
    if title_matches > 1:
        score += 2
    if author_matches > 0 and title_matches > 0:
        score += 3  # Bonus for matching both

    return score


def find_matches(filename: str, json_files: List[str], min_score: int = 3) -> List[Dict]:
    """Find matching books without covers"""
    # Remove file extension from filename
    name_without_ext = os.path.splitext(filename)[0]
    filename_words = extract_words(name_without_ext)

    matches = []

    for json_file in json_files:
        if not os.path.exists(json_file):
            print(f"Warning: {json_file} not found", file=sys.stderr)
            continue

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                books = json.load(f)

            for idx, book in enumerate(books):
                # Skip books that already have covers
                if book.get('coverImage', '').strip():
                    continue

                title = book.get('title', '')
                author = book.get('author', '')

                title_words = extract_words(title)
                author_words = extract_words(author)

                score = calculate_match_score(filename_words, title_words, author_words)

                if score >= min_score:
                    matches.append({
                        'title': title,
                        'author': author,
                        'publisher': book.get('publisher', ''),
                        'publicationDate': book.get('publicationDate', ''),
                        'yearFile': os.path.basename(json_file),
                        'bookIndex': idx,
                        'score': score,
                        'hasCover': False
                    })
        except Exception as e:
            print(f"Error reading {json_file}: {e}", file=sys.stderr)

    # Sort by score descending, limit to top 5
    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches[:5]


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: cover-matcher.py <filename> <json_file1> [json_file2...]", file=sys.stderr)
        sys.exit(1)

    filename = sys.argv[1]
    json_files = sys.argv[2:]

    matches = find_matches(filename, json_files)
    print(json.dumps(matches, indent=2, ensure_ascii=False))

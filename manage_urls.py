#!/usr/bin/env python3
import json
import os
import glob
import sys
import urllib.request
import urllib.error
import socket
from datetime import datetime

# Configuration
JSON_PATTERN = "20[0-9][0-9].json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"

class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def load_all_data():
    """Loads all year-based JSON files."""
    files = sorted(glob.glob(JSON_PATTERN))
    data_map = {}
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data_map[f] = json.load(file)
        except Exception as e:
            print(f"{Color.RED}Error loading {f}: {e}{Color.END}")
    return data_map

def save_file(filename, data):
    """Saves a single JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"{Color.GREEN}Saved changes to {filename}{Color.END}")
    except Exception as e:
        print(f"{Color.RED}Error saving {filename}: {e}{Color.END}")

def check_url(url, timeout=5):
    """Checks if a URL is accessible. Returns (True, status) or (False, error)."""
    if not url:
        return False, "Empty URL"
    
    try:
        req = urllib.request.Request(
            url, 
            data=None, 
            headers={'User-Agent': USER_AGENT}
        )
        # We try a HEAD request first to save bandwidth, but some servers block it.
        # So we'll just do a normal open but close quickly.
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return True, response.getcode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"Connection Error: {e.reason}"
    except socket.timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

def mode_search_and_update(data_map):
    while True:
        print(f"\n{Color.BOLD}--- Search & Update Mode ---{Color.END}")
        query = input("Enter title or author (or 'q' to quit): ").strip().lower()
        if query == 'q':
            break
        if not query:
            continue

        matches = []
        for filename, books in data_map.items():
            for idx, book in enumerate(books):
                if query in book.get('title', '').lower() or query in book.get('author', '').lower():
                    matches.append((filename, idx, book))

        if not matches:
            print(f"{Color.YELLOW}No matches found.{Color.END}")
            continue

        print(f"\nFound {len(matches)} matches:")
        for i, (fname, idx, book) in enumerate(matches):
            print(f"[{i+1}] {Color.BOLD}{book.get('title')}{Color.END}")
            print(f"    Author: {book.get('author')}")
            print(f"    File: {fname}")
            print(f"    Current URL: {book.get('publisherURL')}")

        try:
            selection = input("\nSelect number to edit (or Enter to search again): ")
            if not selection:
                continue
            
            sel_idx = int(selection) - 1
            if 0 <= sel_idx < len(matches):
                fname, book_idx, book = matches[sel_idx]
                
                new_url = input(f"{Color.BLUE}New URL (Enter to keep current): {Color.END}").strip()
                if new_url:
                    data_map[fname][book_idx]['publisherURL'] = new_url
                    save_file(fname, data_map[fname])
                else:
                    print("No change made.")
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input.")

def mode_scan_broken(data_map):
    print(f"\n{Color.BOLD}--- Scanning for Broken Links... ---{Color.END}")
    print("This may take a few minutes. Checking HTTP status codes...")
    
    total_checked = 0
    issues_found = 0

    for filename, books in data_map.items():
        # Iterate backwards so we can potentially delete if needed (though we're just updating here)
        # actually forward is fine for updates.
        print(f"Scanning {filename}...")
        
        updated_file = False
        
        for idx, book in enumerate(books):
            url = book.get('publisherURL')
            title = book.get('title', 'Unknown Title')
            
            if not url:
                continue

            total_checked += 1
            sys.stdout.write(f"\rChecked: {total_checked} | Issues: {issues_found}")
            sys.stdout.flush()

            is_valid, status = check_url(url)
            
            if not is_valid:
                sys.stdout.write("\n") # Clear line
                issues_found += 1
                print(f"\n{Color.RED}[BROKEN] {title}{Color.END}")
                print(f"  Author: {book.get('author')}")
                print(f"  URL: {url}")
                print(f"  Error: {status}")
                
                action = input(f"{Color.BLUE}Action? (n=new url, i=ignore/skip, q=quit scan): {Color.END}").lower().strip()
                
                if action == 'n':
                    new_url = input("Enter new URL: ").strip()
                    if new_url:
                        book['publisherURL'] = new_url
                        updated_file = True
                        print(f"{Color.GREEN}Updated.{Color.END}")
                elif action == 'q':
                    return
                # else ignore
        
        if updated_file:
            save_file(filename, books)

    print(f"\nScan complete. Checked {total_checked} links.")

def main():
    print("=========================================")
    print("Rhetorlist URL Manager")
    print("=========================================")
    
    # Check dependencies (standard lib only, so likely fine)
    
    data_map = load_all_data()
    total_books = sum(len(b) for b in data_map.values())
    print(f"Loaded {len(data_map)} files containing {total_books} books.")

    while True:
        print("\nSelect Mode:")
        print("1. Search & Update (Find a specific book and change its URL)")
        print("2. Scan for Broken Links (Check all URLs and fix broken ones)")
        print("3. Quit")
        
        choice = input("Choice: ").strip()
        
        if choice == '1':
            mode_search_and_update(data_map)
        elif choice == '2':
            mode_scan_broken(data_map)
        elif choice == '3':
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()

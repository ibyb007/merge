#!/usr/bin/env python3
"""
Updated M3U Playlist Merger for IPTV (Full Block Preservation + EPG + Exclusions)
===============================================================================

Fetches three M3U playlists, parses full entry blocks (#EXTINF + all #props like KODIPROP/DRM + URL),
excludes Devotional/Music/Educational groups and channels containing specified languages in titles,
merges unique by URL (first occurrence wins, preserves all metadata),
with fancode.m3u on top. Adds global EPG to header.

Usage: python merge_m3u.py
Output: merged.m3u
"""

import urllib.request
import re  # For case-insensitive group matching and title extraction
from collections import OrderedDict

# Sources: fancode FIRST for top priority in merge order
SOURCES = [
    "https://raw.githubusercontent.com/Jitendra-unatti/fancode/refs/heads/main/data/fancode.m3u",
    "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/jtv.m3u",
    "https://raw.githubusercontent.com/alex8875/m3u/refs/heads/main/z5.m3u"
]

# Excluded groups (case-insensitive)
EXCLUDED_GROUPS = ["devotional", "music", "educational"]

# Languages to exclude in channel titles (case-insensitive)
EXCLUDE_LANGUAGES = ['tamil', 'telugu', 'oriya', 'gujarati', 'kannada', 'malayalam', 'bhojpuri', 'punjabi', 'marathi']

EPG_URL = "https://raw.githubusercontent.com/ibyb007/myepg/main/epg.xml.gz"

def fetch_m3u(url):
    """Fetch M3U content from URL."""
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def get_group_title(extinf_line):
    """Extract group-title from #EXTINF line (case-insensitive)."""
    match = re.search(r'group-title="([^"]*)"', extinf_line, re.IGNORECASE)
    return match.group(1).lower() if match else ''

def is_excluded_group(extinf_line):
    """Check if #EXTINF line contains excluded group-titles (case-insensitive)."""
    lower_line = extinf_line.lower()
    for group in EXCLUDED_GROUPS:
        if f'group-title="{group}"' in lower_line:
            return True
    return False

def is_excluded_language(title):
    """Check if channel title contains excluded languages (case-insensitive)."""
    lower_title = title.lower()
    for lang in EXCLUDE_LANGUAGES:
        if lang in lower_title:
            return True
    return False

def parse_m3u(content):
    """Parse M3U into dict of URL: list of exact lines for the entry block (#EXTINF + all #props).
    Skips excluded groups and language-based exclusions; preserves everything verbatim;
    handles plain URLs as fallback.
    """
    if not content:
        return {}
    lines = content.split('\n')
    entries = OrderedDict()  # Preserve order within source
    i = 0
    group_excluded_count = 0
    lang_excluded_count = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:'):
            extinf = line
            
            if is_excluded_group(extinf):
                group_excluded_count += 1
                # Skip the whole block
                i += 1
                while i < len(lines) and (lines[i].startswith('#') or not lines[i].strip()):
                    i += 1
                if i < len(lines) and not lines[i].startswith('#'):
                    i += 1  # Skip URL
                continue
            
            # Extract title: everything after the last comma
            title_match = re.search(r',(.+)$', extinf)
            title = title_match.group(1).strip() if title_match else ''
            
            if is_excluded_language(title):
                lang_excluded_count += 1
                # Skip the whole block
                i += 1
                while i < len(lines) and (lines[i].startswith('#') or not lines[i].strip()):
                    i += 1
                if i < len(lines) and not lines[i].startswith('#'):
                    i += 1  # Skip URL
                continue
            
            block = [extinf]  # Start with EXTINF
            i += 1
            # Collect all consecutive # lines (props like KODIPROP, DRM, etc.)
            while i < len(lines):
                next_line = lines[i]
                if next_line.startswith('#') and not next_line.startswith('#EXTINF:'):
                    block.append(next_line)
                    i += 1
                else:
                    break
            # Now at URL (non-# line)
            if i < len(lines):
                url = lines[i]
                if url and not url.startswith('#'):
                    # Dedupe within source by URL
                    if url not in entries:
                        entries[url] = block
                        print(f"Parsed full block ({len(block)} props): {title[:30]}... -> {url[:50]}...")
                    i += 1
                    continue
            # If no URL, skip
            i += 1
        elif line and not line.startswith('#'):
            # Fallback: plain URL without block (no group or title to exclude)
            url = line
            if url not in entries:
                entries[url] = []  # Empty block
                print(f"Parsed plain URL: {url[:50]}...")
            i += 1
        else:
            i += 1  # Skip headers, comments, empty
    print(f"  Excluded {group_excluded_count} group-based entries, {lang_excluded_count} language-based entries")
    return entries

def merge_m3us(source_entries):
    """Merge full blocks from sources in order (fancode first), unique by URL."""
    merged = OrderedDict()
    total_added = 0
    for source_name, entries in source_entries.items():
        print(f"\nMerging from {source_name} ({len(entries)} entries)...")
        for url, block in entries.items():
            if url not in merged:
                merged[url] = block
                total_added += 1
                print(f"  Added full block ({len(block)} lines): {url[:30]}...")
            # Uncomment below for NO deduplication (full concat, even duplicates):
            # merged[url] = block  # Always add
    print(f"\nTotal unique entries merged: {len(merged)}")
    return merged

def save_merged(merged, output_file='merged.m3u'):
    """Save merged entries to M3U with EPG-enabled header, writing full blocks verbatim."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U url-tvg="{EPG_URL}"\n')  # Header with global EPG
        for url, block in merged.items():
            for b_line in block:
                f.write(b_line + '\n')
            f.write(url + '\n')
    print(f"Saved {len(merged)} entries (with full props + EPG) to {output_file}")

def main():
    source_entries = {}
    print("Fetching sources...\n")
    for i, url in enumerate(SOURCES, 1):
        source_name = f"Source {i} ({url.split('/')[-1].split('.')[0] if '.' in url else 'Unknown'})"
        print(f"Fetching {source_name}...")
        content = fetch_m3u(url)
        if content:
            entries = parse_m3u(content)
            source_entries[source_name] = entries
            print(f"  Parsed {len(entries)} entries")
        else:
            print(f"  Skipped (empty or error)")
    
    if not source_entries:
        print("No sources loaded. Exiting.")
        return
    
    print("\nMerging (fancode on top, excluding groups and languages)...")
    merged_entries = merge_m3us(source_entries)
    save_merged(merged_entries)
    print("Done! All metadata preserved, groups/languages excluded, EPG added. Check merged.m3u. 🎵")

if __name__ == "__main__":
    main()

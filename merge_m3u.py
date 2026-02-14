#!/usr/bin/env python3
"""
M3U Playlist Merger - IPTV (Full Block Preservation + EPG + Source-Specific Exclusions)
===================================================================================

Fetches playlists from env vars: share, jtv, fcode, sliv
- Global: exclude devotional/music/education/shopping groups for ALL sources
- JTV only: additionally exclude groups containing regional languages ('tamil', 'telugu', etc.)
- Other sources: exclude certain languages from channel titles (after comma)
- sliv (fourth): restrict to only 'movies' + 'bengali' groups
- Merge unique by URL (first wins), preserve full #EXTINF + props + URL

Output: merged.m3u with EPG header
"""

import urllib.request
import re
import os
from collections import OrderedDict

# ── Sources ────────────────────────────────────────────────────────────────
share = os.getenv('share')
jtv   = os.getenv('jtv')
fcode = os.getenv('fcode')
sliv  = os.getenv('sliv')

SOURCES = [share, jtv, fcode, sliv]
SOURCE_NAMES = ["share", "jtv", "fcode", "sliv"]

# Global excluded groups (applied to EVERY source)
GLOBAL_EXCLUDED_GROUPS = ["devotional", "education", "shopping", "music", "educational"]

# JTV-specific excluded groups (applied ONLY to jtv source)
JTV_EXCLUDE_GROUPS = [
    'tamil', 'telugu', 'odia', 'oriya', 'gujarati', 'kannada', 'malayalam',
    'bhojpuri', 'punjabi', 'marathi', 'unknown', 'nepali', 'french',
    'haryanvi', 'urdu'
]

# Title-based language exclusions (applied to share, fcode, sliv — NOT jtv)
TITLE_EXCLUDE_LANGUAGES = ['tamil', 'telugu', 'oriya', 'gujarati', 'gujarat', 'kannada', 'malayalam', 'bhojpuri', 'punjabi', 'marathi']

EPG_URL = "https://raw.githubusercontent.com/ibyb007/myepg/main/epg.xml.gz"

def fetch_m3u(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.read().decode('utf-8')
    except Exception as e:
        print(f"Fetch error {url}: {e}")
        return None

def get_group_title(extinf):
    m = re.search(r'group-title="([^"]*)"', extinf, re.I)
    return m.group(1).lower() if m else ''

def is_global_excluded_group(extinf):
    lower = extinf.lower()
    return any(f'group-title="{g}"' in lower for g in GLOBAL_EXCLUDED_GROUPS)

def is_jtv_excluded_group(group_lower):
    return any(lang in group_lower for lang in JTV_EXCLUDE_GROUPS)

def is_excluded_language_in_title(title):
    lower_title = title.lower()
    return any(lang in lower_title for lang in TITLE_EXCLUDE_LANGUAGES)

def parse_m3u(content, source_name="", is_special=False):
    if not content:
        return {}
    
    lines = content.splitlines()
    entries = OrderedDict()
    i = 0
    global_group_excl = 0
    jtv_group_excl = 0
    title_lang_excl = 0
    
    is_jtv = source_name.lower() == "jtv"
    
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith('#EXTINF:'):
            extinf = line
            group_lower = get_group_title(extinf)
            
            # 1. Global group exclusion (all sources)
            if is_global_excluded_group(extinf):
                global_group_excl += 1
                i = skip_to_next_entry(lines, i)
                continue
            
            # 2. JTV-specific group exclusion
            if is_jtv and is_jtv_excluded_group(group_lower):
                jtv_group_excl += 1
                i = skip_to_next_entry(lines, i)
                continue
            
            # 3. Special source (sliv) restriction
            if is_special and group_lower not in ['movies', 'bengali']:
                global_group_excl += 1  # count as global for consistency
                i = skip_to_next_entry(lines, i)
                continue
            
            # 4. Title language exclusion (only non-JTV sources)
            title_match = re.search(r',(.+)$', extinf)
            title = title_match.group(1).strip() if title_match else ''
            if not is_jtv and is_excluded_language_in_title(title):
                title_lang_excl += 1
                i = skip_to_next_entry(lines, i)
                continue
            
            # Keep this entry
            block = [extinf]
            i += 1
            while i < len(lines) and lines[i].startswith('#') and not lines[i].startswith('#EXTINF:'):
                block.append(lines[i].rstrip())
                i += 1
            
            if i < len(lines):
                url = lines[i].rstrip()
                if url and not url.startswith('#'):
                    if url not in entries:
                        entries[url] = block
                        print(f"[{source_name}] + {title[:40]}... ({group_lower}) → {url[:55]}...")
                    i += 1
                    continue
            i += 1
        elif line.strip() and not line.startswith('#'):
            # Plain URL fallback
            url = line
            if url not in entries:
                entries[url] = []
                print(f"[{source_name}] plain URL: {url[:55]}...")
            i += 1
        else:
            i += 1
    
    print(f"[{source_name}] Exclusions → global groups: {global_group_excl} | "
          f"jtv groups: {jtv_group_excl} | title langs: {title_lang_excl}")
    return entries

def skip_to_next_entry(lines, start):
    i = start + 1
    while i < len(lines) and lines[i].startswith('#'):
        i += 1
    if i < len(lines) and not lines[i].startswith('#'):
        i += 1  # skip URL
    return i

def merge_m3us(source_entries):
    merged = OrderedDict()
    for src, entries in source_entries.items():
        print(f"\n→ Merging {src} ({len(entries)} channels)")
        for url, block in entries.items():
            if url not in merged:
                merged[url] = block
    print(f"\nTotal unique: {len(merged)}")
    return merged

def save_merged(merged):
    with open('merged.m3u', 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U url-tvg="{EPG_URL}"\n')
        for block in merged.values():
            for ln in block:
                f.write(ln + '\n')
            f.write(list(merged.keys())[list(merged.values()).index(block)] + '\n')  # URL
    print(f"Saved {len(merged)} entries → merged.m3u")

def main():
    source_entries = {}
    print("Processing sources...\n")
    
    for idx, url in enumerate(SOURCES):
        if not url:
            print(f"{SOURCE_NAMES[idx]} not set → skip")
            continue
        name = SOURCE_NAMES[idx]
        print(f"→ {name}")
        content = fetch_m3u(url)
        special = (name == "sliv")
        if content:
            source_entries[name] = parse_m3u(content, name, special)
    
    if not source_entries:
        print("Nothing loaded.")
        return
    
    merged = merge_m3us(source_entries)
    save_merged(merged)
    print("Finished.")

if __name__ == "__main__":
    main()

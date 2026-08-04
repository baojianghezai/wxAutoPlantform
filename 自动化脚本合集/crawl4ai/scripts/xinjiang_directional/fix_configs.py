#!/usr/bin/env python3
"""Fix all directional config JSON files: remove Python r-prefix, escape backslashes for JSON."""
import glob
import re
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(SCRIPT_DIR, "xinjiang_directional")

def fix_config(content):
    """Fix Python raw string syntax to proper JSON."""
    # Remove r prefix from string values: r"..." -> "..."
    # Use simple string replacement approach
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        # Remove r" prefix on pattern/date_in_md lines
        if '"pattern"' in line or '"date_in_md"' in line:
            line = line.replace('r"', '"').replace("r'", "'")
        fixed_lines.append(line)
    content = '\n'.join(fixed_lines)
    # Escape backslashes for JSON (but not already escaped ones)
    # Simple approach: replace \d, \s, \., etc. with double backslash versions
    # But only within pattern and date_in_md values
    # Actually, let's just do a global replace of specific patterns
    content = content.replace('\\\\d', '__ESCAPED_D__')  # temp save already escaped
    content = content.replace('\\d', '\\\\d')
    content = content.replace('__ESCAPED_D__', '\\\\d')
    
    content = content.replace('\\\\s', '__ESCAPED_S__')
    content = content.replace('\\s', '\\\\s')
    content = content.replace('__ESCAPED_S__', '\\\\s')
    
    content = content.replace('\\\\.', '__ESCAPED_DOT__')
    content = content.replace('\\.', '\\\\.')
    content = content.replace('__ESCAPED_DOT__', '\\\\.')
    
    content = content.replace('\\\\+', '__ESCAPED_PLUS__')
    content = content.replace('\\+', '\\\\+')
    content = content.replace('__ESCAPED_PLUS__', '\\\\+')
    
    content = content.replace('\\\\/', '__ESCAPED_SLASH__')
    content = content.replace('\\/', '\\\\/')
    content = content.replace('__ESCAPED_SLASH__', '\\\\/')
    
    return content

for f in sorted(glob.glob(os.path.join(CONFIG_DIR, 'config_*.json'))):
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    fixed = fix_config(content)
    with open(f, 'w', encoding='utf-8') as fh:
        fh.write(fixed)
    try:
        data = json.loads(fixed)
        print(f'OK: {os.path.basename(f)} ({len(data["sources"])} sources)')
    except Exception as e:
        print(f'FAIL: {os.path.basename(f)}: {e}')

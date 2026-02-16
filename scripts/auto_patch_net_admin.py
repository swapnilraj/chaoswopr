#!/usr/bin/env python3
"""Automatically patch ethereum-package Starlark files to add NET_ADMIN capability.

This script finds all ServiceConfig calls in .star files and adds the
capabilities parameter to enable tc/netem network fault injection.
"""

import os
import re
import sys
from pathlib import Path


def patch_service_config(content: str) -> tuple[str, bool]:
    """Add NET_ADMIN capability to ServiceConfig calls.

    Args:
        content: File content as string.

    Returns:
        Tuple of (patched_content, was_modified).
    """
    # Check if already patched
    if 'NET_ADMIN' in content:
        return content, False

    # Pattern to match ServiceConfig(...) with closing parenthesis
    # We'll add capabilities before the closing paren

    modified = False
    lines = content.split('\n')
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for ServiceConfig( calls
        if 'ServiceConfig(' in line:
            # Find the matching closing parenthesis
            # Track brace depth to handle nested structures
            config_lines = [line]
            paren_depth = line.count('(') - line.count(')')
            j = i + 1

            while j < len(lines) and paren_depth > 0:
                next_line = lines[j]
                config_lines.append(next_line)
                paren_depth += next_line.count('(') - next_line.count(')')
                j += 1

            # Check if this ServiceConfig already has capabilities
            config_text = '\n'.join(config_lines)
            if 'capabilities' not in config_text:
                # Add capabilities parameter before the closing paren
                # Find the last line with closing paren
                last_line_idx = len(config_lines) - 1
                last_line = config_lines[last_line_idx]

                # Get the indentation from a previous line
                indent = ''
                for cl in config_lines[1:]:  # Skip first line
                    if cl.strip() and '=' in cl:
                        indent = cl[:len(cl) - len(cl.lstrip())]
                        break

                if not indent:
                    indent = '    '  # Default 4 spaces

                # Insert capabilities line before closing paren
                cap_line = f'{indent}capabilities = {{"add": ["NET_ADMIN"]}},'

                # Find where to insert: before the last line's closing paren
                if ')' in last_line:
                    # Insert before the closing paren
                    config_lines.insert(last_line_idx, cap_line)
                    modified = True

                result_lines.extend(config_lines)
            else:
                # Already has capabilities, keep as is
                result_lines.extend(config_lines)

            i = j
        else:
            result_lines.append(line)
            i += 1

    return '\n'.join(result_lines), modified


def patch_file(filepath: Path) -> bool:
    """Patch a single Starlark file.

    Args:
        filepath: Path to .star file.

    Returns:
        True if file was modified.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        patched_content, modified = patch_service_config(content)

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(patched_content)
            print(f"  ✓ Patched: {filepath}")
            return True
        else:
            return False

    except Exception as e:
        print(f"  ✗ Error patching {filepath}: {e}")
        return False


def main() -> int:
    """Find and patch all Starlark files."""
    if len(sys.argv) < 2:
        print("Usage: auto_patch_net_admin.py <ethereum-package-dir>")
        return 1

    package_dir = Path(sys.argv[1])
    if not package_dir.exists():
        print(f"Error: Directory not found: {package_dir}")
        return 1

    print(f"Patching ethereum-package at: {package_dir}")
    print()

    patched_count = 0
    skipped_count = 0

    # Find all .star files
    for star_file in package_dir.rglob('*.star'):
        # Skip .git directory
        if '.git' in str(star_file):
            continue

        # Read and check if file has ServiceConfig
        try:
            with open(star_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if 'ServiceConfig(' in content:
                if patch_file(star_file):
                    patched_count += 1
                else:
                    skipped_count += 1
        except Exception:
            continue

    print()
    print(f"Patching complete:")
    print(f"  - {patched_count} files patched")
    print(f"  - {skipped_count} files skipped (already patched or no ServiceConfig)")

    return 0


if __name__ == '__main__':
    sys.exit(main())

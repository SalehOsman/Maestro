#!/usr/bin/env python3
"""Language separation validator for Maestro documentation and metadata.

Checks that:
1. English-only files contain no Arabic characters across all standard Unicode Arabic blocks.
2. Arabic files contain no English prose outside code blocks, inline code,
   URLs, markdown link targets, placeholders, and technical allowlisted terms.

Standard library only. Exits 0 if clean, 1 if violations are found.
"""
import argparse
import os
import re
import sys
from pathlib import Path

ALLOWLIST = {
    "Maestro", "Antigravity", "Claude", "Code", "IDE", "Gemini", "Flash", "High",
    "Python", "Windows", "macOS", "Linux", "Wayland", "X11", "MCP", "TDD", "Google",
    "Anthropic", "MIT", "GitHub", "CLI", "JSON", "PowerShell", "Bash", "Enter",
    "Return", "Accessibility", "Superpowers", "EGM", "AgentShield", "ECC",
    "Harness", "Engineering", "README", "md", "CSV",
}

ENGLISH_FIXED = [
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
]

ENGLISH_DIRS = [
    "docs/en",
    "methodologies",
    "templates",
    "skill",
]

ARABIC_FIXED = [
    "README.ar.md",
]

ARABIC_DIRS = [
    "docs/ar",
]

# Unicode Arabic character ranges across all standard blocks:
# - Arabic: U+0600–U+06FF
# - Arabic Supplement: U+0750–U+077F
# - Arabic Extended-B: U+0870–U+089F
# - Arabic Extended-A: U+08A0–U+08FF
# - Arabic Presentation Forms-A: U+FB50–U+FDFF
# - Arabic Presentation Forms-B: U+FE70–U+FEFC (ends at U+FEFC to exclude BOM U+FEFF)
ARABIC_CHAR_RANGES = (
    r"\u0600-\u06FF"  # Arabic
    r"\u0750-\u077F"  # Arabic Supplement
    r"\u0870-\u089F"  # Arabic Extended-B
    r"\u08A0-\u08FF"  # Arabic Extended-A
    r"\uFB50-\uFDFF"  # Arabic Presentation Forms-A
    r"\uFE70-\uFEFC"  # Arabic Presentation Forms-B
)
ARABIC_CHAR_RE = re.compile(rf"[{ARABIC_CHAR_RANGES}]")
LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`+[^`]*`+")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_TARGET_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL_RE = re.compile(r"https?://\S+")
PLACEHOLDER_RE = re.compile(r"<[^>]+>")


def clean_arabic_line(line, strip_placeholders=True):
    """Strip code, images, links, URLs, and optionally placeholders from line."""
    l = line
    l = IMAGE_RE.sub(" ", l)
    l = LINK_TARGET_RE.sub(r" \1 ", l)
    l = INLINE_CODE_RE.sub(" ", l)
    l = URL_RE.sub(" ", l)
    if strip_placeholders:
        l = PLACEHOLDER_RE.sub(" ", l)
    return l


def check_english_file(path, rel_str):
    violations = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                match = ARABIC_CHAR_RE.search(line)
                if match:
                    ch = match.group(0)
                    violations.append(
                        f"{rel_str}:{line_no}: Arabic character U+{ord(ch):04X} found in English file"
                    )
    except Exception as err:
        violations.append(f"{rel_str}:1: error reading file: {err}")
    return violations


def check_arabic_file(path, rel_str):
    violations = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as err:
        return [f"{rel_str}:1: error reading file: {err}"]

    in_code_block = False
    fence_pattern = None

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        m = FENCE_RE.match(stripped)
        if m:
            curr_fence = m.group(1)[:3]
            if not in_code_block:
                in_code_block = True
                fence_pattern = curr_fence
                continue
            elif fence_pattern == curr_fence:
                in_code_block = False
                fence_pattern = None
                continue
        if in_code_block:
            continue

        l = clean_arabic_line(line, strip_placeholders=True)
        words = LATIN_WORD_RE.findall(l)
        for w in words:
            if w not in ALLOWLIST:
                violations.append(
                    f"{rel_str}:{line_no}: English prose word '{w}' found in Arabic file"
                )
    return violations


def collect_files(root):
    english_files = []
    arabic_files = []

    for name in ENGLISH_FIXED:
        p = root / name
        if p.is_file():
            english_files.append(p)

    for d in ENGLISH_DIRS:
        dp = root / d
        if dp.is_dir():
            for p in sorted(dp.rglob("*")):
                if p.is_file():
                    english_files.append(p)

    for name in ARABIC_FIXED:
        p = root / name
        if p.is_file():
            arabic_files.append(p)

    for d in ARABIC_DIRS:
        dp = root / d
        if dp.is_dir():
            for p in sorted(dp.rglob("*")):
                if p.is_file():
                    arabic_files.append(p)

    return english_files, arabic_files


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Verify language separation across documentation and metadata."
    )
    parser.add_argument(
        "--root",
        default=str(default_root),
        help="Repository root directory to inspect (default: repository root).",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    english_files, arabic_files = collect_files(root)

    violations = []
    for p in english_files:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        violations.extend(check_english_file(p, rel))

    for p in arabic_files:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        violations.extend(check_arabic_file(p, rel))

    if violations:
        for v in violations:
            print(v)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

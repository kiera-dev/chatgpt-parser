#!/usr/bin/env python3

import argparse
import re
from pathlib import Path


def split_by_lines(text, target_lines):
    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = []
    current_lines = 0

    for para in paragraphs:
        para_lines = para.count('\n') + 1
        if current_lines + para_lines > target_lines and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_lines = para_lines
        else:
            current.append(para)
            current_lines += para_lines

    if current:
        chunks.append('\n\n'.join(current))

    return [c for c in chunks if c.strip()]


def split_by_chars(text, target_chars):
    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para)
        if current_size + para_size > target_chars and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_size = para_size
        else:
            current.append(para)
            current_size += para_size + 2  # +2 for \n\n

    if current:
        chunks.append('\n\n'.join(current))

    return [c for c in chunks if c.strip()]


def split_by_headers(text, level=2):
    pattern = r'(?=^#{1,' + str(level) + r'} )'
    sections = re.split(pattern, text, flags=re.MULTILINE)
    return [s.strip() for s in sections if s.strip()]


def write_chunks(chunks, input_path, output_dir=None):
    base = Path(input_path)
    out = Path(output_dir) if output_dir else base.parent
    out.mkdir(parents=True, exist_ok=True)

    total = len(chunks)
    files_written = []

    for i, chunk in enumerate(chunks, start=1):
        filename = f"{base.stem}_part-{i:03}{base.suffix}"
        path = out / filename
        path.write_text(chunk, encoding="utf-8")
        files_written.append(path)

    return files_written


def main():
    parser = argparse.ArgumentParser(
        description="Split a large .txt or .md file into chunks."
    )
    parser.add_argument("input", help="Input file to split")
    parser.add_argument("-o", "--output", help="Output directory (default: same folder as input)")

    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument("--lines", type=int, default=500,
                            help="Target lines per chunk, paragraph-aware (default: 500)")
    size_group.add_argument("--chars", type=int,
                            help="Target characters per chunk, paragraph-aware")
    size_group.add_argument("--split-on-headers", action="store_true",
                            help="Split at Markdown heading boundaries")

    parser.add_argument("--header-level", type=int, default=2,
                        help="Max heading depth for --split-on-headers (default: 2, meaning # and ##)")

    args = parser.parse_args()

    input_path = Path(args.input)
    text = input_path.read_text(encoding="utf-8")

    if args.split_on_headers:
        chunks = split_by_headers(text, level=args.header_level)
        mode = f"headers (level 1–{args.header_level})"
    elif args.chars:
        chunks = split_by_chars(text, args.chars)
        mode = f"{args.chars:,} chars per chunk"
    else:
        chunks = split_by_lines(text, args.lines)
        mode = f"{args.lines} lines per chunk"

    total_lines = text.count('\n') + 1
    total_chars = len(text)

    if len(chunks) <= 1:
        print(f"File fits in one chunk — no splitting needed.")
        print(f"  {total_lines:,} lines  |  {total_chars:,} chars")
        return

    files = write_chunks(chunks, input_path, args.output)

    print(f"Split into {len(files)} chunks ({mode})")
    print(f"  {total_lines:,} lines  |  {total_chars:,} chars  →  {input_path.name}")
    for f in files:
        print(f"  Wrote: {f}")


if __name__ == "__main__":
    main()

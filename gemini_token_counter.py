import json
import argparse
import re
import tiktoken
from pathlib import Path

# Gemini's tokenizer isn't public; cl100k_base is a reasonable approximation
encoding = tiktoken.get_encoding("cl100k_base")


def strip_html(html):
    return re.sub(r"<[^>]+>", "", html).strip()


def count_tokens_in_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    entries = data if isinstance(data, list) else [data]

    total = 0
    for entry in entries:
        if entry.get("header") != "Gemini Apps":
            continue

        # User prompt — stored in title as "Prompted <text>" (may be truncated)
        title = entry.get("title", "")
        if title.startswith("Prompted "):
            prompt_text = title[len("Prompted "):]
            total += len(encoding.encode(prompt_text))

        # Assistant response — stored as HTML, strip tags first
        for item in entry.get("safeHtmlItem", []):
            html = item.get("html", "")
            if html:
                total += len(encoding.encode(strip_html(html)))

    return total


def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in Gemini Takeout MyActivity JSON file(s).",
        epilog="Note: user prompt tokens may be understated — Takeout truncates prompt text in titles.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="JSON file or directory to scan (default: current directory)",
    )
    args = parser.parse_args()

    target = Path(args.path)

    if target.is_dir():
        files = sorted(target.glob("*.json"))
    elif target.is_file():
        files = [target]
    else:
        print(f"Error: {target} is not a file or directory")
        return

    if not files:
        print("No JSON files found.")
        return

    grand_total = 0
    for f in files:
        try:
            tokens = count_tokens_in_file(f)
            print(f"{f.name}: {tokens:,} tokens")
            grand_total += tokens
        except Exception as e:
            print(f"Error with {f.name}: {e}")

    if len(files) > 1:
        print("\n======================")
        print(f"TOTAL TOKENS: {grand_total:,}")
    else:
        print(f"\nTOTAL TOKENS: {grand_total:,}")

    print("\n(Note: user prompt counts are approximate — Takeout truncates prompt titles)")


if __name__ == "__main__":
    main()

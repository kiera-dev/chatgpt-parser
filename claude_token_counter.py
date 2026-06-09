import json
import argparse
import tiktoken
from pathlib import Path

# Claude uses claude-3 family; token counts are approximate using cl100k_base
encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens_in_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    conversations = data if isinstance(data, list) else [data]

    total = 0
    for convo in conversations:
        for msg in convo.get("chat_messages", []):
            if msg.get("sender") not in {"human", "assistant"}:
                continue
            text = msg.get("text", "")
            if text:
                total += len(encoding.encode(text))

    return total


def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in Claude export JSON file(s)."
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


if __name__ == "__main__":
    main()

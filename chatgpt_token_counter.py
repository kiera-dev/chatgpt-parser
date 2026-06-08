import json
import glob
import argparse
import tiktoken
from pathlib import Path

encoding = tiktoken.encoding_for_model("gpt-4o")


def get_message_text(message):
    content = message.get("content", {})
    ctype = content.get("content_type")

    if ctype == "text":
        return "\n".join(p for p in content.get("parts", []) if isinstance(p, str)).strip()

    if ctype == "code":
        return content.get("text", "").strip()

    return ""


def count_tokens_in_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"), strict=False)

    # Handle both a single conversation dict and a list of conversations
    conversations = data if isinstance(data, list) else [data]

    total = 0
    for convo in conversations:
        mapping = convo.get("mapping", {})
        for node in mapping.values():
            msg = node.get("message")
            if not msg:
                continue
            role = msg.get("author", {}).get("role", "")
            if role not in {"user", "assistant"}:
                continue
            text = get_message_text(msg)
            if text:
                total += len(encoding.encode(text))

    return total


def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in ChatGPT export JSON file(s)."
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

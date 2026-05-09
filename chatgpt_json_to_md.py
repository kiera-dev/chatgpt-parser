#!/usr/bin/env python3

import json
import argparse
from datetime import datetime
from pathlib import Path


def ts_to_local(ts):
    if not ts:
        return "NO_TIMESTAMP"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def get_message_text(message):
    content = message.get("content", {})
    ctype = content.get("content_type")

    if ctype == "text":
        return "\n".join(content.get("parts", [])).strip()

    if ctype == "code":
        lang = content.get("language") or ""
        text = content.get("text", "")
        return f"```{lang}\n{text}\n```".strip()

    return ""


def extract_visible_chain(data):
    mapping = data.get("mapping", {})
    current = data.get("current_node")

    if not current:
        # fallback: find a leaf node
        children = {child for node in mapping.values() for child in node.get("children", [])}
        possible_leaves = [node_id for node_id in mapping if node_id not in children]
        current = possible_leaves[-1] if possible_leaves else None

    chain = []

    while current:
        node = mapping.get(current)
        if not node:
            break
        chain.append(node)
        current = node.get("parent")

    chain.reverse()
    return chain


def convert(input_path, output_path, include_tools=False, include_hidden=False):
    data = json.loads(
    Path(input_path).read_text(encoding="utf-8"),
    strict=False
)

    title = data.get("title", "Untitled Chat")
    created = ts_to_local(data.get("create_time"))
    updated = ts_to_local(data.get("update_time"))

    lines = [
        f"# {title}",
        "",
        f"Created: {created}",
        f"Updated: {updated}",
        "",
    ]

    chain = extract_visible_chain(data)

    count = 0

    for node in chain:
        msg = node.get("message")
        if not msg:
            continue

        metadata = msg.get("metadata", {})
        if metadata.get("is_visually_hidden_from_conversation") and not include_hidden:
            continue

        role = msg.get("author", {}).get("role", "unknown")

        if role not in {"user", "assistant"}:
            if not include_tools:
                continue

        text = get_message_text(msg)

        attachments = metadata.get("attachments", [])
        attachment_lines = []
        for att in attachments:
            name = att.get("name", "unnamed attachment")
            attachment_lines.append(f"[Attachment: {name}]")

        if not text and not attachment_lines:
            continue

        count += 1
        timestamp = ts_to_local(msg.get("create_time"))
        label = role.upper()

        lines.append(f"--- {label} {count} | {timestamp} ---")
        lines.append("")

        if attachment_lines:
            lines.extend(attachment_lines)
            lines.append("")

        if text:
            lines.append(text)
            lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")

    print(f"Exported {count} messages")
    print(f"Wrote: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert ChatGPT conversation JSON to clean Markdown."
    )
    parser.add_argument("input", help="Input ChatGPT JSON file")
    parser.add_argument("-o", "--output", help="Output Markdown file")
    parser.add_argument("--include-tools", action="store_true", help="Include tool/system messages")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden messages")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = args.output or input_path.with_suffix(".md")

    convert(
        input_path=input_path,
        output_path=output_path,
        include_tools=args.include_tools,
        include_hidden=args.include_hidden,
    )


if __name__ == "__main__":
    main()

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


def extract_messages(data, include_tools=False, include_hidden=False):
    messages = []

    for node in extract_visible_chain(data):
        msg = node.get("message")
        if not msg:
            continue

        metadata = msg.get("metadata", {}) or {}
        if metadata.get("is_visually_hidden_from_conversation") and not include_hidden:
            continue

        role = msg.get("author", {}).get("role", "unknown")
        if role not in {"user", "assistant"}:
            if not include_tools:
                continue

        text = get_message_text(msg)

        attachment_lines = []
        for att in metadata.get("attachments", []) or []:
            name = att.get("name") or att.get("id") or "unnamed attachment"
            attachment_lines.append(f"[Attachment: {name}]")

        if not text and not attachment_lines:
            continue

        messages.append({
            "role": role.upper(),
            "timestamp": ts_to_local(msg.get("create_time")),
            "text": text,
            "attachments": attachment_lines,
        })

    return messages


def render_markdown(data, messages, start_index=1):
    title = data.get("title", "Untitled Chat")
    created = ts_to_local(data.get("create_time"))
    updated = ts_to_local(data.get("update_time"))
    convo_id = data.get("conversation_id") or data.get("id") or "UNKNOWN"

    lines = [
        f"# {title}",
        "",
        f"Created: {created}",
        f"Updated: {updated}",
        f"Conversation ID: {convo_id}",
        "",
    ]

    for i, msg in enumerate(messages, start=start_index):
        lines.append(f"--- {msg['role']} {i} | {msg['timestamp']} ---")
        lines.append("")

        if msg["attachments"]:
            lines.extend(msg["attachments"])
            lines.append("")

        if msg["text"]:
            lines.append(msg["text"])
            lines.append("")

    return "\n".join(lines)


def convert(input_path, output_path, include_tools=False, include_hidden=False, chunk_size=None):
    data = json.loads(Path(input_path).read_text(encoding="utf-8"), strict=False)

    messages = extract_messages(data, include_tools, include_hidden)
    title = data.get("title", "Untitled Chat")
    convo_id = data.get("conversation_id") or data.get("id") or "unknown-id"
    base = Path(output_path).with_suffix("")

    if chunk_size and len(messages) > chunk_size:
        files_written = []
        for part_num, start in enumerate(range(0, len(messages), chunk_size), start=1):
            chunk = messages[start:start + chunk_size]
            path = Path(f"{base}_part-{part_num:03}.md")

            header = [
                f"# {title} — Part {part_num}",
                "",
                f"Conversation ID: {convo_id}",
                f"Messages: {start + 1}–{start + len(chunk)} of {len(messages)}",
                "",
            ]

            body = render_markdown(data, chunk, start_index=start + 1)
            path.write_text("\n".join(header) + "\n" + body, encoding="utf-8")
            files_written.append(path)

        print(f"Exported {len(messages)} messages across {len(files_written)} files")
        for f in files_written:
            print(f"Wrote: {f}")
        return

    Path(output_path).write_text(render_markdown(data, messages), encoding="utf-8")
    print(f"Exported {len(messages)} messages")
    print(f"Wrote: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert ChatGPT conversation JSON to clean Markdown."
    )
    parser.add_argument("input", help="Input ChatGPT JSON file")
    parser.add_argument("-o", "--output", help="Output Markdown file")
    parser.add_argument("--chunk-size", type=int, default=200, help="Messages per chunk for large conversations (default: 200)")
    parser.add_argument("--no-chunk", action="store_true", help="Do not split large conversations")
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
        chunk_size=None if args.no_chunk else args.chunk_size,
    )


if __name__ == "__main__":
    main()

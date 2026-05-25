#!/usr/bin/env python3

import json
import argparse
import re
from datetime import datetime
from pathlib import Path


def ts_to_local(ts):
    if not ts:
        return "NO_TIMESTAMP"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def slugify(text):
    text = text or "untitled-chat"
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "untitled-chat"


def get_message_text(message):
    content = message.get("content", {})
    ctype = content.get("content_type")

    if ctype == "text":
        return "\n".join(content.get("parts", [])).strip()

    if ctype == "multimodal_text":
        parts = content.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if part.get("content_type") == "image_asset_pointer":
                    text_parts.append("[Image attachment]")
        return "\n".join(text_parts).strip()

    if ctype == "code":
        lang = content.get("language") or ""
        text = content.get("text", "")
        return f"```{lang}\n{text}\n```".strip()

    return ""


def extract_chain(data):
    mapping = data.get("mapping", {})
    current = data.get("current_node")

    if not current:
        children = {child for node in mapping.values() for child in node.get("children", [])}
        leaves = [node_id for node_id in mapping if node_id not in children]
        current = leaves[-1] if leaves else None

    chain = []
    while current:
        node = mapping.get(current)
        if not node:
            break
        chain.append(node)
        current = node.get("parent")

    return list(reversed(chain))


def extract_messages(convo, include_tools=False, include_hidden=False):
    messages = []

    for node in extract_chain(convo):
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


def render_markdown(convo, messages, start_index=1):
    title = convo.get("title", "Untitled Chat")
    created = ts_to_local(convo.get("create_time"))
    updated = ts_to_local(convo.get("update_time"))

    lines = [
        f"# {title}",
        "",
        f"Created: {created}",
        f"Updated: {updated}",
        f"Conversation ID: {convo.get('conversation_id') or convo.get('id') or 'UNKNOWN'}",
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


def write_conversation(convo, output_dir, chunk_size, include_tools, include_hidden):
    title = convo.get("title", "Untitled Chat")
    slug = slugify(title)
    convo_id = convo.get("conversation_id") or convo.get("id") or "unknown-id"

    messages = extract_messages(convo, include_tools, include_hidden)

    if not messages:
        return None

    if chunk_size and len(messages) > chunk_size:
        parts = []
        for part_num, start in enumerate(range(0, len(messages), chunk_size), start=1):
            chunk = messages[start:start + chunk_size]
            filename = f"{slug}_part-{part_num:03}.md"
            path = output_dir / filename

            header = [
                f"# {title} — Part {part_num}",
                "",
                f"Conversation ID: {convo_id}",
                f"Messages: {start + 1}–{start + len(chunk)} of {len(messages)}",
                "",
            ]

            body = render_markdown(convo, chunk, start_index=start + 1)
            path.write_text("\n".join(header) + "\n" + body, encoding="utf-8")
            parts.append(filename)

        return {
            "title": title,
            "slug": slug,
            "messages": len(messages),
            "files": parts,
        }

    filename = f"{slug}.md"
    path = output_dir / filename
    path.write_text(render_markdown(convo, messages), encoding="utf-8")

    return {
        "title": title,
        "slug": slug,
        "messages": len(messages),
        "files": [filename],
    }


def write_index(output_dir, records):
    lines = [
        "# ChatGPT Export Index",
        "",
        f"Conversations exported: {len(records)}",
        "",
    ]

    for record in sorted(records, key=lambda r: r["title"].lower()):
        lines.append(f"## {record['title']}")
        lines.append("")
        lines.append(f"- Messages: {record['messages']}")
        lines.append(f"- Files:")
        for file in record["files"]:
            lines.append(f"  - [{file}]({file})")
        lines.append("")

    (output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def convert(input_path, output=None, chunk_size=None, include_tools=False, include_hidden=False):
    raw = Path(input_path).read_text(encoding="utf-8")
    data = json.loads(raw, strict=False)

    # Big export: list of conversations
    if isinstance(data, list):
        output_dir = Path(output or "chatgpt_md_export")
        output_dir.mkdir(exist_ok=True)

        records = []
        for convo in data:
            record = write_conversation(
                convo=convo,
                output_dir=output_dir,
                chunk_size=chunk_size,
                include_tools=include_tools,
                include_hidden=include_hidden,
            )
            if record:
                records.append(record)

        write_index(output_dir, records)

        print(f"✅ Done! Exported {len(records)} conversations to {output_dir}/")
        print(f"📄 Index: {output_dir / 'index.md'}")
        return

    # Single conversation
    messages = extract_messages(data, include_tools, include_hidden)
    output_path = Path(output) if output else Path(input_path).with_suffix(".md")
    output_path.write_text(render_markdown(data, messages), encoding="utf-8")

    print(f"✅ Done! {len(messages)} messages written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert ChatGPT conversation JSON to Markdown."
    )
    parser.add_argument("input", help="Input ChatGPT JSON file")
    parser.add_argument("-o", "--output", help="Output file or folder")
    parser.add_argument("--chunk-size", type=int, default=200, help="Messages per chunk for large conversations")
    parser.add_argument("--no-chunk", action="store_true", help="Do not split large conversations")
    parser.add_argument("--include-tools", action="store_true", help="Include tool/system messages")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden messages")

    args = parser.parse_args()

    convert(
        input_path=args.input,
        output=args.output,
        chunk_size=None if args.no_chunk else args.chunk_size,
        include_tools=args.include_tools,
        include_hidden=args.include_hidden,
    )


if __name__ == "__main__":
    main()
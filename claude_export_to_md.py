#!/usr/bin/env python3

import json
import argparse
import re
from datetime import datetime
from pathlib import Path


def ts_to_local(ts_str):
    if not ts_str:
        return "NO_TIMESTAMP"
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(ts_str)


def slugify(text):
    text = text or "untitled-conversation"
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "untitled-conversation"


def get_message_text(message, include_tools=False, include_thinking=False):
    content_blocks = message.get("content", []) or []
    parts = []

    for block in content_blocks:
        btype = block.get("type")

        if btype == "text":
            text = block.get("text", "").strip()
            if text:
                parts.append(text)

        elif btype == "thinking" and include_thinking:
            thinking = block.get("thinking", "").strip()
            if thinking:
                parts.append(f"<thinking>\n{thinking}\n</thinking>")

        elif btype == "tool_use" and include_tools:
            name = block.get("name", "unknown")
            inp = block.get("input", {})
            inp_str = json.dumps(inp, indent=2)
            parts.append(f"[Tool call: {name}]\n```json\n{inp_str}\n```")

        elif btype == "tool_result" and include_tools:
            inner = block.get("content", [])
            result_parts = []
            for item in inner:
                if isinstance(item, dict) and item.get("type") == "text":
                    result_parts.append(item.get("text", "").strip())
                elif isinstance(item, str):
                    result_parts.append(item.strip())
            result_text = "\n".join(result_parts).strip()
            if result_text:
                parts.append(f"[Tool result]\n{result_text}")

    if parts:
        return "\n\n".join(parts)

    # Fallback to top-level text field
    return message.get("text", "").strip()


def extract_messages(convo, include_tools=False, include_thinking=False):
    messages = []

    for msg in convo.get("chat_messages", []) or []:
        sender = msg.get("sender", "unknown")
        label = "USER" if sender == "human" else sender.upper()

        text = get_message_text(msg, include_tools=include_tools, include_thinking=include_thinking)

        attachment_lines = []
        for att in msg.get("attachments", []) or []:
            name = att.get("file_name") or att.get("name") or att.get("id") or "unnamed attachment"
            attachment_lines.append(f"[Attachment: {name}]")
        for f in msg.get("files", []) or []:
            name = f.get("file_name") or f.get("name") or f.get("id") or "unnamed file"
            attachment_lines.append(f"[File: {name}]")

        if not text and not attachment_lines:
            continue

        messages.append({
            "role": label,
            "timestamp": ts_to_local(msg.get("created_at")),
            "text": text,
            "attachments": attachment_lines,
        })

    return messages


def render_markdown(convo, messages, start_index=1):
    title = convo.get("name", "Untitled Conversation")
    created = ts_to_local(convo.get("created_at"))
    updated = ts_to_local(convo.get("updated_at"))
    convo_id = convo.get("uuid", "UNKNOWN")

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


def write_conversation(convo, output_dir, chunk_size, include_tools, include_thinking):
    title = convo.get("name", "Untitled Conversation")
    slug = slugify(title)
    convo_id = convo.get("uuid", "unknown-id")

    messages = extract_messages(convo, include_tools, include_thinking)

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
        "# Claude Export Index",
        "",
        f"Conversations exported: {len(records)}",
        "",
    ]

    for record in sorted(records, key=lambda r: r["title"].lower()):
        lines.append(f"## {record['title']}")
        lines.append("")
        lines.append(f"- Messages: {record['messages']}")
        lines.append("- Files:")
        for file in record["files"]:
            lines.append(f"  - [{file}]({file})")
        lines.append("")

    (output_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def convert(input_path, output=None, chunk_size=None, include_tools=False, include_thinking=False):
    raw = Path(input_path).read_text(encoding="utf-8")
    data = json.loads(raw, strict=False)

    # Unwrap {"conversations": [...]} envelope from full Claude export
    if isinstance(data, dict) and "conversations" in data:
        data = data["conversations"]

    # Bulk export: list of conversations
    if isinstance(data, list):
        output_dir = Path(output or "claude_md_export")
        output_dir.mkdir(exist_ok=True)

        records = []
        for convo in data:
            record = write_conversation(
                convo=convo,
                output_dir=output_dir,
                chunk_size=chunk_size,
                include_tools=include_tools,
                include_thinking=include_thinking,
            )
            if record:
                records.append(record)

        write_index(output_dir, records)

        print(f"Done! Exported {len(records)} conversations to {output_dir}/")
        print(f"Index: {output_dir / 'index.md'}")
        return

    # Single conversation object
    messages = extract_messages(data, include_tools, include_thinking)
    output_path = Path(output) if output else Path(input_path).with_suffix(".md")
    output_path.write_text(render_markdown(data, messages), encoding="utf-8")

    print(f"Done! {len(messages)} messages written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Claude.ai exported JSON to Markdown."
    )
    parser.add_argument("input", help="Input Claude JSON file (single conversation or full export)")
    parser.add_argument("-o", "--output", help="Output file or folder")
    parser.add_argument("--chunk-size", type=int, default=200, help="Messages per chunk for large conversations (default: 200)")
    parser.add_argument("--no-chunk", action="store_true", help="Do not split large conversations")
    parser.add_argument("--include-tools", action="store_true", help="Include tool use/result blocks")
    parser.add_argument("--include-thinking", action="store_true", help="Include extended thinking blocks")

    args = parser.parse_args()

    convert(
        input_path=args.input,
        output=args.output,
        chunk_size=None if args.no_chunk else args.chunk_size,
        include_tools=args.include_tools,
        include_thinking=args.include_thinking,
    )


if __name__ == "__main__":
    main()

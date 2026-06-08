#!/usr/bin/env python3

import json
import argparse
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


def extract_messages(data, include_tools=False, include_thinking=False):
    messages = []

    for msg in data.get("chat_messages", []) or []:
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


def render_markdown(data, messages, start_index=1):
    title = data.get("name", "Untitled Conversation")
    created = ts_to_local(data.get("created_at"))
    updated = ts_to_local(data.get("updated_at"))
    convo_id = data.get("uuid", "UNKNOWN")

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


def convert(input_path, output_path, include_tools=False, include_thinking=False, chunk_size=None):
    data = json.loads(Path(input_path).read_text(encoding="utf-8"), strict=False)

    messages = extract_messages(data, include_tools, include_thinking)
    title = data.get("name", "Untitled Conversation")
    convo_id = data.get("uuid", "unknown-id")
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
        description="Convert a Claude.ai conversation JSON to clean Markdown."
    )
    parser.add_argument("input", help="Input Claude conversation JSON file")
    parser.add_argument("-o", "--output", help="Output Markdown file")
    parser.add_argument("--chunk-size", type=int, default=200, help="Messages per chunk for large conversations (default: 200)")
    parser.add_argument("--no-chunk", action="store_true", help="Do not split large conversations")
    parser.add_argument("--include-tools", action="store_true", help="Include tool use/result blocks")
    parser.add_argument("--include-thinking", action="store_true", help="Include extended thinking blocks")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = args.output or input_path.with_suffix(".md")

    convert(
        input_path=input_path,
        output_path=output_path,
        include_tools=args.include_tools,
        include_thinking=args.include_thinking,
        chunk_size=None if args.no_chunk else args.chunk_size,
    )


if __name__ == "__main__":
    main()

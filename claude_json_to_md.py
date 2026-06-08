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


def convert(input_path, output_path, include_tools=False, include_thinking=False):
    data = json.loads(Path(input_path).read_text(encoding="utf-8"), strict=False)

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

    chat_messages = data.get("chat_messages", []) or []
    count = 0

    for msg in chat_messages:
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

        count += 1
        timestamp = ts_to_local(msg.get("created_at"))

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
        description="Convert a Claude.ai conversation JSON to clean Markdown."
    )
    parser.add_argument("input", help="Input Claude conversation JSON file")
    parser.add_argument("-o", "--output", help="Output Markdown file")
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
    )


if __name__ == "__main__":
    main()

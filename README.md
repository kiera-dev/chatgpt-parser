# ChatGPT & Claude JSON to Markdown

Convert exported ChatGPT or Claude.ai conversation JSON files into clean, readable Markdown. Built for preserving long conversations and carrying context between threads.

These scripts parse the official export formats and reconstruct the visible conversation chain, including:

- User messages
- Assistant responses
- Timestamps
- Attachments
- Optional tool/thinking messages

Perfect for:
- Uploading cleaned context back into a new thread or project source file
- Archiving conversations
- Creating searchable notes
- Personal knowledge management
- Avoiding broken PDF exports / print issues

---

## Features

- Converts ChatGPT and Claude.ai JSON → clean Markdown
- Preserves conversation order
- Includes timestamps
- Handles attachments
- UTF-8 safe
- Supports single conversation JSON files and full exports
- Automatically splits large conversations into chunks
- Generates an index.md for bulk exports

---

## Why This Exists

AI threads eventually become too long, difficult to search, unstable to print, or hit context limits. These scripts convert exported JSON files into clean Markdown that can be uploaded into new threads, searched locally, archived, or used as continuity files.

## Example Output

```md
# <Conversation Title>

Created: 2026-05-08 22:39:32
Updated: 2026-05-09 10:05:14
Conversation ID: abc123

--- USER 1 | 2026-05-08 22:39:37 ---

hey buddy, i’m kicking off a new thread...

--- ASSISTANT 2 | 2026-05-08 22:39:49 ---

I’ll pull from the project files now...
```

---

## Requirements

- Python 3.9+
- No external dependencies

---

## ChatGPT Usage

### Single Conversation JSON:

```bash
python3 chatgpt_json_to_md.py conversation.json
python3 chatgpt_json_to_md.py conversation.json -o output.md
python3 chatgpt_json_to_md.py conversation.json --include-tools --include-hidden
```

### Full Export:
```bash
python3 chatgpt_export_to_md.py conversations.json
```
Creates:
```
chatgpt_md_export/
  index.md
  thread-name.md
  giant-thread_part-001.md
```

Options:
```bash
python3 chatgpt_export_to_md.py conversations.json --chunk-size 500
python3 chatgpt_export_to_md.py conversations.json --no-chunk
python3 chatgpt_export_to_md.py conversations.json --include-tools --include-hidden
```

### Getting Your ChatGPT JSON

In ChatGPT: **Settings > Data Controls > Export Data**

You’ll receive a ZIP containing your conversations as JSON.

---

## Claude Usage

### Single Conversation JSON:

```bash
python3 claude_json_to_md.py conversation.json
python3 claude_json_to_md.py conversation.json -o output.md
python3 claude_json_to_md.py conversation.json --include-tools --include-thinking
```

### Full Export:
```bash
python3 claude_export_to_md.py conversations.json
```
Creates:
```
claude_md_export/
  index.md
  thread-name.md
  giant-thread_part-001.md
```

Options:
```bash
python3 claude_export_to_md.py conversations.json --chunk-size 500
python3 claude_export_to_md.py conversations.json --no-chunk
python3 claude_export_to_md.py conversations.json --include-tools --include-thinking
```

`--include-tools` shows tool use/result blocks (function calls and responses).
`--include-thinking` shows extended thinking blocks (Claude’s internal reasoning, when available).

### Getting Your Claude JSON

In Claude.ai: **Settings > Privacy > Export Data**

You’ll receive a file containing your conversations as JSON.

---


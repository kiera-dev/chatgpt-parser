# ChatGPT JSON to Markdown

Convert exported ChatGPT conversation JSON files into clean, readable Markdown.

This script parses the official ChatGPT conversation export format and reconstructs the visible conversation chain, including:

- User messages
- Assistant responses
- Timestamps
- Attachments
- Optional hidden/tool messages

Perfect for:
- Uploading cleaned context back into ChatGPT in chats or as a project source file.
- Archiving conversations
- Creating searchable notes
- Personal knowledge management
- Avoiding broken PDF exports / print issues

---

## Features

- Converts ChatGPT JSON → clean Markdown
- Preserves conversation order
- Includes timestamps
- Handles attachments
- UTF-8 safe
- Handles malformed JSON exports using `strict=False`
- Optional inclusion of hidden/system/tool messages

---

## Example Output

```md
# <Conversation Title>

Created: 2026-05-08 22:39:32
Updated: 2026-05-09 10:05:14

--- USER 1 | 2026-05-08 22:39:37 ---

hey buddy, i'm kicking off a new thread...

--- ASSISTANT 2 | 2026-05-08 22:39:49 ---

I’ll pull from the project files now...
```

---

## Requirements

- Python 3.9+
- No external dependencies

---

## Usage

Basic usage:

```bash
python3 chatgpt_json_to_md.py conversation.json
```

Output:

```txt
conversation.md
```

Specify output file:

```bash
python3 chatgpt_json_to_md.py conversation.json -o output.md
```

Include hidden/system/tool messages:

```bash
python3 chatgpt_json_to_md.py conversation.json --include-tools --include-hidden
```

---

## Getting Your ChatGPT JSON

### Option 1 — Export Your Data

In ChatGPT:

- Settings > Data Controls > Export Data

You’ll receive a ZIP containing your conversations as JSON.

### Option 2 — Browser DevTools / DOM Export

Extract conversation JSON manually using browser DevTools.

---

## Why This Exists

This tool was created to preserve long ChatGPT conversations and carry context between threads.

ChatGPT threads eventually become:
- too long
- difficult to search
- unstable to print/export
- or hit context limits

This script converts exported ChatGPT JSON files into clean Markdown files that can be:
- uploaded into new ChatGPT threads/project source files 
- searched locally
- archived
- summarized
- used as continuity/context files

The original goal was simple: Keep long-running conversations and project context portable between threads.

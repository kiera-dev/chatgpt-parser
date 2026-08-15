# ChatGPT & Claude JSON to Text

Convert exported ChatGPT or Claude.ai conversation JSON files into clean, readable text. Built for preserving long conversations and carrying context between threads.

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

- Converts ChatGPT and Claude.ai JSON → clean text
- Outputs `.txt` (default) or `.md` via `--format`
- Preserves conversation order
- Includes timestamps
- Handles attachments
- UTF-8 safe
- Supports single conversation JSON files and full exports
- Automatically splits large conversations into chunks
- Generates an index file for bulk exports
- Includes `chunker.py` for splitting text files you already have

---

## Why This Exists

AI threads eventually become too long, difficult to search, unstable to print, or hit context limits. These scripts convert exported JSON files into clean text that can be uploaded into new threads, searched locally, archived, or used as continuity files.

## Output Format

Output defaults to `.txt`. Pass `--format md` for `.md` instead.

The file contents are identical either way — the same headers and `--- USER 1 | ... ---`
separators are used in both. Only the extension changes. Those separators are what make a
long transcript navigable, so they are kept in plain-text mode too.

```
# <Conversation Title>

Created: 2026-05-08 22:39:32
Updated: 2026-05-09 10:05:14
Conversation ID: abc123

--- USER 1 | 2026-05-08 22:39:37 ---

hey buddy, i'm kicking off a new thread...

--- ASSISTANT 2 | 2026-05-08 22:39:49 ---

I'll pull from the project files now...
```

---

## Requirements

- Python 3.9+
- **Command-line scripts:** no external dependencies, standard library only
- **GUI (`gui.py`):** additionally needs a Python built with working
  Tkinter/Tcl-Tk support (see [GUI](#gui) below)

---

## GUI

If you would rather not use the command line, `gui.py` puts a window around the
same converters:

```bash
python3 gui.py
```

Pick an export file and it works out on its own whether it came from ChatGPT or
Claude. The **Convert JSON** tab covers everything the parser scripts do (format,
splitting, tool/hidden/thinking messages); the **Split a file** tab wraps
`chunker.py` for text files you already have.

### Tkinter

The GUI needs Tkinter. Whether you already have it depends on how your Python was
installed, not just which OS you are on. To check any interpreter:

```bash
python -m tkinter
```

That opens a small test window if Tkinter is working. If it fails:

| How Python was installed | What to do |
| --- | --- |
| Debian/Ubuntu system Python | `sudo apt install python3-tk` |
| Fedora system Python | `sudo dnf install python3-tkinter` |
| python.org installer (macOS/Windows) | Tkinter is bundled; reinstalling Python restores it |
| pyenv or Homebrew (macOS or Linux) | Install Tk **first**, then rebuild Python |

The pyenv/Homebrew case catches people out: Python links against Tcl-Tk when it
is compiled, so installing Tk afterwards does not fix an interpreter that was
already built without it. Install Tk, then rebuild:

```bash
brew install tcl-tk
pyenv uninstall 3.11.15 && pyenv install 3.11.15   # use your own version
```

The command-line scripts work with or without Tkinter.

---

## ChatGPT Usage

### Single Conversation JSON:

```bash
python3 chatgpt_json_to_text.py conversation.json                    # → conversation.txt
python3 chatgpt_json_to_text.py conversation.json --format md        # → conversation.md
python3 chatgpt_json_to_text.py conversation.json -o output.md       # -o wins over --format
python3 chatgpt_json_to_text.py conversation.json --include-tools --include-hidden
```

### Full Export:
```bash
python3 chatgpt_export_to_text.py conversations.json
```
Creates:
```
chatgpt_text_export/
  index.txt
  thread-name.txt
  giant-thread_part-001.txt
```

Options:
```bash
python3 chatgpt_export_to_text.py conversations.json --format md
python3 chatgpt_export_to_text.py conversations.json --chunk-size 500
python3 chatgpt_export_to_text.py conversations.json --no-chunk
python3 chatgpt_export_to_text.py conversations.json --include-tools --include-hidden
```

### Getting Your ChatGPT JSON

In ChatGPT: **Settings > Data Controls > Export Data**

You'll receive a ZIP containing your conversations as JSON.

---

## Claude Usage

### Single Conversation JSON:

```bash
python3 claude_json_to_text.py conversation.json                     # → conversation.txt
python3 claude_json_to_text.py conversation.json --format md         # → conversation.md
python3 claude_json_to_text.py conversation.json -o output.md
python3 claude_json_to_text.py conversation.json --include-tools --include-thinking
```

### Full Export:
```bash
python3 claude_export_to_text.py conversations.json
```
Creates:
```
claude_text_export/
  index.txt
  thread-name.txt
  giant-thread_part-001.txt
```

Options:
```bash
python3 claude_export_to_text.py conversations.json --format md
python3 claude_export_to_text.py conversations.json --chunk-size 500
python3 claude_export_to_text.py conversations.json --no-chunk
python3 claude_export_to_text.py conversations.json --include-tools --include-thinking
```

`--include-tools` shows tool use/result blocks (function calls and responses).
`--include-thinking` shows extended thinking blocks (Claude's internal reasoning, when available).

### Getting Your Claude JSON

In Claude.ai: **Settings > Privacy > Export Data**

You'll receive a file containing your conversations as JSON.

---

## Chunking Existing Files

`chunker.py` splits a `.txt` or `.md` file you already have. It never cuts mid-paragraph —
it waits for the next blank line to break.

```bash
python3 chunker.py bigfile.txt                       # 500 lines per chunk
python3 chunker.py bigfile.txt --lines 200
python3 chunker.py bigfile.txt --chars 50000         # useful for token budgeting
python3 chunker.py bigfile.md --split-on-headers     # split at # and ## boundaries
python3 chunker.py bigfile.md --split-on-headers --header-level 1
python3 chunker.py bigfile.txt -o chunks/            # custom output folder
```

By default the chunks keep the input file's extension. Use `--format` to change it —
this is also how you convert an existing `.md` file to `.txt`:

```bash
python3 chunker.py notes.md --format txt
```

---

#!/usr/bin/env python3
"""Desktop GUI for the ChatGPT / Claude conversation parsers.

Wraps the same converters the command-line scripts use, so behaviour is
identical -- this only puts a window around them. Requires tkinter; see main()
if your Python was built without it.
"""

import contextlib
import io
import json
import queue
import threading
import traceback
from pathlib import Path

import chatgpt_export_to_text as chatgpt_export
import chatgpt_json_to_text as chatgpt_single
import chunker
import claude_export_to_text as claude_export
import claude_json_to_text as claude_single

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False


PLATFORMS = ["Auto-detect", "ChatGPT", "Claude"]

# Structural keys unique to each export format. Whichever appears first in the
# file wins, so a stray mention inside message text can't outvote the real one.
MARKERS = (
    ('"mapping"', "chatgpt"),
    ('"current_node"', "chatgpt"),
    ('"chat_messages"', "claude"),
    ('"conversations"', "claude"),
)

DEFAULT_LINES = "500"
DEFAULT_CHARS = "50000"


def sniff_platform(path, limit=65536):
    """Guess the service from the first chunk of the file.

    Full exports run to hundreds of megabytes, so this reads a bounded prefix
    instead of parsing the whole document -- cheap enough to call on the UI
    thread. Returns 'chatgpt', 'claude', or None if the prefix is inconclusive.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(limit)
    except OSError:
        return None

    hits = {}
    for needle, platform in MARKERS:
        found = head.find(needle)
        if found != -1:
            hits[found] = platform
    return hits[min(hits)] if hits else None


def detect_platform(path):
    """Authoritative detection: parses the whole file. Slow on big exports."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"), strict=False)
    except (OSError, ValueError):
        return None

    if isinstance(data, dict) and "conversations" in data:
        return "claude"
    if isinstance(data, list):
        data = data[0] if data else {}

    if not isinstance(data, dict):
        return None
    if "mapping" in data:
        return "chatgpt"
    if "chat_messages" in data:
        return "claude"
    return None


def is_bulk_export(data):
    """True when the JSON holds many conversations rather than one."""
    if isinstance(data, dict) and "conversations" in data:
        return True
    return isinstance(data, list)


def _conversation_name(data, platform, input_path):
    """Filename stem for a single conversation, matching the export scripts."""
    title = data.get("title") if platform == "chatgpt" else data.get("name")
    if not title:
        return Path(input_path).stem
    slugify = chatgpt_export.slugify if platform == "chatgpt" else claude_export.slugify
    return slugify(title)


def resolve_output(output, data, platform, input_path, ext):
    """Work out where a single conversation should be written.

    The GUI's "Save to" box is always a folder, but the single-conversation
    converters expect a full filename -- handing them a directory raises
    IsADirectoryError. Build the filename here. A path typed by hand that
    isn't a directory is taken as the filename the user wants.
    """
    if not output:
        return Path(input_path).with_suffix(ext)
    target = Path(output)
    if target.is_dir():
        return target / f"{_conversation_name(data, platform, input_path)}{ext}"
    return target


def run_conversion(input_path, platform=None, output=None, fmt="txt", chunk_size=200,
                   include_tools=False, include_hidden=False, include_thinking=False):
    """Convert an export. Returns whatever the underlying script printed.

    Called on a worker thread, so detection and parsing here are free to be
    slow. Pass platform=None to detect it.
    """
    data = json.loads(Path(input_path).read_text(encoding="utf-8"), strict=False)

    if platform is None:
        platform = detect_platform(input_path)
        if platform is None:
            raise ValueError(
                "Couldn't tell whether this is a ChatGPT or Claude export. "
                "Choose one under Service and try again."
            )

    ext = f".{fmt}"
    is_chatgpt = platform == "chatgpt"
    buffer = io.StringIO()

    if is_bulk_export(data):
        module = chatgpt_export if is_chatgpt else claude_export
        kwargs = {
            "input_path": input_path,
            "output": output or None,
            "chunk_size": chunk_size,
            "include_tools": include_tools,
            "ext": ext,
        }
    else:
        # The export scripts ignore chunk_size for a lone conversation; the
        # single-conversation scripts honour it, so route there instead.
        module = chatgpt_single if is_chatgpt else claude_single
        kwargs = {
            "input_path": input_path,
            "output_path": resolve_output(output, data, platform, input_path, ext),
            "chunk_size": chunk_size,
            "include_tools": include_tools,
        }

    if is_chatgpt:
        kwargs["include_hidden"] = include_hidden
    else:
        kwargs["include_thinking"] = include_thinking

    with contextlib.redirect_stdout(buffer):
        module.convert(**kwargs)
    return buffer.getvalue()


def run_chunker(input_path, mode="lines", size=500, header_level=2, output=None, fmt=None):
    """Split an existing .txt/.md file. Returns a summary string."""
    text = Path(input_path).read_text(encoding="utf-8")

    if mode == "headers":
        chunks = chunker.split_by_headers(text, level=header_level)
    elif mode == "chars":
        chunks = chunker.split_by_chars(text, size)
    else:
        chunks = chunker.split_by_lines(text, size)

    if len(chunks) <= 1:
        return "File fits in one chunk - nothing written."

    files = chunker.write_chunks(chunks, input_path, output or None,
                                 ext=f".{fmt}" if fmt else None)
    lines = [f"Split into {len(files)} chunks"]
    lines.extend(f"  Wrote: {f}" for f in files)
    return "\n".join(lines)


class ParserGUI:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.busy = False

        root.title("ChatGPT / Claude Parser")
        root.minsize(640, 520)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        convert_tab = ttk.Frame(notebook, padding=10)
        chunk_tab = ttk.Frame(notebook, padding=10)
        notebook.add(convert_tab, text="Convert JSON")
        notebook.add(chunk_tab, text="Split a file")

        self._build_convert_tab(convert_tab)
        self._build_chunk_tab(chunk_tab)

        self.log = scrolledtext.ScrolledText(root, height=12, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

        self._apply_service_state()
        self._apply_mode_state()
        self._say("Pick an export file and press Convert.")
        self.root.after(100, self._drain)

    # ---------- Convert tab ----------

    def _build_convert_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        self.input_var = tk.StringVar()
        self.platform_var = tk.StringVar(value=PLATFORMS[0])
        self.output_var = tk.StringVar()
        self.format_var = tk.StringVar(value="txt")
        self.chunk_var = tk.StringVar(value="200")
        self.no_chunk_var = tk.BooleanVar(value=False)
        self.tools_var = tk.BooleanVar(value=False)
        self.hidden_var = tk.BooleanVar(value=False)
        self.thinking_var = tk.BooleanVar(value=False)

        ttk.Label(parent, text="Export JSON:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_input).grid(row=0, column=2)

        ttk.Label(parent, text="Service:").grid(row=1, column=0, sticky="w", pady=4)
        self.platform_box = ttk.Combobox(parent, textvariable=self.platform_var,
                                         values=PLATFORMS, state="readonly", width=14)
        self.platform_box.grid(row=1, column=1, sticky="w", padx=6)
        self.platform_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_service_state())

        ttk.Label(parent, text="Save to folder:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_output).grid(row=2, column=2)
        ttk.Label(parent, text="(leave blank to save beside the original)",
                  foreground="grey").grid(row=3, column=1, sticky="w", padx=6)

        fmt = ttk.LabelFrame(parent, text="Output format", padding=8)
        fmt.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Radiobutton(fmt, text=".txt", variable=self.format_var, value="txt").pack(side="left")
        ttk.Radiobutton(fmt, text=".md", variable=self.format_var, value="md").pack(side="left", padx=12)
        ttk.Label(fmt, text="contents are the same either way",
                  foreground="grey").pack(side="left", padx=8)

        split = ttk.LabelFrame(parent, text="Splitting", padding=8)
        split.grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Label(split, text="Messages per file:").pack(side="left")
        self.chunk_entry = ttk.Entry(split, textvariable=self.chunk_var, width=8)
        self.chunk_entry.pack(side="left", padx=6)
        ttk.Checkbutton(split, text="Don't split", variable=self.no_chunk_var,
                        command=self._toggle_chunk).pack(side="left", padx=12)

        extras = ttk.LabelFrame(parent, text="Include extra messages", padding=8)
        extras.grid(row=6, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Checkbutton(extras, text="Tool calls & results", variable=self.tools_var).pack(anchor="w")
        self.hidden_check = ttk.Checkbutton(extras, text="Hidden/system messages (ChatGPT)",
                                            variable=self.hidden_var)
        self.hidden_check.pack(anchor="w")
        self.thinking_check = ttk.Checkbutton(extras, text="Extended thinking (Claude)",
                                              variable=self.thinking_var)
        self.thinking_check.pack(anchor="w")

        self.convert_btn = ttk.Button(parent, text="Convert", command=self._convert)
        self.convert_btn.grid(row=7, column=0, columnspan=3, pady=10)

    def _apply_service_state(self):
        """Grey out the toggle that doesn't apply to the chosen service.

        Under Auto-detect both stay live: we don't know yet which one matters,
        and picking a file will settle it.
        """
        choice = self.platform_var.get()
        hidden = "normal" if choice in ("Auto-detect", "ChatGPT") else "disabled"
        thinking = "normal" if choice in ("Auto-detect", "Claude") else "disabled"
        self.hidden_check.configure(state=hidden)
        self.thinking_check.configure(state=thinking)

    def _toggle_chunk(self):
        self.chunk_entry.configure(state="disabled" if self.no_chunk_var.get() else "normal")

    def _pick_input(self):
        path = filedialog.askopenfilename(
            title="Choose an exported conversation JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self.input_var.set(path)

        # Cheap prefix scan first; only fall back to a full parse (off-thread,
        # since exports can be huge) when that comes back inconclusive.
        found = sniff_platform(path)
        if found:
            self._set_platform(found)
        else:
            self._say("Checking which service this came from...")
            self._detect_async(path)

    def _set_platform(self, platform):
        self.platform_var.set("ChatGPT" if platform == "chatgpt" else "Claude")
        self._apply_service_state()
        self._say(f"Detected a {self.platform_var.get()} export.")

    def _detect_async(self, path):
        """Full detection on a worker thread; the result is applied in _drain."""
        def worker():
            self.messages.put(("platform", detect_platform(path)))
        threading.Thread(target=worker, daemon=True).start()

    def _pick_output(self):
        path = filedialog.askdirectory(title="Choose an output folder")
        if path:
            self.output_var.set(path)

    def _convert(self):
        source = self.input_var.get().strip()
        if not source:
            self._say("Choose an export file first.")
            return
        if not Path(source).is_file():
            self._say(f"No such file: {source}")
            return

        # None means "detect it on the worker thread" -- keeps a big parse off the UI.
        platform = {"ChatGPT": "chatgpt", "Claude": "claude"}.get(self.platform_var.get())

        if self.no_chunk_var.get():
            chunk_size = None
        else:
            try:
                chunk_size = int(self.chunk_var.get())
                if chunk_size < 1:
                    raise ValueError
            except ValueError:
                self._say("Messages per file must be a whole number above 0.")
                return

        self._start(run_conversion, source, platform,
                    output=self.output_var.get().strip(),
                    fmt=self.format_var.get(),
                    chunk_size=chunk_size,
                    include_tools=self.tools_var.get(),
                    include_hidden=self.hidden_var.get(),
                    include_thinking=self.thinking_var.get())

    # ---------- Split tab ----------

    def _build_chunk_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        self.c_input_var = tk.StringVar()
        self.c_output_var = tk.StringVar()
        self.c_mode_var = tk.StringVar(value="lines")
        self.c_size_var = tk.StringVar(value=DEFAULT_LINES)
        self.c_level_var = tk.StringVar(value="2")
        self.c_format_var = tk.StringVar(value="same")

        ttk.Label(parent, text="Text file:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.c_input_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_chunk_input).grid(row=0, column=2)

        ttk.Label(parent, text="Save to folder:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.c_output_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_chunk_output).grid(row=1, column=2)

        mode = ttk.LabelFrame(parent, text="Split by", padding=8)
        mode.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        for label, value in (("Lines", "lines"), ("Characters", "chars"),
                             ("Markdown headings", "headers")):
            ttk.Radiobutton(mode, text=label, variable=self.c_mode_var, value=value,
                            command=self._apply_mode_state).pack(anchor="w")

        opts = ttk.Frame(parent)
        opts.grid(row=3, column=0, columnspan=3, sticky="ew", pady=4)
        self.c_size_label = ttk.Label(opts, text="Size per chunk:")
        self.c_size_label.pack(side="left")
        self.c_size_entry = ttk.Entry(opts, textvariable=self.c_size_var, width=10)
        self.c_size_entry.pack(side="left", padx=6)
        self.c_level_label = ttk.Label(opts, text="Heading depth:")
        self.c_level_label.pack(side="left", padx=(12, 0))
        self.c_level_entry = ttk.Entry(opts, textvariable=self.c_level_var, width=4)
        self.c_level_entry.pack(side="left", padx=6)

        fmt = ttk.LabelFrame(parent, text="Chunk extension", padding=8)
        fmt.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)
        for label, value in (("Same as input", "same"), (".txt", "txt"), (".md", "md")):
            ttk.Radiobutton(fmt, text=label, variable=self.c_format_var,
                            value=value).pack(side="left", padx=(0, 12))

        ttk.Label(parent, text="Chunks always break at blank lines, never mid-paragraph.",
                  foreground="grey").grid(row=5, column=0, columnspan=3, sticky="w", pady=4)

        self.chunk_btn = ttk.Button(parent, text="Split", command=self._chunk)
        self.chunk_btn.grid(row=6, column=0, columnspan=3, pady=10)

    def _apply_mode_state(self):
        """Only the field the chosen mode actually uses stays editable."""
        headers = self.c_mode_var.get() == "headers"
        state = "disabled" if headers else "normal"
        self.c_size_entry.configure(state=state)
        self.c_size_label.configure(foreground="grey" if headers else "")
        self.c_level_entry.configure(state="normal" if headers else "disabled")
        self.c_level_label.configure(foreground="" if headers else "grey")

        # Nudge the size to a sane default for the mode -- 500 characters would
        # be a useless chunk, and 50,000 lines would never split anything.
        current = self.c_size_var.get()
        if self.c_mode_var.get() == "lines" and current == DEFAULT_CHARS:
            self.c_size_var.set(DEFAULT_LINES)
        elif self.c_mode_var.get() == "chars" and current == DEFAULT_LINES:
            self.c_size_var.set(DEFAULT_CHARS)

    def _pick_chunk_input(self):
        path = filedialog.askopenfilename(
            title="Choose a text file to split",
            filetypes=[("Text files", "*.txt *.md"), ("All files", "*.*")])
        if path:
            self.c_input_var.set(path)

    def _pick_chunk_output(self):
        path = filedialog.askdirectory(title="Choose an output folder")
        if path:
            self.c_output_var.set(path)

    def _chunk(self):
        source = self.c_input_var.get().strip()
        if not source:
            self._say("Choose a file to split first.")
            return
        if not Path(source).is_file():
            self._say(f"No such file: {source}")
            return

        # Only check the field this mode reads, so a stale value in the other
        # one can't block the run.
        mode = self.c_mode_var.get()
        size, level = 0, 2
        if mode == "headers":
            try:
                level = int(self.c_level_var.get())
                if not 1 <= level <= 6:
                    raise ValueError
            except ValueError:
                self._say("Heading depth must be a whole number from 1 to 6.")
                return
        else:
            try:
                size = int(self.c_size_var.get())
                if size < 1:
                    raise ValueError
            except ValueError:
                self._say("Size per chunk must be a whole number above 0.")
                return

        fmt = self.c_format_var.get()
        self._start(run_chunker, source, mode=mode, size=size, header_level=level,
                    output=self.c_output_var.get().strip(),
                    fmt=None if fmt == "same" else fmt)

    # ---------- shared plumbing ----------

    def _start(self, func, *args, **kwargs):
        """Run a job off the UI thread so the window stays responsive."""
        if self.busy:
            self._say("Still working on the last one...")
            return
        self.busy = True
        self.convert_btn.configure(state="disabled")
        self.chunk_btn.configure(state="disabled")
        self._say("Working...")

        def worker():
            try:
                self.messages.put(("log", func(*args, **kwargs) or "Done."))
            except Exception as exc:
                # Expected problems get a plain sentence; anything else keeps
                # its traceback, which is what made the last round debuggable.
                if isinstance(exc, (ValueError, OSError)):
                    self.messages.put(("log", f"Couldn't do that: {exc}"))
                else:
                    self.messages.put(("log", "Something went wrong:\n" + traceback.format_exc()))
            finally:
                self.messages.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self):
        """Poll the worker queue. Every widget touch below is on the UI thread."""
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._say(payload)
            elif kind == "platform":
                if payload:
                    self._set_platform(payload)
                else:
                    self._say("Couldn't tell which service this is from - pick one under Service.")
            elif kind == "done":
                self.busy = False
                self.convert_btn.configure(state="normal")
                self.chunk_btn.configure(state="normal")

        self.root.after(100, self._drain)

    def _say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main():
    if not TK_AVAILABLE:
        raise SystemExit(
            "This GUI needs tkinter, which this Python was built without.\n"
            "\n"
            "To check any interpreter:  python -m tkinter\n"
            "(that opens a small test window if tkinter is working)\n"
            "\n"
            "  Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  Fedora:         sudo dnf install python3-tkinter\n"
            "\n"
            "  pyenv / Homebrew Python (macOS or Linux): Tk has to be present\n"
            "  *before* Python is built, so installing it alone won't fix an\n"
            "  existing interpreter -- rebuild afterwards. For example:\n"
            "      brew install tcl-tk\n"
            "      pyenv uninstall 3.11.15 && pyenv install 3.11.15\n"
            "\n"
            "  python.org installer (macOS/Windows): tkinter is bundled, so\n"
            "  reinstalling Python restores it.\n"
            "\n"
            "The command-line scripts work without tkinter."
        )
    root = tk.Tk()
    ParserGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

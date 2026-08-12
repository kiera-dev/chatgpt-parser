#!/usr/bin/env python3
"""Desktop GUI for the ChatGPT / Claude conversation parsers.

Wraps the same converters the command-line scripts use, so behaviour is
identical -- this only puts a window around them. Requires tkinter, which
ships with most Python installs (see main() for the exception).
"""

import contextlib
import io
import json
import queue
import threading
import traceback
from pathlib import Path

import chatgpt_export_to_text as chatgpt
import claude_export_to_text as claude
import chunker

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False


PLATFORMS = ["Auto-detect", "ChatGPT", "Claude"]


def detect_platform(path):
    """Guess which service exported this JSON. Returns 'chatgpt', 'claude' or None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"), strict=False)
    except (OSError, ValueError):
        return None

    # A full export is a list of conversations; look at the first one.
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


def run_conversion(input_path, platform, output=None, fmt="txt", chunk_size=200,
                   include_tools=False, include_hidden=False, include_thinking=False):
    """Run the converter for `platform`. Returns whatever it printed."""
    module = chatgpt if platform == "chatgpt" else claude

    kwargs = {
        "input_path": input_path,
        "output": output or None,
        "chunk_size": chunk_size,
        "include_tools": include_tools,
        "ext": f".{fmt}",
    }
    if platform == "chatgpt":
        kwargs["include_hidden"] = include_hidden
    else:
        kwargs["include_thinking"] = include_thinking

    buffer = io.StringIO()
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

        ttk.Label(parent, text="Save to:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_output).grid(row=2, column=2)
        ttk.Label(parent, text="(leave blank for the default location)",
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

    def _toggle_chunk(self):
        self.chunk_entry.configure(state="disabled" if self.no_chunk_var.get() else "normal")

    def _pick_input(self):
        path = filedialog.askopenfilename(
            title="Choose an exported conversation JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self.input_var.set(path)
        found = detect_platform(path)
        if found:
            self.platform_var.set("ChatGPT" if found == "chatgpt" else "Claude")
            self._say(f"Detected a {self.platform_var.get()} export.")
        else:
            self._say("Couldn't tell which service this is from - pick one under Service.")

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

        choice = self.platform_var.get()
        platform = {"ChatGPT": "chatgpt", "Claude": "claude"}.get(choice) or detect_platform(source)
        if not platform:
            self._say("Couldn't detect the service. Choose ChatGPT or Claude under Service.")
            return

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
        self.c_size_var = tk.StringVar(value="500")
        self.c_level_var = tk.StringVar(value="2")
        self.c_format_var = tk.StringVar(value="same")

        ttk.Label(parent, text="Text file:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.c_input_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_chunk_input).grid(row=0, column=2)

        ttk.Label(parent, text="Save to:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.c_output_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(parent, text="Browse...", command=self._pick_chunk_output).grid(row=1, column=2)

        mode = ttk.LabelFrame(parent, text="Split by", padding=8)
        mode.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Radiobutton(mode, text="Lines", variable=self.c_mode_var, value="lines").pack(anchor="w")
        ttk.Radiobutton(mode, text="Characters", variable=self.c_mode_var, value="chars").pack(anchor="w")
        ttk.Radiobutton(mode, text="Markdown headings", variable=self.c_mode_var,
                        value="headers").pack(anchor="w")

        opts = ttk.Frame(parent)
        opts.grid(row=3, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Label(opts, text="Size per chunk:").pack(side="left")
        ttk.Entry(opts, textvariable=self.c_size_var, width=10).pack(side="left", padx=6)
        ttk.Label(opts, text="Heading depth:").pack(side="left", padx=(12, 0))
        ttk.Entry(opts, textvariable=self.c_level_var, width=4).pack(side="left", padx=6)

        fmt = ttk.LabelFrame(parent, text="Chunk extension", padding=8)
        fmt.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)
        for label, value in (("Same as input", "same"), (".txt", "txt"), (".md", "md")):
            ttk.Radiobutton(fmt, text=label, variable=self.c_format_var,
                            value=value).pack(side="left", padx=(0, 12))

        ttk.Label(parent, text="Chunks always break at blank lines, never mid-paragraph.",
                  foreground="grey").grid(row=5, column=0, columnspan=3, sticky="w", pady=4)

        self.chunk_btn = ttk.Button(parent, text="Split", command=self._chunk)
        self.chunk_btn.grid(row=6, column=0, columnspan=3, pady=10)

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

        mode = self.c_mode_var.get()
        try:
            size = int(self.c_size_var.get())
            level = int(self.c_level_var.get())
            if size < 1 or not 1 <= level <= 6:
                raise ValueError
        except ValueError:
            self._say("Size must be a whole number above 0, and heading depth 1-6.")
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
                self.messages.put(func(*args, **kwargs) or "Done.")
            except Exception:
                self.messages.put("Something went wrong:\n" + traceback.format_exc())
            finally:
                self.messages.put(None)  # sentinel: job finished

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self):
        """Poll the worker queue from the UI thread."""
        while True:
            try:
                item = self.messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.busy = False
                self.convert_btn.configure(state="normal")
                self.chunk_btn.configure(state="normal")
            else:
                self._say(item)
        self.root.after(100, self._drain)

    def _say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main():
    if not TK_AVAILABLE:
        raise SystemExit(
            "This GUI needs tkinter, which is missing from this Python install.\n"
            "  Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  Fedora:         sudo dnf install python3-tkinter\n"
            "  macOS/Windows:  reinstall Python from python.org (tkinter is included)\n"
            "The command-line scripts work without it."
        )
    root = tk.Tk()
    ParserGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

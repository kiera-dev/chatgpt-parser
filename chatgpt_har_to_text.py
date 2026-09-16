#!/usr/bin/env python3
"""Rebuild a ChatGPT conversation from a DevTools HAR capture.

ChatGPT no longer hands the whole conversation over in one response. The page
asks for the newest turns, then pages backwards through the rest as you scroll:

    /backend-api/conversations/<id>?num_turns=10
    /backend-api/conversations/<id>/messages?before=<cursor>&num_turns=10

So there is no single JSON blob left to copy out of DevTools. Capturing the
network traffic as a HAR does still get everything, and this script stitches
those responses back into one conversation, in the same shape the official
data export uses, and hands it to the usual converters.

A HAR is a recording of your browser traffic. Keep it to yourself: it holds
the conversation text and can hold session identifiers or auth headers. Nothing
here uploads it anywhere, and *.har is in this repo's .gitignore.
"""

import argparse
import base64
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

import chatgpt_json_to_text as chatgpt

# Matches the initial conversation fetch and the /messages pages that follow.
CONVERSATION_URL = re.compile(r"/backend-api/conversation")

# Fields worth lifting off whichever payload happens to carry them.
META_FIELDS = ("title", "create_time", "update_time", "conversation_id", "id", "current_node")


def _decode_body(entry):
    """Pull the response body out of one HAR entry, or None if it has none."""
    content = entry.get("response", {}).get("content", {})
    text = content.get("text")
    if not text:
        return None
    if content.get("encoding") == "base64":
        try:
            text = base64.b64decode(text).decode("utf-8", "replace")
        except (ValueError, TypeError):
            return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def iter_payloads(har_path):
    """Yield (url, parsed_body) for every conversation request in the HAR.

    parsed_body is None when the entry has no usable body, which is how a HAR
    saved *without* content shows up -- worth reporting rather than ignoring.
    """
    har = json.loads(Path(har_path).read_text(encoding="utf-8"), strict=False)
    for entry in har.get("log", {}).get("entries", []):
        url = entry.get("request", {}).get("url", "")
        if not CONVERSATION_URL.search(url):
            continue
        yield url, _decode_body(entry)


def normalise_record(item):
    """Turn one message record into an export-style (id, node) pair.

    Handles both shapes seen in the wild: a mapping-style node that wraps a
    message, and a bare message object.
    """
    if not isinstance(item, dict):
        return None

    if isinstance(item.get("message"), dict):
        message = item["message"]
        node_id = item.get("id") or message.get("id")
        node = {
            "message": message,
            "parent": item.get("parent"),
            "children": list(item.get("children") or []),
        }
    elif "author" in item or "content" in item:
        node_id = item.get("id")
        node = {
            "message": item,
            "parent": item.get("parent"),
            "children": [],
        }
    else:
        return None

    return (node_id, node) if node_id else None


def collect(payloads):
    """Merge every page into one mapping plus whatever metadata we saw.

    Records are keyed by message id, so pages overlapping or arriving out of
    order does not matter -- the first copy of each id wins.
    """
    mapping = {}
    meta = {}

    for _url, data in payloads:
        if not isinstance(data, dict):
            continue

        for field in META_FIELDS:
            value = data.get(field)
            if value is not None and field not in meta:
                meta[field] = value

        node_map = data.get("mapping")
        if isinstance(node_map, dict):
            for node_id, node in node_map.items():
                if isinstance(node, dict) and node_id not in mapping:
                    mapping[node_id] = node

        for key in ("messages", "items", "data"):
            records = data.get(key)
            if isinstance(records, list):
                for item in records:
                    pair = normalise_record(item)
                    if pair and pair[0] not in mapping:
                        mapping[pair[0]] = pair[1]

    return mapping, meta


def _created(node):
    return (node.get("message") or {}).get("create_time") or 0


def linearise(mapping):
    """Rewrite mapping as one straight chain ordered by timestamp."""
    ordered = sorted(mapping.items(), key=lambda pair: _created(pair[1]))
    previous = None
    for node_id, node in ordered:
        node["parent"] = previous
        node["children"] = []
        if previous is not None:
            mapping[previous]["children"] = [node_id]
        previous = node_id
    return previous


def walk_from(mapping, current):
    """Follow parent links back from `current`, like the export format does."""
    seen, chain = set(), []
    while current and current in mapping and current not in seen:
        seen.add(current)
        chain.append(current)
        current = mapping[current].get("parent")
    return chain


def build_conversation(mapping, meta, all_branches=False):
    """Assemble an export-shaped conversation dict, plus a note on what we did.

    The export format stores a tree: edits and regenerations leave dead
    branches hanging off it, and only the path back from current_node is the
    conversation you actually see. We follow that path when it looks intact,
    and fall back to plain timestamp order when it does not.
    """
    conversation = {
        "title": meta.get("title") or "Untitled Chat",
        "create_time": meta.get("create_time"),
        "update_time": meta.get("update_time"),
        "conversation_id": meta.get("conversation_id") or meta.get("id"),
    }

    if not mapping:
        conversation["mapping"] = {}
        conversation["current_node"] = None
        return conversation, "No messages found."

    current = meta.get("current_node")
    chain = walk_from(mapping, current) if current else []

    if all_branches:
        conversation["current_node"] = linearise(mapping)
        note = f"Using all {len(mapping)} records in timestamp order."
    elif len(chain) >= 2:
        conversation["current_node"] = current
        dropped = len(mapping) - len(chain)
        note = f"Followed the conversation thread: {len(chain)} of {len(mapping)} records."
        if dropped and dropped / len(mapping) > 0.5:
            note += ("\n  Over half the records are off that thread. They are usually edits"
                     "\n  or regenerations, but if the result looks short, try --all-branches.")
        else:
            note += f" ({dropped} off-thread: edits/regenerations.)"
    else:
        # No usable current_node -- common when the HAR missed the first
        # request, which is the only response carrying it.
        conversation["current_node"] = linearise(mapping)
        note = (f"No conversation thread to follow, so using all {len(mapping)} records "
                "in timestamp order.")

    conversation["mapping"] = mapping
    return conversation, note


def reconstruct(har_path, all_branches=False):
    payloads = list(iter_payloads(har_path))
    if not payloads:
        raise ValueError(
            "No ChatGPT conversation requests in this HAR. Capture it with the "
            "Network tab open on the conversation, with 'Preserve log' ticked."
        )
    if all(body is None for _url, body in payloads):
        raise ValueError(
            f"Found {len(payloads)} conversation requests but none had a response body. "
            "The HAR was probably saved without content -- right-click the request "
            "list and choose 'Save all as HAR with content'."
        )

    mapping, meta = collect(payloads)
    conversation, note = build_conversation(mapping, meta, all_branches)
    bodies = sum(1 for _url, body in payloads if body is not None)
    return conversation, f"Read {bodies} responses from {len(payloads)} requests.\n  {note}"


def inspect(har_path):
    """Describe the HAR's structure without printing any conversation content.

    For working out what changed if the format moves again -- safe to paste.
    """
    payloads = list(iter_payloads(har_path))
    print(f"Conversation requests: {len(payloads)}")
    if not payloads:
        print("  (nothing matched /backend-api/conversation)")
        return

    print(f"  with a response body: {sum(1 for _u, b in payloads if b is not None)}")

    paths = Counter()
    params = Counter()
    for url, _body in payloads:
        path, _, query = url.partition("?")
        # Replace the conversation id so nothing identifying is printed.
        paths[re.sub(r"/[0-9a-f-]{16,}", "/<id>", path.split("/backend-api")[-1])] += 1
        for pair in query.split("&"):
            if pair:
                params[pair.split("=")[0]] += 1

    print("\nEndpoints:")
    for path, count in paths.most_common():
        print(f"  {count:4}x /backend-api{path}")
    print("\nQuery parameters:")
    for name, count in params.most_common():
        print(f"  {count:4}x {name}")

    top, record, page_info = Counter(), Counter(), Counter()
    for _url, body in payloads:
        if not isinstance(body, dict):
            continue
        top.update(body.keys())
        if isinstance(body.get("page_info"), dict):
            page_info.update(body["page_info"].keys())
        for key in ("messages", "items", "data"):
            items = body.get(key)
            if isinstance(items, list) and items and isinstance(items[0], dict):
                record.update(items[0].keys())
                break
        else:
            node_map = body.get("mapping")
            if isinstance(node_map, dict):
                for node in list(node_map.values())[:1]:
                    if isinstance(node, dict):
                        record.update(f"mapping.{k}" for k in node)

    for title, counter in (("Top-level keys", top), ("page_info keys", page_info),
                           ("Message record keys", record)):
        if counter:
            print(f"\n{title}:")
            for name, count in counter.most_common():
                print(f"  {count:4}x {name}")

    mapping, meta = collect(payloads)
    print(f"\nUnique message records: {len(mapping)}")
    print(f"Metadata found: {', '.join(sorted(meta)) or 'none'}")
    if "current_node" in meta:
        print(f"Thread length from current_node: {len(walk_from(mapping, meta['current_node']))}")


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild a ChatGPT conversation from a DevTools HAR capture.")
    parser.add_argument("input", help="The .har file")
    parser.add_argument("-o", "--output", help="Output file (extension overrides --format)")
    parser.add_argument("--format", choices=["txt", "md"], default="txt",
                        help="Output file extension (default: txt)")
    parser.add_argument("--json", metavar="PATH",
                        help="Also save the rebuilt conversation as export-format JSON")
    parser.add_argument("--all-branches", action="store_true",
                        help="Include every message, not just the visible thread")
    parser.add_argument("--inspect", action="store_true",
                        help="Describe the HAR's structure and exit (prints no conversation text)")
    parser.add_argument("--chunk-size", type=int, default=200,
                        help="Messages per chunk for large conversations (default: 200)")
    parser.add_argument("--no-chunk", action="store_true", help="Do not split large conversations")
    parser.add_argument("--include-tools", action="store_true", help="Include tool/system messages")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden messages")

    args = parser.parse_args()
    har_path = Path(args.input)

    if args.inspect:
        inspect(har_path)
        return

    try:
        conversation, note = reconstruct(har_path, all_branches=args.all_branches)
    except ValueError as exc:
        # These are the "your capture is wrong" cases -- say so plainly rather
        # than burying the advice under a traceback.
        raise SystemExit(f"{exc}\n\nRun with --inspect to see what the HAR does contain.")
    print(note)

    if args.json:
        Path(args.json).write_text(json.dumps(conversation, indent=2), encoding="utf-8")
        print(f"  Wrote: {args.json}")

    output_path = Path(args.output) if args.output else har_path.with_suffix(f".{args.format}")

    # Hand the rebuilt conversation to the ordinary converter rather than
    # re-implementing rendering and chunking, so HAR output is byte-identical
    # to converting the same conversation from a data export.
    source = args.json
    if not source:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with handle:
            json.dump(conversation, handle)
        source = handle.name

    try:
        chatgpt.convert(
            input_path=source,
            output_path=output_path,
            include_tools=args.include_tools,
            include_hidden=args.include_hidden,
            chunk_size=None if args.no_chunk else args.chunk_size,
        )
    finally:
        if not args.json:
            Path(source).unlink(missing_ok=True)


if __name__ == "__main__":
    main()

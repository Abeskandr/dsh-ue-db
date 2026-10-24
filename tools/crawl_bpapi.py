"""Crawl the Blueprint API Reference in ONE pass, saving nodes as they are found.

A category page lists child links and has little body text; a node page has the
actual reference (Inputs/Outputs with types) and no new children. So every fetch
can decide both things at once: save the content, and enqueue any new children.
No second pass, no re-download.

Resumable via raw/bpapi-index.json (saved pages) and raw/bpapi-seen.json
(visited paths), so an interrupted run continues where it stopped.

Usage:  python crawl_bpapi.py [limit] --base <dir>
"""
import json
import os
import queue
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))
from epic import document_json, blocks_to_html
from mdconv import html_to_text
from kbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
kb_ensure(_P)
RAW = _P["raw"]
OUT = os.path.join(RAW, "bpapi")
INDEX = os.path.join(RAW, "bpapi-index.json")
SEEN = os.path.join(RAW, "bpapi-seen.json")

BASE_DOC = "https://dev.epicgames.com/documentation"
ROOT = "en-us/unreal-engine"
PREFIX = f"{BASE_DOC}/unreal-engine/BlueprintAPI/"

_lock = threading.Lock()
_log_lock = threading.Lock()
_counter = {"ok": 0, "fail": 0, "pages": 0}


def log(m):
    with _log_lock:
        print(m, flush=True)


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name.replace("/", "__")) or "page"


def load_json(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def save_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)


def fetch(path):
    page = f"{ROOT}/BlueprintAPI/{path}" if path else f"{ROOT}/BlueprintAPI"
    doc = document_json(page)
    if not doc or not isinstance(doc, dict):
        return None, []
    if doc.get("__redirect__") or doc.get("__notfound__"):
        return None, []
    kids = []
    for h in re.findall(r'href="([^"]+)"', blocks_to_html(doc)):
        if h.startswith(PREFIX):
            rel = h[len(PREFIX):].strip("/")
            if rel and rel != path:
                kids.append(rel)
    return doc, list(dict.fromkeys(kids))


def main():
    argv = sys.argv[1:]
    # strip "--base <dir>"
    cleaned = []
    i = 0
    while i < len(argv):
        if argv[i] == "--base":
            i += 2
            continue
        if argv[i].startswith("--base="):
            i += 1
            continue
        cleaned.append(argv[i])
        i += 1
    limit = int(cleaned[0]) if cleaned and cleaned[0].isdigit() else 0

    os.makedirs(OUT, exist_ok=True)
    pages = load_json(INDEX, {"pages": {}}).get("pages") or {}
    seen = set(load_json(SEEN, {"seen": []}).get("seen") or [])
    log(f"[bpapi] resume: saved={len(pages)} seen={len(seen)}")

    doc, roots = fetch("")
    if not roots:
        log("[bpapi] FAILED root")
        return
    log(f"[bpapi] {len(roots)} top categories")

    q = queue.Queue()
    for r in roots:
        if r not in seen:
            seen.add(r)
            q.put(r)

    t0 = time.time()
    done_flag = threading.Event()

    def worker():
        while True:
            try:
                path = q.get(timeout=2)
            except queue.Empty:
                if done_flag.is_set() and q.empty():
                    return
                continue
            try:
                doc, kids = fetch(path)
                if doc is None:
                    with _lock:
                        _counter["fail"] += 1
                else:
                    body = html_to_text(blocks_to_html(doc))
                    title = doc.get("title") or path
                    fn = safe(path) + ".md"
                    url = f"{BASE_DOC}/{ROOT}/BlueprintAPI/{path}"
                    with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
                        f.write(f"# {title}\n\n> Source: {url}\n"
                                f"> Blueprint API Reference | Unreal Engine 5.8\n\n---\n\n{body}\n")
                    with _lock:
                        if path not in pages:
                            _counter["ok"] += 1
                        pages[path] = {"title": title, "file": fn, "url": url,
                                       "category": "blueprint-api", "size": len(body)}
                    new_kids = []
                    with _lock:
                        for k in kids:
                            if k not in seen:
                                seen.add(k)
                                new_kids.append(k)
                    for k in new_kids:
                        q.put(k)
            except Exception:
                with _lock:
                    _counter["fail"] += 1

            with _lock:
                _counter["pages"] += 1
                n = _counter["pages"]
            if n % 250 == 0:
                el = time.time() - t0
                rate = n / el if el else 0
                log(f"[bpapi] {n} pages | saved={len(pages)} seen={len(seen)} "
                    f"queue={q.qsize()} {rate:.1f}/s")
                with _lock:
                    save_json(INDEX, {"pages": pages})
                    save_json(SEEN, {"seen": sorted(seen)})
            q.task_done()
            if limit and n >= limit:
                done_flag.set()

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(6)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()

    save_json(INDEX, {"pages": pages})
    save_json(SEEN, {"seen": sorted(seen)})
    log(f"[bpapi] DONE pages={_counter['pages']} saved={len(pages)} "
        f"seen={len(seen)} fail={_counter['fail']}")


if __name__ == "__main__":
    main()


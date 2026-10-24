"""Crawl the C++ API restricted to core engine modules.

The full BFS spends most of its time inside `Plugins/*` (third-party and
experimental plugins), while the classes a developer asks about live in
Runtime, Editor and Developer. This script walks only those modules, so the
useful part of the C++ reference is complete long before the long tail.

Usage:  python crawl_cpp_core.py [limit] --base <dir>
"""
import json
import os
import queue
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))
from mdconv import html_to_text
from dbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure
from crawl_cppapi import fetch_html, safe

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
kb_ensure(_P)
RAW = _P["raw"]
OUT = os.path.join(RAW, "cppapi")
INDEX = os.path.join(RAW, "cppapi-index.json")
BASE_DOC = "https://dev.epicgames.com/documentation"
ROOT = "en-us/unreal-engine"

CORE_MODULES = {"Runtime", "Editor", "Developer", "Core", "CoreUObject", "Engine"}

_lock = threading.Lock()
_log_lock = threading.Lock()
_counter = {"pages": 0, "ok": 0, "fail": 0}


def log(m):
    with _log_lock:
        print(m, flush=True)


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


def main():
    argv = sys.argv[1:]
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

    # Candidate paths come from what the full crawler already discovered.
    seen = load_json(os.path.join(RAW, "cppapi-seen.json"), {"seen": []}).get("seen") or []
    core = [p for p in seen if p.split("/")[0] in CORE_MODULES and p not in pages]
    log(f"[cpp-core] {len(core)} core paths to fetch (saved={len(pages)})")
    if not core:
        log("[cpp-core] nothing to do")
        return
    if limit:
        core = core[:limit]

    q = queue.Queue()
    for p in core:
        q.put(p)

    t0 = time.time()
    total = len(core)

    def worker():
        while True:
            try:
                path = q.get_nowait()
            except queue.Empty:
                return
            html = fetch_html(path)
            with _lock:
                _counter["pages"] += 1
                n = _counter["pages"]
            if html is None:
                with _lock:
                    _counter["fail"] += 1
            else:
                body = html_to_text(html)
                if len(body) >= 800:
                    title_m = re.search(r"<title>([^<]*)</title>", html)
                    title = (title_m.group(1).split("|")[0].strip() if title_m
                             else path.split("/")[-1])
                    fn = safe(path) + ".md"
                    url = f"{BASE_DOC}/{ROOT}/API/{path}"
                    try:
                        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
                            f.write(f"# {title}\n\n> Source: {url}\n"
                                    f"> Unreal Engine 5.8 C++ API\n\n---\n\n{body}\n")
                        with _lock:
                            pages[path] = {"title": title, "file": fn, "url": url,
                                           "category": path.split("/")[0],
                                           "size": len(body)}
                            _counter["ok"] += 1
                    except Exception:
                        pass
            if n % 200 == 0:
                el = time.time() - t0
                rate = n / el if el else 0
                log(f"[cpp-core] {n}/{total} saved={len(pages)} "
                    f"{rate:.1f}/s eta={(total - n) / rate / 60:.0f}min" if rate else "")
                with _lock:
                    save_json(INDEX, {"pages": pages})
            q.task_done()

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()

    save_json(INDEX, {"pages": pages})
    log(f"[cpp-core] DONE pages={_counter['pages']} ok={_counter['ok']} "
        f"fail={_counter['fail']} total={len(pages)}")


if __name__ == "__main__":
    main()

"""Crawl the Unreal Engine C++ API Reference pages to Markdown.

The C++ API index (/API) does not expose a machine-readable class list in its
HTML, so class names are discovered from `table_of_content.json` where possible
and, failing that, from the links present on module index pages.

Pages are large (a single class page can exceed 800 KB of HTML) and are served
as static Sphinx-like HTML, so plain HTTP works; cloudscraper is used anyway for
uniform Cloudflare behaviour.

Usage:  python crawl_cppapi.py [limit] --base <dir>
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
from kbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
kb_ensure(_P)
RAW = _P["raw"]
OUT = os.path.join(RAW, "cppapi")
INDEX = os.path.join(RAW, "cppapi-index.json")
SEEN = os.path.join(RAW, "cppapi-seen.json")

BASE_DOC = "https://dev.epicgames.com/documentation"
ROOT = "en-us/unreal-engine"
API_PREFIX = f"{BASE_DOC}/unreal-engine/API/"

_lock = threading.Lock()
_log_lock = threading.Lock()
_counter = {"pages": 0, "fail": 0}


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


def fetch_html(path):
    """Fetch an API page as raw HTML (C++ API pages are not in document.json)."""
    from epic import _scraper, _pace, _rotate
    url = f"{BASE_DOC}/{ROOT}/API/{path}" if path else f"{BASE_DOC}/{ROOT}/API"
    for attempt in range(6):
        try:
            _pace()
            r = _scraper().get(url, timeout=90, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 2000:
                return r.text
            if r.status_code in (403, 429, 503):
                _rotate()
                time.sleep(1.0 + attempt * 2)
                continue
        except Exception:
            _rotate()
            time.sleep(1.0 + attempt * 2)
    return None


def first_class_page():
    """Sanity check that a known class page is readable."""
    return fetch_html("Runtime/Engine/AActor")


def discover_roots():
    """Collect top-level module paths from the API landing page."""
    html = fetch_html("")
    if not html:
        return []
    links = []
    for h in re.findall(r'href="([^"]+)"', html):
        m = re.search(r"/API/([A-Za-z0-9_]+)(?:/|$)", h)
        if m:
            links.append(m.group(1))
    # modules look like "Runtime", "Editor", "Developer", ...
    return list(dict.fromkeys(links))


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

    probe = first_class_page()
    if not probe:
        log("[cppapi] cannot read a known class page — aborting")
        return
    log(f"[cppapi] probe AActor ok ({len(probe)} chars)")

    pages = load_json(INDEX, {"pages": {}}).get("pages") or {}
    seen = set(load_json(SEEN, {"seen": []}).get("seen") or [])
    log(f"[cppapi] resume: saved={len(pages)} seen={len(seen)}")

    roots = discover_roots()
    log(f"[cppapi] {len(roots)} module roots: {roots[:12]}")

    q = queue.Queue()
    # Enqueue everything discovered but never saved (seen - pages), plus roots.
    pending = [p for p in seen if p not in pages]
    for p in pending:
        q.put(p)
    for r in roots:
        if r not in seen:
            seen.add(r)
            q.put(r)
    log(f"[cppapi] queued {q.qsize()} paths ({len(pending)} discovered-not-saved + roots)")

    t0 = time.time()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                path = q.get(timeout=2)
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
                kids = []
                for h in re.findall(r'href="([^"]+)"', html):
                    m = re.search(r"/API/([A-Za-z0-9_/.-]+)", h)
                    if m:
                        rel = m.group(1).strip("/")
                        if rel and rel != path:
                            kids.append(rel)
                # Save any page whose body is substantial: real class/struct
                # reference pages are tens of KB, module index pages are small
                # link lists. Size is the reliable discriminator here.
                if len(body) > 4000:
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
                    except Exception:
                        pass
                new_kids = []
                with _lock:
                    for k in kids:
                        if k not in seen:
                            seen.add(k)
                            new_kids.append(k)
                for k in new_kids:
                    q.put(k)

            if n % 200 == 0:
                el = time.time() - t0
                rate = n / el if el else 0
                log(f"[cppapi] {n} pages | classes={len(pages)} seen={len(seen)} "
                    f"queue={q.qsize()} {rate:.1f}/s")
                with _lock:
                    save_json(INDEX, {"pages": pages})
                    save_json(SEEN, {"seen": sorted(seen)})
            if limit and n >= limit:
                stop.set()

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()

    save_json(INDEX, {"pages": pages})
    save_json(SEEN, {"seen": sorted(seen)})
    log(f"[cppapi] DONE pages={_counter['pages']} classes={len(pages)} "
        f"fail={_counter['fail']}")


if __name__ == "__main__":
    main()

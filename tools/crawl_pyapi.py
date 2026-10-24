"""Download the Unreal Python API documentation (~11 600 classes) as Markdown.

Source: dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/<Class>
These are static Sphinx pages (plain HTTP works, no Cloudflare), so urllib is
enough вЂ” but we reuse cloudscraper for uniform behaviour.

Class list is discovered from the Sphinx genindex page.
"""
import html as htmlmod
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from mdconv import html_to_text
from dbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
kb_ensure(_P)
WORK = KB_BASE
RAW = _P["raw"]
OUT = os.path.join(RAW, "pyapi")
INDEX = os.path.join(RAW, "pyapi-index.json")

BASE = "https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_lock = threading.Lock()


def log(m):
    with _lock:
        print(m, flush=True)


def fetch(url, timeout=45, retries=3):
    """Fetch a Sphinx page.

    Plain urllib used to be enough here, but Epic now answers it with a stall
    or a Cloudflare challenge. cloudscraper is tried first and urllib remains
    as a fallback for environments without it.
    """
    try:
        import cloudscraper
        s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        for a in range(retries):
            try:
                r = s.get(url, timeout=timeout)
                if r.status_code == 200 and r.content:
                    # Decode explicitly: requests/cloudscraper falls back to
                    # latin-1 when no charset is declared, which turns the
                    # Sphinx pilcrow into mojibake ("\u00c2\u00b6").
                    return r.content.decode("utf-8", "replace")
            except Exception:
                time.sleep(1.5 * (a + 1))
    except ImportError:
        pass

    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            time.sleep(1.5 * (a + 1))
    return None


def discover_classes():
    cache = os.path.join(RAW, "pyapi-classes.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    log("[pyapi] discovering class list from genindex...")
    # The Sphinx genindex stopped listing classes (it returns an empty page,
    # 0 links). The documentation root does list them, so try it first and
    # fall back to genindex for older layouts.
    html = fetch(f"{BASE}/")
    if not html or not re.search(r'href="class/[A-Za-z0-9_]+\.html"', html):
        html = fetch(f"{BASE}/genindex.html")
    if not html:
        log("FAILED genindex")
        return []
    names = re.findall(r'href="class/([A-Za-z0-9_]+)\.html"', html)
    names = sorted(set(names))
    json.dump(names, open(cache, "w", encoding="utf-8"))
    log(f"[pyapi] found {len(names)} classes")
    return names


def extract_class(html):
    """Sphinx page -> clean text of the main body."""
    m = re.search(r'<div[^>]*role="main"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.S)
    body = m.group(1) if m else html
    body = re.sub(r'<div class="clearer"></div>', "", body)
    body = re.sub(r'<div class="related".*?</div>', "", body, flags=re.S)
    title_m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
    # Sphinx appends a pilcrow anchor ("unreal.Actor¶") to every heading, so it
    # has to be removed from the title and from the body headings too.
    title = title.replace("\u00b6", "").strip()
    return title, html_to_text(body).replace("\u00b6", "")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    threads = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    os.makedirs(OUT, exist_ok=True)

    classes = discover_classes()
    if not classes:
        return

    done = {}
    if os.path.exists(INDEX):
        try:
            done = json.load(open(INDEX, encoding="utf-8")).get("pages") or {}
        except Exception:
            done = {}
    todo = [c for c in classes if c not in done]
    if limit:
        todo = todo[:limit]
    log(f"[pyapi] to fetch {len(todo)} (have {len(done)})")
    if not todo:
        return

    q = queue.Queue()
    for c in todo:
        q.put(c)
    counter = {"n": 0}
    total = len(todo)
    t0 = time.time()

    def worker():
        while True:
            try:
                name = q.get_nowait()
            except queue.Empty:
                return
            url = f"{BASE}/class/{name}.html"
            html = fetch(url)
            if html:
                title, body = extract_class(html)
                fn = f"{name}.md"
                with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
                    f.write(f"# {title or ('unreal.' + name)}\n\n> Source: {url}\n"
                            f"> Unreal Python API 5.8\n\n---\n\n{body}\n")
                with _lock:
                    done[name] = {"title": title or name, "file": fn, "url": url, "size": len(body)}
            with _lock:
                counter["n"] += 1
                n = counter["n"]
            if n % 200 == 0:
                el = time.time() - t0
                rate = n / el if el else 0
                log(f"  [{n}/{total}] saved={len(done)} {rate:.1f}/s eta={(total-n)/rate/60:.0f}min" if rate else "")
                tmp = INDEX + ".tmp"
                json.dump({"pages": done}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                os.replace(tmp, INDEX)
            q.task_done()

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    json.dump({"pages": done}, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"[pyapi] DONE total={len(done)}")


if __name__ == "__main__":
    main()


"""Parallel crawl of Epic docs with a shared work queue.

Usage:
  crawl.py guides [limit]      -- guides from table_of_content
  crawl.py bpapi  [limit]      -- Blueprint API Reference nodes
  crawl.py cppapi [limit]      -- C++ API classes

Threads each own a cloudscraper session; on 403 the session is replaced.
State is written every N pages so any run is resumable.
"""
import json
import os
import queue
import random
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))
from epic import make_scraper, document_json, blocks_to_html, table_of_content
from mdconv import html_to_text
from kbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure

BASE = base_from_argv(sys.argv[1:])
P = kb_paths(BASE)
kb_ensure(P)
RAW = P["raw"]
WORK = BASE
BASE_DOC = "https://dev.epicgames.com/documentation"
ROOT = "en-us/unreal-engine"

BP_PREFIX = f"{BASE_DOC}/unreal-engine/BlueprintAPI/"
SKIP_TOP = {"PythonAPI", "BlueprintAPI", "API"}

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


class Crawler:
    def __init__(self, kind, out_dir, index_file, threads=6):
        self.kind = kind
        self.out = os.path.join(RAW, out_dir)
        self.index_file = os.path.join(RAW, index_file)
        self.threads = threads
        self.results = {}
        self.fail = []
        self.lock = threading.Lock()
        self.count = 0
        self.total = 0
        self.t0 = time.time()
        os.makedirs(self.out, exist_ok=True)
        if os.path.exists(self.index_file):
            try:
                self.results = json.load(open(self.index_file, encoding="utf-8")).get("pages") or {}
            except Exception:
                self.results = {}

    def safe(self, key):
        return re.sub(r"[^A-Za-z0-9._-]+", "-", key.replace("/", "__")) or "page"

    def save_state(self):
        with self.lock:
            data = {"pages": self.results}
            tmp = self.index_file + ".tmp"
            json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(tmp, self.index_file)

    def record_ok(self, key, title, body, meta):
        fn = self.safe(key) + ".md"
        url = meta.get("url") or f"{BASE_DOC}/en-us/unreal-engine/{key}"
        cat = meta.get("category") or ""
        header = f"# {title}\n\n> Source: {url}\n"
        if cat:
            header += f"> Category: {cat}\n"
        header += f"> Unreal Engine 5.8\n\n---\n\n"
        with open(os.path.join(self.out, fn), "w", encoding="utf-8") as f:
            f.write(header + body + "\n")
        with self.lock:
            self.results[key] = {"title": title, "file": fn, "url": url,
                                 "category": cat, "size": len(body)}

    def worker(self, q, scraper_box):
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                return
            key = item["key"]
            try:
                doc = document_json(f"{ROOT}/{key}")
                if not doc or not isinstance(doc, dict) or doc.get("__redirect__") or doc.get("__notfound__"):
                    with self.lock:
                        self.fail.append(key)
                else:
                    body = html_to_text(blocks_to_html(doc))
                    self.record_ok(key, doc.get("title") or item.get("title") or key, body, item)
            except Exception as exc:
                with self.lock:
                    self.fail.append(key)
            with self.lock:
                self.count += 1
                n = self.count
            if n % 50 == 0:
                el = time.time() - self.t0
                rate = n / el if el else 0
                rem = self.total - n
                log(f"  [{n}/{self.total}] ok={len(self.results)} fail={len(self.fail)} "
                    f"{rate:.1f}/s eta={rem/rate/60:.0f}min" if rate else f"  [{n}]")
                self.save_state()
            q.task_done()

    def run(self, items, limit=0):
        todo = [it for it in items if it["key"] not in self.results]
        if limit:
            todo = todo[:limit]
        self.total = len(todo)
        log(f"[{self.kind}] to fetch: {len(todo)} (already have {len(self.results)})")
        if not todo:
            return
        q = queue.Queue()
        for it in todo:
            q.put(it)
        ths = []
        for _ in range(self.threads):
            box = [make_scraper()]
            t = threading.Thread(target=self.worker, args=(q, box), daemon=True)
            t.start()
            ths.append(t)
        for t in ths:
            t.join()
        self.save_state()
        log(f"[{self.kind}] DONE ok={len(self.results)} fail={len(self.fail)}")


def collect_toc(entries, out, cat=""):
    for e in entries or []:
        slug = e.get("slug")
        if slug:
            top = slug.split("/")[0]
            if top not in SKIP_TOP:
                out.append({"key": slug, "title": e.get("title") or slug,
                            "category": cat or top})
        collect_toc(e.get("sub_entries"), out, cat or (slug or "").split("/")[0])


def build_guides():
    toc_cache = os.path.join(RAW, "toc.json")
    if os.path.exists(toc_cache):
        toc = json.load(open(toc_cache, encoding="utf-8"))
    else:
        toc = table_of_content()
        if not toc:
            log("FAILED toc"); return []
        os.makedirs(RAW, exist_ok=True)
        json.dump(toc, open(toc_cache, "w", encoding="utf-8"), ensure_ascii=False)
    items = []
    collect_toc(toc.get("entries") or [], items)
    seen = set()
    uniq = []
    for it in items:
        if it["key"] in seen:
            continue
        seen.add(it["key"])
        uniq.append(it)
    return uniq


def build_bpapi(c):
    """Discover BP API nodes by walking categories (uses cached discovery)."""
    cache = os.path.join(RAW, "bpapi-discovered.json")
    if os.path.exists(cache):
        data = json.load(open(cache, encoding="utf-8"))
        return data["items"]
    log("[bpapi] discovering tree...")
    root = document_json(f"{ROOT}/BlueprintAPI")
    if not root:
        log("FAILED bpapi root"); return []
    roots = []
    for h in re.findall(r'href="([^"]+)"', blocks_to_html(root)):
        if h.startswith(BP_PREFIX):
            rel = h[len(BP_PREFIX):].strip("/")
            if rel:
                roots.append(rel)
    roots = list(dict.fromkeys(roots))
    log(f"[bpapi] {len(roots)} top categories; walking...")

    import collections
    seen = set(roots)
    q = collections.deque(roots)
    items = []
    while q:
        path = q.popleft()
        doc = document_json(f"{ROOT}/BlueprintAPI/{path}")
        if not doc or doc.get("__redirect__") or doc.get("__notfound__"):
            items.append({"key": f"BlueprintAPI/{path}", "title": path, "category": "BlueprintAPI"})
            continue
        kids = [k[len(BP_PREFIX):].strip("/")
                for k in re.findall(r'href="([^"]+)"', blocks_to_html(doc))
                if k.startswith(BP_PREFIX)]
        kids = [k for k in dict.fromkeys(kids) if k and k not in seen and k != path]
        if kids:
            seen.update(kids)
            q.extend(kids)
        else:
            items.append({"key": f"BlueprintAPI/{path}",
                          "title": doc.get("title") or path,
                          "category": "BlueprintAPI"})
        if len(seen) % 500 == 0:
            log(f"[bpapi] seen={len(seen)} q={len(q)} nodes={len(items)}")
    json.dump({"items": items}, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"[bpapi] discovered {len(items)} nodes")
    return items


def main():
    # Positional args: <kind> [limit]. --base is handled by base_from_argv above,
    # so strip it (and its value) before reading positionals.
    argv = list(sys.argv[1:])
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

    if not cleaned:
        print(__doc__)
        return
    kind = cleaned[0]
    limit = int(cleaned[1]) if len(cleaned) > 1 and cleaned[1].isdigit() else 0

    if kind == "guides":
        items = build_guides()
        c = Crawler("guides", "guides", "guides-index.json", threads=6)
        c.run(items, limit)
    elif kind == "bpapi":
        c = Crawler("bpapi", "bpapi", "bpapi-index.json", threads=6)
        items = build_bpapi(c)
        c.run(items, limit)
    else:
        print("unknown kind", kind)


if __name__ == "__main__":
    main()

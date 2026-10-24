"""Build a single unified index (index-ue.json) for the DSH plugin.

Merges every source under raw/ into one JSON index the plugin loads:
  guides      -- Epic 5.8 pages crawled by crawl.py (or dbv guides as fallback)
  pyapi       -- Unreal Python API classes
  bpapi       -- Blueprint API Reference nodes (inputs/outputs with types)
  cppapi      -- C++ API classes (if crawled)

Each entry carries precomputed `terms` (top keywords from title + body head) so
the plugin can score without opening every file at query time.
"""
import json
import os
import re
import sys
from collections import Counter

from kbpaths import base_from_argv, paths as kb_paths, ensure as kb_ensure

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
kb_ensure(_P)
WORK = KB_BASE
RAW = _P["raw"]
OUT = KB_BASE

STOP = set("""the a an and or of to in on for with is are how do i my it this that can you
what when where which be from at as by not use using set get make want all any may
also its has have will should would could into more than then them these those
there their they we our your""".split())

WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def terms_of(title, body, limit=40):
    c = Counter()
    for w in WORD.findall(title or ""):
        w = w.lower()
        if len(w) > 2:
            c[w] += 6
    for w in WORD.findall((body or "")[:6000]):
        w = w.lower()
        if len(w) > 3 and w not in STOP:
            c[w] += 1
    return [w for w, _ in c.most_common(limit)]


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def collect_guides():
    """Guides live under raw/guides; the index must point there.

    A stale copy may also sit in <base>/guides from an older layout, so the
    path is resolved against the filesystem rather than assumed.
    """
    out = []
    idx = load_json(os.path.join(RAW, "guides-index.json"))
    if idx and idx.get("pages"):
        for slug, m in idx["pages"].items():
            rel = m["file"]
            for cand in (os.path.join("raw", "guides", rel),
                         os.path.join("guides", rel)):
                if os.path.exists(os.path.join(RAW, os.path.dirname(cand), os.path.basename(cand))) \
                        or os.path.exists(os.path.join(KB_BASE, cand)):
                    rel_out = cand
                    break
            else:
                rel_out = os.path.join("raw", "guides", rel)
            f = os.path.join(KB_BASE, rel_out)
            body = ""
            if os.path.exists(f):
                body = open(f, encoding="utf-8", errors="replace").read()
            out.append({
                "slug": slug,
                "title": m.get("title") or slug,
                "file": rel_out,
                "url": m.get("url") or "",
                "category": m.get("category") or "",
                "size": len(body),
                "terms": terms_of(m.get("title") or slug, body),
            })
    # fallback / supplement: optional 5.7 guide chunks next to the 5.8 pages
    dbv_idx = load_json(os.path.join(RAW, "dbv-extract", "dbv-mcp-server-master",
                                     "skills", "dbv-unreal-python-api",
                                     "knowledge", "index_guides.json"))
    if dbv_idx is None:
        dbv_idx = load_json(os.path.join(RAW, "index_guides-dbv.json"))
    have = {g["slug"] for g in out}
    if dbv_idx and dbv_idx.get("guides"):
        for slug, m in dbv_idx["guides"].items():
            if slug in have:
                continue
            chunks = m.get("chunks") or []
            if not chunks:
                continue
            rel = chunks[0]["file"]
            f = os.path.join(RAW, "guides-dbv", os.path.basename(rel))
            body = ""
            if os.path.exists(f):
                body = open(f, encoding="utf-8", errors="replace").read()
            out.append({
                "slug": slug,
                "title": m.get("title") or slug,
                "file": os.path.join("guides-dbv", os.path.basename(rel)),
                "url": m.get("url") or "",
                "category": m.get("category") or "",
                "size": len(body),
                "terms": terms_of(m.get("title") or slug, body),
                "source": "dbv-5.7",
                "chunks": [os.path.join("guides-dbv", os.path.basename(c["file"]))
                           for c in chunks],
            })
    return out


def collect_pyapi():
    out = []
    idx = load_json(os.path.join(RAW, "pyapi-dbv-index.json"))
    # Older layouts kept the classes in raw/pyapi; a crawler run keeps them in
    # pyapi/. Accept whichever exists, and record the path that actually works.
    d = None
    for cand in (os.path.join(RAW, "pyapi"), os.path.join(KB_BASE, "pyapi")):
        if os.path.isdir(cand) and os.listdir(cand):
            d = cand
            break
    if d is None:
        return out
    rel_dir = "raw/pyapi" if d == os.path.join(RAW, "pyapi") else "pyapi"
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        name = fn[:-3]
        p = os.path.join(d, fn)
        try:
            body = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            body = ""
        title = name
        m = re.match(r"#\s+(.+)", body)
        if m:
            title = m.group(1).strip()
        out.append({
            "name": name,
            "title": title,
            "file": os.path.join(rel_dir, fn).replace(os.sep, "/"),
            "url": f"https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/{name}.html",
            "category": "python-api",
            "size": len(body),
            "terms": terms_of(title + " " + name, body),
        })
    return out


def collect_bpapi():
    out = []
    idx = load_json(os.path.join(RAW, "bpapi-index.json"))
    if idx and idx.get("pages"):
        for key, m in idx["pages"].items():
            f = os.path.join(RAW, "bpapi", m["file"])
            body = ""
            if os.path.exists(f):
                body = open(f, encoding="utf-8", errors="replace").read()
            out.append({
                "path": key,
                "title": m.get("title") or key,
                # files stay under raw/, so the index carries that prefix
                "file": os.path.join("raw", "bpapi", m["file"]),
                "url": m.get("url") or "",
                "category": "blueprint-api",
                "size": len(body),
                "terms": terms_of(m.get("title") or key, body),
            })
    return out


def collect_cppapi():
    """Scan the cppapi directory directly.

    The crawler's index file can lag behind what was written to disk (state is
    flushed periodically), so the filesystem is the source of truth here.
    """
    out = []
    d = os.path.join(RAW, "cppapi")
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(d, fn)
        try:
            body = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        title = fn[:-3].replace("__", " / ")
        m = re.match(r"#\s+(.+)", body)
        if m:
            title = m.group(1).strip()
        out.append({
            "name": fn[:-3],
            "title": title,
            "file": os.path.join("raw", "cppapi", fn),
            "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/API/" + fn[:-3].replace("__", "/"),
            "category": "cpp-api",
            "size": len(body),
            "terms": terms_of(title, body),
        })
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    guides = collect_guides()
    pyapi = collect_pyapi()
    bpapi = collect_bpapi()
    cppapi = collect_cppapi()

    import time
    data = {
        "version": "5.8",
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": {"guides": len(guides), "pyapi": len(pyapi),
                   "bpapi": len(bpapi), "cppapi": len(cppapi)},
        "guides": guides,
        "pyapi": pyapi,
        "bpapi": bpapi,
        "cppapi": cppapi,
    }
    outp = os.path.join(OUT, "index-ue.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("wrote", outp, round(os.path.getsize(outp) / 1024 / 1024, 1), "MB")
    print("counts:", data["counts"])


if __name__ == "__main__":
    main()

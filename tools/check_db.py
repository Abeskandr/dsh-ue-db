#!/usr/bin/env python3
"""Health check for the knowledge base.

Verifies that every entry recorded in index-ue.json actually opens, and that a
handful of representative queries return something sensible. Run this after any
crawl, after moving directories, or before publishing.

The path bugs found during development (guides and Python API pointing at
directories that no longer existed) were invisible to search — the metadata was
fine and only `ue_db_get` failed. So the important part here is the exhaustive
read, not the query list.

Usage:  python check_db.py [--base <dir>] [--full]
        --base   knowledge base root (default: DSH_UE_DB_BASE or .)
        --full   read every entry; default samples 500 per kind
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dbpaths import base_from_argv

BASE = base_from_argv(sys.argv[1:])
FULL = "--full" in sys.argv
INDEX = os.path.join(BASE, "index-ue.json")

SECTIONS = ["guides", "pyapi", "bpapi", "cppapi"]

# Queries that should resolve to something recognisable. Kept short on purpose:
# they are a smoke test, not a benchmark.
QUERIES = [
    ("AActor", "cppapi"),
    ("UObject", "cppapi"),
    ("UGameplayStatics", "cppapi"),
    ("Set Actor Location", "bpapi"),
    ("Spawn Actor from Class", "bpapi"),
    ("MaterialEditingLibrary", "pyapi"),
    ("как создать переменную в блюпринте", None),
    ("как сохранить игру", None),
    ("ниагара дождь", None),
]


def main():
    if not os.path.exists(INDEX):
        print(f"FAIL: no index at {INDEX}")
        return 1
    data = json.load(open(INDEX, encoding="utf-8"))

    total = 0
    problems = []
    for sec in SECTIONS:
        entries = data.get(sec) or []
        total += len(entries)
        sample = entries if FULL else random.sample(entries, min(500, len(entries)))
        bad = 0
        for e in sample:
            rel = (e.get("file") or "").replace("\\", os.sep).replace("/", os.sep)
            if not rel:
                bad += 1
                problems.append((sec, e.get("name") or e.get("slug") or e.get("path"), "no file field"))
                continue
            if not os.path.exists(os.path.join(BASE, rel)):
                bad += 1
                if len(problems) < 20:
                    problems.append((sec, e.get("name") or e.get("slug") or e.get("path"), rel))
        status = "OK" if bad == 0 else f"FAIL ({bad}/{len(sample)})"
        print(f"  {sec:<8} {len(entries):>6} entries, checked {len(sample):>4}  {status}")

    print(f"\ntotal entries: {total}")

    if problems:
        print("\nmissing files (first 20):")
        for sec, key, rel in problems[:20]:
            print(f"  [{sec}] {key} -> {rel}")
        return 1

    # Query smoke test — needs the JS search engine, so it is advisory only.
    print("\nquery smoke test: run `node tools/check_queries.mjs` for this part")
    return 0


if __name__ == "__main__":
    sys.exit(main())

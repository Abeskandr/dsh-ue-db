"""Re-derive guide categories from the table_of_content tree.

The first crawler pass inherited the root slug as the category for every page,
so all 3 612 guides ended up with `unreal-engine-5-8-documentation`. The TOC
knows the real section each page belongs to (Get Started, Gameplay Systems,
Animating Characters, ...), so categories are recomputed from it here.

Runs in place over raw/guides-index.json; safe to re-run.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dbpaths import base_from_argv, paths as kb_paths

KB_BASE = base_from_argv(sys.argv[1:])
_P = kb_paths(KB_BASE)
RAW = _P["raw"]
GUIDES_INDEX = os.path.join(RAW, "guides-index.json")
TOC = os.path.join(RAW, "toc.json")

# Top-level section slug -> readable label shown to the agent.
LABELS = {
    "whats-new": "What's New",
    "get-started": "Get Started",
    "understanding-the-basics-of-unreal-engine": "Understanding the Basics",
    "working-with-content-in-unreal-engine": "Working with Content",
    "building-virtual-worlds-in-unreal-engine": "Building Virtual Worlds",
    "designing-visuals-rendering-and-graphics-with-unreal-engine": "Rendering & Graphics",
    "ai-features-tools-and-plugins-in-unreal-engine": "AI Features",
    "creating-visual-effects-in-niagara-for-unreal-engine": "Visual Effects (Niagara)",
    "gameplay-tutorials-for-unreal-engine": "Gameplay Tutorials",
    "blueprints-visual-scripting-in-unreal-engine": "Blueprints",
    "programming-with-cplusplus-in-unreal-engine": "C++ Programming",
    "gameplay-systems-in-unreal-engine": "Gameplay Systems",
    "getting-started-with-mobile-development-in-unreal-engine": "Mobile",
    "animating-characters-and-objects-in-unreal-engine": "Animation",
    "motion-design-in-unreal-engine": "Motion Design",
    "creating-user-interfaces-with-umg-and-slate-in-unreal-engine": "UI (UMG/Slate)",
    "working-with-audio-in-unreal-engine": "Audio",
    "working-with-media-in-unreal-engine": "Media",
    "setting-up-your-production-pipeline-in-unreal-engine": "Production Pipeline",
    "testing-and-optimizing-your-content": "Testing & Optimization",
    "sharing-and-releasing-projects-for-unreal-engine": "Sharing & Releasing",
    "samples-and-tutorials-for-unreal-engine": "Samples & Tutorials",
    "epic-staffcreated-resources-for-unreal-engine": "Epic Resources",
    "node-reference": "Node Reference",
}


def build_slug_map(entries):
    """slug -> top-level section slug, walking the TOC depth-first."""
    out = {}

    def walk(nodes, section):
        for e in nodes or []:
            slug = e.get("slug")
            if not slug:
                continue
            top = section or slug
            # A top-level entry defines the section for its whole subtree.
            out[slug] = top
            walk(e.get("sub_entries") or [], top)

    walk(entries, None)
    return out


def main():
    if not os.path.exists(TOC):
        print("toc.json missing — cannot re-derive categories")
        return
    toc = json.load(open(TOC, encoding="utf-8"))
    roots = toc.get("entries") or []
    # entries[0] is the "Unreal Engine 5.8 Documentation" wrapper
    top_nodes = (roots[0].get("sub_entries") if roots else []) or []
    slug_map = build_slug_map(top_nodes)

    idx = json.load(open(GUIDES_INDEX, encoding="utf-8"))
    pages = idx.get("pages") or {}
    changed = 0
    unknown = 0
    for slug, meta in pages.items():
        top = slug_map.get(slug)
        if not top:
            unknown += 1
            continue
        label = LABELS.get(top, top)
        if meta.get("category") != label:
            meta["category"] = label
            changed += 1

    json.dump(idx, open(GUIDES_INDEX, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"categories updated: {changed} changed, {unknown} unresolved, {len(pages)} total")

    from collections import Counter
    cats = Counter(v.get("category") for v in pages.values())
    print(f"distinct categories: {len(cats)}")
    for c, n in cats.most_common(12):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()

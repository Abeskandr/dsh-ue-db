# -*- coding: utf-8 -*-
"""Remove duplicate keys from the RU_EN glossary, keeping the first value.

JavaScript object literals silently let the LAST occurrence win, so a duplicate
key means the earlier (often better) mapping is dead. For example
'освещение' was mapped to 'lighting' early on and then re-added as 'light' by a
later top-up, which made "настройка освещения" return online-services pages
instead of lighting docs. Detection is silent — nothing errors, the mapping just
quietly changes.

Runs in place; safe to re-run.
"""
import io
import re
from collections import Counter

DB = r"C:\Users\Abesk\Documents\deepseek-harness\default-workspace\ue-kb-work\plugin\lib\db.js"


def main():
    src = io.open(DB, encoding="utf-8").read()
    i = src.find("const RU_EN = {")
    j = src.find("};", i)
    if i < 0 or j < 0:
        raise SystemExit("RU_EN map not found")

    block = src[i:j]
    pairs = re.findall(r"'([^']+)':\s*'([^']*)'", block)
    counts = Counter(k for k, _ in pairs)
    dupes = {k: n for k, n in counts.items() if n > 1}

    if not dupes:
        print("no duplicate keys")
        return

    print(f"duplicate keys: {len(dupes)}")

    # Rebuild the map keeping the FIRST occurrence of each key.
    seen = set()
    keep = []
    dropped = []
    for k, v in pairs:
        if k in seen:
            dropped.append((k, v))
            continue
        seen.add(k)
        keep.append((k, v))

    # Re-emit as a clean object, three pairs per line.
    lines = []
    for n in range(0, len(keep), 3):
        chunk = keep[n:n + 3]
        parts = []
        for k, v in chunk:
            kk = k.replace("'", "\\'")
            vv = v.replace("'", "\\'")
            parts.append(f"'{kk}': '{vv}'")
        lines.append("  " + ", ".join(parts) + ",")
    new_block = "const RU_EN = {\n" + "\n".join(lines) + "\n"

    src = src[:i] + new_block + src[j:]
    io.open(DB, "w", encoding="utf-8", newline="\n").write(src)

    print(f"kept {len(keep)} unique keys, dropped {len(dropped)} duplicates")
    for k, v in dropped[:10]:
        print("  dropped", k.encode("unicode_escape").decode(), "->", v.encode("unicode_escape").decode())


if __name__ == "__main__":
    main()

"""HTML -> Markdown conversion tuned for Epic docs (tables, headers, code)."""
import html as htmlmod
import re


def _table_to_md(table_html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S | re.I)
    out = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)
        vals = []
        for c in cells:
            t = re.sub(r"<br\s*/?>", " ", c, flags=re.I)
            t = re.sub(r"<[^>]+>", "", t)
            t = htmlmod.unescape(t)
            t = re.sub(r"\s+", " ", t).strip()
            vals.append(t)
        if vals:
            out.append("| " + " | ".join(vals) + " |")
            if len(out) == 1:
                out.append("|" + "|".join([" --- "] * len(vals)) + "|")
    return "\n".join(out)


def html_to_text(h):
    if not h:
        return ""
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S | re.I)
    h = re.sub(r"<style.*?</style>", "", h, flags=re.S | re.I)

    # tables first (protect them from generic tag stripping)
    tables = []

    def _stash(m):
        tables.append(_table_to_md(m.group(0)))
        return f"\n\x00TABLE{len(tables) - 1}\x00\n"

    h = re.sub(r"<table[^>]*>.*?</table>", _stash, h, flags=re.S | re.I)

    h = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n\n" + "#" * int(m.group(1)) + " ", h, flags=re.I)
    h = re.sub(r"</h[1-6]>", "\n", h, flags=re.I)
    h = re.sub(r"<pre[^>]*>", "\n```\n", h, flags=re.I)
    h = re.sub(r"</pre>", "\n```\n", h, flags=re.I)
    h = re.sub(r"<code[^>]*>", "`", h, flags=re.I)
    h = re.sub(r"</code>", "`", h, flags=re.I)
    h = re.sub(r"<li[^>]*>", "\n- ", h, flags=re.I)
    h = re.sub(r"</li>", "", h, flags=re.I)
    h = re.sub(r"<strong[^>]*>", "**", h, flags=re.I)
    h = re.sub(r"</strong>", "**", h, flags=re.I)
    h = re.sub(r"<em[^>]*>", "_", h, flags=re.I)
    h = re.sub(r"</em>", "_", h, flags=re.I)
    h = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>', r"\n![\2](\1)\n", h, flags=re.I)
    h = re.sub(r'<img[^>]*src="([^"]*)"[^>]*>', r"\n![](\1)\n", h, flags=re.I)
    h = re.sub(r"<a[^>]*href=\"([^\"]*)\"[^>]*>(.*?)</a>", r"[\2](\1)", h, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</(p|div|tr|blockquote)>", "\n", h, flags=re.I)
    h = re.sub(r"<(p|div)[^>]*>", "\n", h, flags=re.I)

    h = re.sub(r"<[^>]+>", "", h)
    h = htmlmod.unescape(h)
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n[ ]+", "\n", h)
    h = re.sub(r"\n{3,}", "\n\n", h)

    for i, t in enumerate(tables):
        h = h.replace(f"\x00TABLE{i}\x00", t)

    return h.strip()

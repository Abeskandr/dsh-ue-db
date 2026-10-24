"""Epic Developer Community docs client — Cloudflare bypass via cloudscraper.

Verified working 2026-10-23: document.json / table_of_content.json return 200,
plain urllib/requests/fetch return 403 (Cloudflare challenge).

Key finding: Cloudflare degrades trust for a session after a burst of requests.
A FRESH cloudscraper instance per request (or on 403) restores 200. So the
client rotates scrapers and backs off on 403 instead of giving up.
"""
import json
import os
import random
import sys
import threading
import time

import cloudscraper

BASE = "https://dev.epicgames.com/community/api/documentation"
UA_BROWSERS = [
    {"browser": "chrome", "platform": "windows", "mobile": False},
    {"browser": "chrome", "platform": "darwin", "mobile": False},
    {"browser": "chrome", "platform": "linux", "mobile": False},
    {"browser": "firefox", "platform": "windows", "mobile": False},
]

_local = threading.local()

# Global pacing: Cloudflare starts answering 429/403 when the aggregate rate is
# too high, regardless of how many sessions we rotate. One shared limiter keeps
# the whole process under a polite ceiling.
_rate_lock = threading.Lock()
_last_call = [0.0]
MIN_INTERVAL = float(os.environ.get("EPIC_MIN_INTERVAL", "0.35"))


def _pace():
    with _rate_lock:
        now = time.monotonic()
        wait = _last_call[0] + MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
            now = _last_call[0] + MIN_INTERVAL
        _last_call[0] = now



def make_scraper():
    return cloudscraper.create_scraper(browser=random.choice(UA_BROWSERS))


def _scraper():
    """Thread-local scraper; one per thread."""
    s = getattr(_local, "scraper", None)
    if s is None:
        s = make_scraper()
        _local.scraper = s
    return s


def _rotate():
    _local.scraper = make_scraper()


def get_json(path, params=None, retries=8, timeout=90, want_raw=False):
    """GET a JSON endpoint with Cloudflare-aware backoff.

    Returns dict, or {"__redirect__":...}, {"__notfound__":...}, or None.
    """
    url = f"{BASE}/{path.lstrip('/')}"
    p = dict(params or {})
    last = None
    for attempt in range(retries):
        try:
            _pace()
            r = _scraper().get(url, params=p, timeout=timeout, allow_redirects=False)
            if r.status_code == 200:
                if not r.content:
                    last = "empty-body"
                else:
                    try:
                        return r.json()
                    except ValueError:
                        last = "bad-json"
            elif r.status_code == 302:
                return {"__redirect__": True, "body": r.text[:400]}
            elif r.status_code == 404:
                return {"__notfound__": True}
            elif r.status_code in (403, 429, 503):
                # Cloudflare pressure: throw away the tainted session.
                last = f"HTTP {r.status_code}"
                _rotate()
                time.sleep(1.0 + attempt * 1.5 + random.uniform(0, 1.5))
                continue
            else:
                last = f"HTTP {r.status_code}"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
            _rotate()
        time.sleep(min(20.0, 0.8 * (2 ** attempt)) + random.uniform(0, 0.8))
    sys.stderr.write(f"[warn] failed {path} params={p}: {last}\n")
    return None


def document_json(page_path, version="5.8", **kw):
    params = {"path": page_path}
    if version:
        params["application_version"] = version
    return get_json("document.json", params, **kw)


def table_of_content(version="5.8",
                     start="en-us/unreal-engine/understanding-the-basics-of-unreal-engine", **kw):
    params = {"path": start}
    if version:
        params["application_version"] = version
    return get_json("table_of_content.json", params, **kw)


def blocks_to_html(doc):
    if not doc or not isinstance(doc, dict):
        return ""
    parts = []
    for b in doc.get("blocks") or []:
        h = b.get("content_html") or b.get("content")
        if h:
            parts.append(h)
    return "\n".join(parts)

"""Shared path resolution for the UE knowledge base tools.

Every crawler accepts `--base <dir>` (the knowledge base root the user chose).
Layout under it:

    <base>/
      raw/guides/      Epic guide pages (5.8)
      raw/guides-dbv/  dbv 5.7 guide chunks (fallback source)
      raw/pyapi/       Python API class pages
      raw/bpapi/       Blueprint API node pages
      raw/cppapi/      C++ API class pages
      raw/*.json       per-source indexes and progress state
      guides/ pyapi/ bpapi/ cppapi/   final content the plugin reads
      index-ue.json    unified index

Environment fallback: DSH_UE_KB_BASE.
"""
import argparse
import os


def base_from_argv(argv=None, with_limit=False, with_threads=False):
    """Parse the common `--base [--limit N] [--threads N]` tail of a crawler CLI."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--base", default=os.environ.get("DSH_UE_KB_BASE") or ".")
    args, _rest = ap.parse_known_args(argv)
    return os.path.abspath(args.base)


def add_base_arg(parser):
    parser.add_argument("--base", default=os.environ.get("DSH_UE_KB_BASE") or ".",
                        help="Knowledge base root directory")
    return parser


def paths(base):
    raw = os.path.join(base, "raw")
    return {
        "base": base,
        "raw": raw,
        "logs": os.path.join(base, "logs"),
        "guides": os.path.join(raw, "guides"),
        "guides_dbv": os.path.join(raw, "guides-dbv"),
        "pyapi": os.path.join(raw, "pyapi"),
        "bpapi": os.path.join(raw, "bpapi"),
        "cppapi": os.path.join(raw, "cppapi"),
    }


def ensure(paths_dict):
    for k, p in paths_dict.items():
        if k in ("base",):
            continue
        os.makedirs(p, exist_ok=True)

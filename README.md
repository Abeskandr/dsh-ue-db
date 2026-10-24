# dsh-ue-kb — offline Unreal Engine 5.8 knowledge base for DeepSeek Harness

Ask your agent about Unreal Engine and it answers **from a local corpus**, without
touching the network. Guides, Blueprint API nodes, the Python API and the C++ API
are all searchable through four tools registered in DSH.

```
You:  «как привести к классу блюпринт»
Agent: [ue_kb_search] → Cast To … Class (with pin types)
```

## What is inside

| Source | Entries | What it gives the agent |
|---|---|---|
| **Blueprint API** | 52 314 nodes | Every node with its `Inputs`/`Outputs` table: pin type, name, description |
| **C++ API** | 30 841 classes | `AActor`, `UObject`, `UWorld` and the rest: header path, include line, full signature |
| **Python API** | 11 642 classes | `unreal.*` signatures, parameters, properties, inheritance |
| **Guides** | 3 643 pages | The whole Epic documentation, sorted into 36 sections: Gameplay, Animation, Niagara, UMG, PCG, Cinematics, Audio, … |

**98 440 entries total**, about 324 MB on disk and 70 MB of index.

Everything is Unreal Engine **5.8** as published on `dev.epicgames.com`.

## Install

```bash
dsh plugin --profile web add dsh-ue-kb
```

Then download the corpus once (~324 MB, the repository does **not** ship it):

```bash
python -m pip install cloudscraper
# then ask the agent:
ue_kb_update            # or: ue_kb_update(what="bpapi")
```

Restart DSH so the tools appear.

**Why the corpus is not bundled:** it is ~324 MB of text. GitHub rejects files
over 100 MB and the git history would balloon. Downloading on first run also
means you always get a corpus matching your engine version.

**How long it takes.** Epic answers at roughly 4 requests/second before blocking
the IP, so the first full download is measured in hours, not minutes. It is
resumable: stop it whenever you like and call `ue_kb_update` again later — every
run continues from where the previous one stopped, and nothing is re-downloaded.

| Scope | Rough time |
|---|---|
| `pyapi` (plain HTTP, no Cloudflare) | ~15 min |
| `guides` (3 600 pages) | ~45 min |
| `bpapi` (52 000 nodes) | several hours |
| `cppapi` (core modules) | ~2.5 h |
| everything | run it overnight |

## Tools

| Tool | Purpose |
|---|---|
| `ue_kb_search` | Ranked search over all sources. Russian queries are mapped to English through a built-in UE glossary. Filter with `kind=guide\|pyapi\|bpapi\|cppapi`. |
| `ue_kb_get` | Full text of one entry by id from a search result. |
| `ue_kb_status` | Corpus location, version, entry counts. Use it to diagnose a missing base. |
| `ue_kb_update` | The only tool that uses the network. Downloads and re-indexes. Resumable. |

## Choosing where the corpus lives

Resolution order:

1. `config.knowledgePath` in the plugin row — explicit path
2. `DSH_UE_KB_ROOT` environment variable
3. `<plugin>/data` when it holds an index — a local install that bundled the corpus
4. `~/.dsh/ue-kb` — default for a fresh registry install

```yaml
- id: ue-kb
  name: dsh-ue-kb
  config:
    knowledgePath: D:/unreal-docs
```

Delete that directory and the corpus is gone; nothing is written elsewhere.

## Updating

Epic rate-limits aggressively — around 4 requests per second before the IP is
blocked for 15–20 minutes. The crawlers pace themselves globally
(`EPIC_MIN_INTERVAL`, default 0.35 s) and rotate the Cloudflare session on 403.
Each step logs its expected duration before starting, so a long run does not
look like a hang.

```bash
ue_kb_update(what="guides")    # guides only
ue_kb_update(what="bpapi")     # Blueprint API only
ue_kb_update(what="cppapi")    # C++ core modules only
ue_kb_update(what="cppall")    # C++ including third-party plugins — many hours
ue_kb_update(limit=200)        # trial run
```

Cloudflare on `dev.epicgames.com` is bypassed with [cloudscraper], which imitates
a browser TLS fingerprint. Plain Node, `curl` and `urllib` receive 403 — that is
why the network layer is Python.

## Health checks

Both are cheap enough to run after any crawl:

```bash
python tools/check_kb.py --base <dir> --full   # every entry opens
node   tools/check_queries.mjs <dir>           # 9 representative queries
node   tools/check_package.mjs                 # every tool ships in the tarball
```

`check_kb.py` exists because two path bugs during development were invisible:
search kept working and the index stayed valid while `ue_kb_get` silently
returned "file missing". A sampled read is not enough — use `--full`.

## Requirements

- DSH `>= 0.2.0-rc.1`
- Node 20+ (ships with DSH)
- Python 3.10+ and `cloudscraper` — **only** for `ue_kb_update`; searching and
  reading are pure Node

## Layout

```
index-ue.json      unified index (search metadata, precomputed terms)
guides/            Epic guide pages, Markdown
pyapi/             Python API classes, Markdown
raw/bpapi/         Blueprint API nodes
raw/cppapi/        C++ API classes
raw/*-index.json   per-source crawler indexes and resume state
tools/             Python crawlers (network layer)
lib/               Node: search engine, tools, update driver
```

## Legal

The documentation text under `guides/`, `pyapi/`, `raw/bpapi/` and `raw/cppapi/`
is the intellectual property of **Epic Games, Inc.** and is subject to Epic's
terms of use. This project ships only the tooling; the corpus is downloaded by
the user from Epic's public documentation site for personal use.

The code — crawlers, indexer, search engine, DSH plugin — is MIT licensed.

## Licence

MIT for the code. See [LICENSE](LICENSE).

[cloudscraper]: https://pypi.org/project/cloudscraper/

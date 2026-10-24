# dsh-ue-db — offline Unreal Engine 5.8 database for DeepSeek Harness

Ask your agent about Unreal Engine and it answers **from a local corpus**, without
touching the network. Blueprint nodes, the C++ API, the Python API and the full
Epic documentation are searchable through four tools registered in DSH.

```
You:    "how do I cast to another blueprint class"
Agent:  [ue_db_search] → Cast To Class (with pin types)

You:    "AActor"
Agent:  [ue_db_get] → header path, include line, full class signature
```

---

## ⏱ Read this before installing

**The first download takes hours, not minutes.**

The corpus is ~324 MB of documentation that is deliberately **not** shipped in
this package (GitHub rejects files over 100 MB, and a bundled corpus would go
stale). It is fetched from Epic on first use.

Epic rate-limits public documentation to roughly **4 requests per second**
before blocking the IP for 15–20 minutes. A complete first download therefore
runs overnight:

| Scope | Rough time |
|---|---|
| `pyapi` — Python API (plain HTTP, no Cloudflare) | ~15 min |
| `guides` — 3 600 documentation pages | ~45 min |
| `bpapi` — 52 000 Blueprint nodes | several hours |
| `cppapi` — C++ core modules | ~2.5 h |
| everything | leave it running overnight |

**You do not have to do it in one sitting.** Every step resumes: stop whenever
you like, call `ue_db_update` again later, and it continues from where it
stopped without re-downloading anything. Each step also prints its expected
duration before starting, so a long run never looks like a hang.

If you only need the answer to "which node / which function", a partial download
is already useful — start with `pyapi`, then add what you need.

---

## What is inside

| Source | Entries | What it gives the agent |
|---|---|---|
| **Blueprint API** | 52 314 nodes | Every node with its `Inputs`/`Outputs` table: pin type, name, description |
| **C++ API** | 30 841 classes | `AActor`, `UObject`, `UWorld` and the rest: header path, include line, full signature |
| **Python API** | 11 642 classes | `unreal.*` signatures, parameters, properties, inheritance |
| **Guides** | 3 643 pages | The Epic documentation, sorted into 36 sections: Gameplay, Animation, Niagara, UMG, PCG, Cinematics, Audio, … |

**98 440 entries total**, about 324 MB on disk and 70 MB of index.
Everything is Unreal Engine **5.8** as published on `dev.epicgames.com`.

## Languages

The corpus is **English only** — that is how Epic publishes it.

The plugin understands **two languages of query**:

| Query language | How it works |
|---|---|
| **English** | matched directly against the corpus |
| **Russian** | mapped to English through a built-in glossary of ~250 Unreal Engine terms |

```
"how do I cast to another blueprint class"   → Cast To Class
"как привести к классу блюпринт"             → Cast To Class
```

Both return the same result. Other languages are not supported — a query in
another language is matched literally, so it will usually return nothing.

## Install

```bash
dsh plugin --profile web add dsh-ue-db
```

Then, once:

```bash
python -m pip install cloudscraper    # needed only for downloading
```

and ask the agent to run `ue_db_update`. Restart DSH afterwards so the tools
appear in the model's toolset.

## Tools

| Tool | Purpose |
|---|---|
| `ue_db_search` | Ranked search across all sources. Filter with `kind=guide\|pyapi\|bpapi\|cppapi`. |
| `ue_db_get` | Full text of one entry by id from a search result. |
| `ue_db_status` | Corpus location, version, entry counts — use it to diagnose a missing base. |
| `ue_db_update` | The only tool that uses the network. Downloads and re-indexes. Resumable. |

## Choosing where the corpus lives

Resolution order:

1. `config.knowledgePath` in the plugin row — explicit path
2. `DSH_UE_DB_ROOT` environment variable
3. `<plugin>/data` when it holds an index — a local install that bundled the corpus
4. `~/.dsh/ue-db` — default for a fresh registry install

```yaml
- id: ue-db
  name: dsh-ue-db
  config:
    knowledgePath: D:/unreal-docs
```

Point it at an existing corpus and nothing is downloaded. Delete that directory
and the corpus is gone; nothing is written elsewhere.

## Updating

```bash
ue_db_update(what="guides")    # guides only
ue_db_update(what="bpapi")     # Blueprint API only
ue_db_update(what="cppapi")    # C++ core modules only
ue_db_update(what="cppall")    # C++ including third-party plugins — many hours
ue_db_update(limit=200)        # trial run
```

The crawlers pace themselves globally (`EPIC_MIN_INTERVAL`, default 0.35 s) and
rotate the Cloudflare session on 403. Cloudflare is bypassed with
[cloudscraper], which imitates a browser TLS fingerprint — plain Node, `curl`
and `urllib` all receive 403, which is why the network layer is Python.

## Health checks

Cheap enough to run after any crawl:

```bash
python tools/check_db.py --base <dir> --full   # every entry opens
node   tools/check_queries.mjs <dir>           # 9 representative queries
node   tools/check_package.mjs                 # every tool ships in the tarball
```

`check_db.py` exists for a reason: during development two path bugs were
invisible — search kept working and the index stayed valid while `ue_db_get`
silently returned "file missing". A sampled read is not enough, hence `--full`.

## Requirements

- DSH `>= 0.2.0-rc.1`
- Node 20+ (ships with DSH)
- Python 3.10+ and `cloudscraper` — **only** for `ue_db_update`; searching and
  reading are pure Node

## Layout

```
index-ue.json      unified index (search metadata, precomputed terms)
pyapi/             Python API classes, Markdown
raw/guides/        Epic guide pages
raw/bpapi/         Blueprint API nodes
raw/cppapi/        C++ API classes
raw/*-index.json   per-source crawler indexes and resume state
tools/             Python crawlers (network layer)
lib/               Node: search engine, tools, update driver
```

## Legal

The documentation text downloaded into `pyapi/`, `raw/guides/`, `raw/bpapi/` and
`raw/cppapi/` is the intellectual property of **Epic Games, Inc.** and is subject
to Epic's terms of use. This project ships only the tooling; the corpus is
downloaded by the user from Epic's public documentation site for personal use.

The code — crawlers, indexer, search engine, DSH plugin — is MIT licensed.

## Licence

MIT for the code. See [LICENSE](LICENSE).

[cloudscraper]: https://pypi.org/project/cloudscraper/

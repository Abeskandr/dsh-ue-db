/**
 * Storage layout helpers shared by the update tooling and tests.
 *
 * The knowledge base always lives in ONE directory the user chooses:
 *
 *   <base>/
 *     index-ue.json        unified search index (built by build_index.py)
 *     guides/              Epic guide pages (5.8), plain Markdown
 *     guides-dbv/          optional 5.7 guide chunks (fallback source)
 *     pyapi/               Unreal Python API classes
 *     raw/bpapi/           Blueprint API node pages
 *     raw/cppapi/          C++ API class pages
 *     raw/*-index.json     per-source crawler indexes and resume state
 *
 * Nothing is written outside <base> and the temp directory, so deleting the
 * base directory removes every trace of the corpus.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

/** Candidate locations for the knowledge base, highest priority first. */
export function resolveBase(config = {}) {
  if (config.knowledgePath) return path.resolve(String(config.knowledgePath));
  if (process.env.DSH_UE_DB_ROOT) return path.resolve(process.env.DSH_UE_DB_ROOT);
  return path.join(os.homedir(), '.dsh', 'ue-db');
}

/** True when the directory holds a usable index. */
export function hasIndex(base) {
  for (const f of ['index-ue.json', 'index.json']) {
    if (fs.existsSync(path.join(base, f))) return true;
  }
  return false;
}

/** Rough size of the corpus in bytes. */
export function baseSize(base) {
  let total = 0;
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile()) {
        try {
          total += fs.statSync(p).size;
        } catch { /* ignore */ }
      }
    }
  };
  walk(base);
  return total;
}

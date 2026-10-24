/**
 * dsh-ue-db — offline Unreal Engine 5.8 knowledge base for DSH.
 *
 * Provides four tools that read a local Markdown corpus (guides, Python API,
 * Blueprint API nodes, C++ API). No network access at query time; updates are
 * an explicit, user-triggered action.
 *
 * The corpus is NOT shipped with the package: it is ~230 MB of Epic
 * documentation, downloaded on demand by ue_db_update. Resolution order:
 *   1. config.knowledgePath (explicit, highest priority)
 *   2. process.env.DSH_UE_DB_ROOT
 *   3. <plugin>/data when present (a local install that bundled the corpus)
 *   4. ~/.dsh/ue-db  (default location for a fresh install)
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = path.resolve(HERE, '..');

let defineTool = null;
try {
  ({ defineTool } = await import('@deepseek-ai/dsh-tools'));
} catch {
  // Fallback: the plugin is installed outside DSH's node_modules tree (a
  // plugins-local link), so bare-specifier resolution can fail. Use the copy
  // that ships inside the harness installation itself.
  const candidates = [];
  const dshHome = process.env.DSH_HOME;
  const npmGlobal = process.env.APPDATA
    ? path.join(process.env.APPDATA, 'npm', 'node_modules', '@deepseek-ai', 'dsh')
    : null;
  if (npmGlobal) candidates.push(npmGlobal);
  if (dshHome) candidates.push(path.join(dshHome, 'node_modules', '@deepseek-ai', 'dsh'));
  // The profile links the harness too; its node_modules is a valid anchor.
  const profileDir = process.env.DSH_PROFILE_DIR;
  if (profileDir) candidates.push(path.join(profileDir, 'node_modules', '@deepseek-ai', 'dsh'));

  for (const root of candidates) {
    const p = path.join(root, 'node_modules', '@deepseek-ai', 'dsh-tools', 'lib', 'index.js');
    if (!fs.existsSync(p)) continue;
    try {
      const url = `file:///${p.replace(/\\/g, '/')}`;
      ({ defineTool } = await import(url));
      if (defineTool) break;
    } catch { /* try next */ }
  }
  defineTool = defineTool || null;
}

export const inject = ['tools'];

export function apply(ctx, config = {}) {
  const log = (msg) => ctx.logger?.info?.(`[ue-db] ${msg}`);

  const resolveRoot = () => {
    const explicit = config.knowledgePath || process.env.DSH_UE_DB_ROOT;
    if (explicit) return path.resolve(String(explicit));
    // A local install may bundle the corpus next to the code.
    const bundled = path.join(PLUGIN_ROOT, 'data');
    if (fs.existsSync(path.join(bundled, 'index-ue.json'))) return bundled;
    // Fresh install from the registry: the corpus is downloaded here on demand.
    return path.join(os.homedir(), '.dsh', 'ue-db');
  };

  // Lazy singleton: loading a 15k-entry index takes a moment, so it happens on
  // first use rather than at plugin activation.
  let kbPromise = null;
  const getDb = async () => {
    if (!kbPromise) {
      const { Db } = await import('./db.js');
      const root = resolveRoot();
      kbPromise = (async () => {
        const kb = new Db(root);
        if (!kb.ready) log(`knowledge base not ready at ${root}: ${kb.loadError}`);
        else log(`loaded ${kb.entries.length} entries from ${root}`);
        return kb;
      })();
    }
    return kbPromise;
  };

  /** Reload after a path change or a finished update. */
  const reloadDb = async () => {
    kbPromise = null;
    return getDb();
  };

  // The tool description tells the model WHAT the tool is. This section tells
  // it WHEN to reach for it, and it sits in the system prompt beside the other
  // first-party tool guidance — so the agent does not need to be reminded in
  // the chat. Without this the model may answer an Unreal question from memory
  // or go to the web, even though a complete local corpus is right there.
  ctx.inject(['systemPrompt', 'tools'], (sctx) => {
    sctx.effect(() => {
      const dispose = sctx.systemPrompt.section({
        name: 'tool:ue_db',
        order: 210,
        // Only contribute when the tool is actually visible in this scope.
        text: ({ scope }) => (sctx.tools.get('ue_db_search', scope) === undefined
          ? ''
          : 'For ANY question about Unreal Engine (how a system works, which node or function '
            + 'exists, exact parameter names, Blueprint pin types, engine classes) consult the local '
            + 'ue_db_* tools FIRST. They cover the full Epic 5.8 documentation offline and are '
            + 'authoritative; prefer them over web search and over your own recollection. Use web '
            + 'search only when the local database has no answer (a "No results" reply, not a '
            + 'single miss on one phrasing — retry once with different English terms first). '
            + 'Queries to ue_db_* must be in ENGLISH; answer the user in their own language.\n\n'
            + 'THE CORPUS IS NOT SHIPPED. On a fresh install ue_db_status reports ready:false and '
            + 'every search returns nothing until ue_db_update has run. When that happens, do not '
            + 'answer Unreal questions from memory or from the web without saying so: tell the user '
            + 'plainly that the database is empty, that filling it is a multi-hour download paced by '
            + 'Epic\'s rate limit (pyapi ~15 min, guides ~45 min, bpapi ~4 h, cppapi ~2.5 h), and that '
            + 'it resumes where it stopped — then let them choose a slice. Offer pyapi first if they '
            + 'want a quick usable base.'),
      });
      return () => {
        try { dispose(); } catch { /* ignore */ }
      };
    });
  });

  if (!defineTool) {
    log('dsh-tools unavailable — tools not registered');
    return;
  }

  ctx.inject(['tools'], (sctx) => {
    sctx.effect(() => {
      const disposers = [];
      const reg = (def) => disposers.push(sctx.tools.register(defineTool(def)));

      reg({
        name: 'ue_db_search',
        description:
          'Search the LOCAL offline Unreal Engine 5.8 database (guides, Python API classes, '
          + 'Blueprint API nodes, C++ API). Use this instead of a web search for any Unreal Engine '
          + 'question: how a system works, which node/property/function exists, exact parameter names.\n\n'
          + 'LANGUAGE CONTRACT — read carefully:\n'
          + '- The corpus is ENGLISH ONLY. Always write `query` in English, even when the user asked '
          + 'in another language. Translate their INTENT, not their words: "как создать материал" '
          + 'becomes "create material", not a transliteration.\n'
          + '- The user never sees your query, so there is no reason to keep their language in it.\n'
          + '- Answer the user in THEIR language, using what you read here.\n'
          + '- A query containing non-Latin characters is rejected with an explicit error — that is a '
          + 'signal you forgot to translate, not an absence of documentation. Retry in English.\n\n'
          + 'Returns ranked entries with an `id` you can pass to ue_db_get.',
        parameters: {
          query: { type: 'string', required: true,
            description: 'What to look for, e.g. "как создать материал через python", "MaterialEditingLibrary", "Niagara rain"' },
          kind: { type: 'string',
            description: 'Optional filter: guide | pyapi | bpapi | cppapi',
            enum: ['guide', 'pyapi', 'bpapi', 'cppapi'] },
          limit: { type: 'number', description: 'Max results (default 8, max 30)' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              ready: { type: 'boolean' },
              error: { type: 'string' },
              version: { type: 'string' },
              root: { type: 'string' },
              entries: { type: 'number' },
              total: { type: 'number' },
              results: {
                type: 'array',
                items: {
                  type: 'object',
                  additionalProperties: false,
                  properties: {
                    kind: { type: 'string' },
                    title: { type: 'string' },
                    id: { type: 'string' },
                    url: { type: 'string' },
                    category: { type: 'string' },
                    score: { type: 'number' },
                    matches: { type: 'number' },
                  },
                },
              },
            },
          },
          render: (_a, v) => {
            if (v.error) return [{ type: 'text', text: `ue_db_search error: ${v.error}` }];
            if (!v.results?.length) return [{ type: 'text', text: `No results in the ${v.entries ?? 0}-entry database at ${v.root}. If the query was a guess at a page name, search by keywords instead; do not assume the topic is undocumented.` }];
            const lines = [
              `UE ${v.version ?? '?'} knowledge base — ${v.results.length} of ${v.total} matches`,
              '',
            ];
            for (const r of v.results) {
              lines.push(`- [${r.kind}] **${r.title}**  (id: \`${r.id}\`, score ${r.score})`);
              if (r.url) lines.push(`  ${r.url}`);
            }
            lines.push('', 'Use `ue_db_get` with one of the ids above to read the full text.');
            return [{ type: 'text', text: lines.join('\n') }];
          },
        },
        async execute(args) {
          const kb = await getDb();
          const st = kb.status();
          if (!st.ready) {
            return { ready: false, error: st.error || 'knowledge base not loaded', root: st.root };
          }
          const limit = Math.min(Math.max(1, Number(args.limit) || 8), 30);
          const res = kb.search(args.query, { limit, kind: args.kind || null });
          if (res.error) return { ready: true, error: res.error, root: st.root };
          return {
            ready: true,
            version: st.version,
            root: st.root,
            total: res.total,
            entries: kb.entries.length,
            results: res.results.map((r) => ({
              kind: r.kind, title: r.title, id: r.id,
              url: r.url || '', category: r.category || '',
              score: r.score, matches: r.matches,
            })),
          };
        },
      });

      reg({
        name: 'ue_db_get',
        description:
          'Read the full text of one entry from the LOCAL Unreal Engine knowledge base. '
          + 'Pass an `id` returned by ue_db_search (e.g. "pyapi:MaterialEditingLibrary" or '
          + '"guide:niagara-systems-as-a-service"), or a bare name. Use this to get exact '
          + 'function signatures, properties, node inputs/outputs, or a complete guide page.',
        parameters: {
          id: { type: 'string', required: true,
            description: 'Entry id from ue_db_search, or a class/guide name such as "Actor" or "MaterialEditingLibrary"' },
          maxChars: { type: 'number',
            description: 'Truncate the returned text at this many characters (default 20000)' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              kind: { type: 'string' },
              title: { type: 'string' },
              url: { type: 'string' },
              chars: { type: 'number' },
              truncated: { type: 'boolean' },
              content: { type: 'string' },
              error: { type: 'string' },
            },
          },
          render: (_a, v) => {
            if (v.error) return [{ type: 'text', text: `ue_db_get error: ${v.error}` }];
            const head = `# ${v.title} [${v.kind}]${v.url ? `\n${v.url}` : ''}\n\n`;
            return [{ type: 'text', text: head + v.content }];
          },
        },
        async execute(args) {
          const kb = await getDb();
          const st = kb.status();
          if (!st.ready) return { error: st.error || 'knowledge base not loaded' };
          const maxChars = Math.min(Math.max(500, Number(args.maxChars) || 20000), 200000);
          const res = kb.get(String(args.id), { maxChars });
          if (res.error) return { error: res.error };
          return {
            kind: res.kind, title: res.title, url: res.url || '',
            chars: res.chars, truncated: !!res.truncated, content: res.content,
          };
        },
      });

      reg({
        name: 'ue_db_status',
        description:
          'Report the state of the LOCAL Unreal Engine knowledge base: which directory is used, '
          + 'how many entries of each kind (guides, python api, blueprint api, c++ api), version and build date.',
        parameters: {},
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              ready: { type: 'boolean' },
              root: { type: 'string' },
              version: { type: 'string' },
              built: { type: 'string' },
              total: { type: 'number' },
              guides: { type: 'number' },
              pyapi: { type: 'number' },
              bpapi: { type: 'number' },
              cppapi: { type: 'number' },
              error: { type: 'string' },
              hint: { type: 'string' },
            },
          },
          render: (_a, v) => {
            const lines = [
              `**Unreal Engine knowledge base** — ${v.ready ? 'ready' : 'NOT READY'}`,
              `- directory: \`${v.root ?? '?'}\``,
              `- version: ${v.version ?? '?'}${v.built ? ` (built ${v.built})` : ''}`,
              `- entries: ${v.total ?? 0} (guides ${v.guides ?? 0}, python api ${v.pyapi ?? 0}, `
                + `blueprint api ${v.bpapi ?? 0}, c++ api ${v.cppapi ?? 0})`,
            ];
            if (v.error) lines.push(`- error: ${v.error}`);
            if (v.hint) lines.push(`- ${v.hint}`);
            return [{ type: 'text', text: lines.join('\n') }];
          },
        },
        async execute() {
          const kb = await getDb();
          const st = kb.status();
          const k = st.byKind || {};
          const out = {
            ready: !!st.ready,
            root: st.root || resolveRoot(),
            version: st.version || '',
            built: st.built || '',
            total: st.total || 0,
            guides: k.guide || 0,
            pyapi: k.pyapi || 0,
            bpapi: k.bpapi || 0,
            cppapi: k.cppapi || 0,
          };
          if (st.error) out.error = st.error;
          if (!st.ready) {
            out.hint = 'Run ue_db_update to download the documentation, or set knowledgePath to an existing base.';
          } else if (!st.total) {
            // An index that parses but holds nothing is the classic symptom of a
            // half-finished update or an empty data directory.
            out.hint = 'The index exists but is empty. Run ue_db_update to download the corpus.';
          }
          return out;
        },
      });

      reg({
        name: 'ue_db_update',
        description:
          'Download the LOCAL Unreal Engine knowledge base from Epic. This is the ONLY tool here '
          + 'that uses the network, and the corpus ships EMPTY: until this has run at least once, '
          + 'ue_db_search returns nothing at all.\n\n'
          + 'TIME — tell the user before starting; they are entitled to decide first:\n'
          + '  pyapi   ~15 min   11 600 classes, plain HTTP — the quickest useful slice\n'
          + '  guides  ~45 min   3 600 documentation pages\n'
          + '  bpapi   ~4 h      52 000 Blueprint nodes\n'
          + '  cppapi  ~2.5 h    30 000 C++ classes\n'
          + '  all     overnight; expect 8+ hours in total\n'
          + 'Epic rate-limits to roughly 4 requests per second before blocking the IP for 15-20 '
          + 'minutes, so no setting makes this faster. Each step prints its own estimate before '
          + 'it starts, so a long run does not look hung.\n\n'
          + 'RESUMABLE: stopping is safe. Downloaded pages are skipped, so the work can be spread '
          + 'over several sittings and a later call continues where the last one stopped. Nothing '
          + 'has to be deleted to resume.\n\n'
          + 'Requires Python 3.10+ and cloudscraper (pip install cloudscraper); without it the crawl '
          + 'fails at the first Cloudflare challenge. Pass `what` to fetch one slice at a time.',
        parameters: {
          what: { type: 'string',
            description: 'Scope: guides | pyapi | bpapi | cppapi (core modules) | cppall (includes plugins) | all (default: all)',
            enum: ['guides', 'pyapi', 'bpapi', 'cppapi', 'cppall', 'all'] },
          limit: { type: 'number',
            description: 'Stop after N pages (useful for a trial run). 0 = no limit.' },
          rebuildIndex: { type: 'boolean',
            description: 'Rebuild index-ue.json after downloading (default true)' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              started: { type: 'boolean' },
              what: { type: 'string' },
              resolved: { type: 'string' },
              command: { type: 'string' },
              log: { type: 'string' },
              error: { type: 'string' },
              hint: { type: 'string' },
            },
          },
          render: (_a, v) => {
            if (v.error) {
              const t = [`ue_db_update failed: ${v.error}`];
              if (v.hint) t.push(v.hint);
              return [{ type: 'text', text: t.join('\n') }];
            }
            return [{ type: 'text', text:
              `Started update (${v.what}).\ncommand: \`${v.command}\`\nbase: ${v.resolved}\n\n${v.log || ''}` }];
          },
        },
        async execute(args, exec) {
          const { runUpdate } = await import('./update.js');
          const scope = args.what || 'all';
          const limit = Number(args.limit) || 0;
          const base = resolveRoot();
          try {
            const r = await runUpdate({
              scope, limit, base,
              pluginRoot: PLUGIN_ROOT,
              signal: exec?.signal,
              onLog: (line) => ctx.logger?.debug?.(`[ue-db] ${line}`),
            });
            if (args.rebuildIndex !== false && r.ok) await reloadDb();
            return {
              started: r.ok,
              what: scope,
              resolved: base,
              command: r.command || '',
              log: (r.tail || '').slice(-4000),
              ...(r.ok ? {} : { error: r.error || 'update failed' }),
              ...(r.hint ? { hint: r.hint } : {}),
            };
          } catch (err) {
            return {
              started: false,
              what: scope,
              resolved: base,
              command: '',
              log: '',
              error: String(err?.message ?? err),
              hint: 'Make sure Python 3.10+ is installed and the plugin tools/ directory is intact.',
            };
          }
        },
      });

      return () => {
        for (const d of disposers.splice(0)) {
          try { d(); } catch { /* ignore */ }
        }
      };
    });
  });

  log(`plugin loaded (default base: ${resolveRoot()})`);
}

/**
 * dsh-ue-kb — offline Unreal Engine 5.8 knowledge base for DSH.
 *
 * Provides four tools that read a local Markdown corpus (guides, Python API,
 * Blueprint API nodes, C++ API). No network access at query time; updates are
 * an explicit, user-triggered action.
 *
 * The corpus is NOT shipped with the package: it is ~230 MB of Epic
 * documentation, downloaded on demand by ue_kb_update. Resolution order:
 *   1. config.knowledgePath (explicit, highest priority)
 *   2. process.env.DSH_UE_KB_ROOT
 *   3. <plugin>/data when present (a local install that bundled the corpus)
 *   4. ~/.dsh/ue-kb  (default location for a fresh install)
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
  const log = (msg) => ctx.logger?.info?.(`[ue-kb] ${msg}`);

  const resolveRoot = () => {
    const explicit = config.knowledgePath || process.env.DSH_UE_KB_ROOT;
    if (explicit) return path.resolve(String(explicit));
    // A local install may bundle the corpus next to the code.
    const bundled = path.join(PLUGIN_ROOT, 'data');
    if (fs.existsSync(path.join(bundled, 'index-ue.json'))) return bundled;
    // Fresh install from the registry: the corpus is downloaded here on demand.
    return path.join(os.homedir(), '.dsh', 'ue-kb');
  };

  // Lazy singleton: loading a 15k-entry index takes a moment, so it happens on
  // first use rather than at plugin activation.
  let kbPromise = null;
  const getKb = async () => {
    if (!kbPromise) {
      const { Kb } = await import('./kb.js');
      const root = resolveRoot();
      kbPromise = (async () => {
        const kb = new Kb(root);
        if (!kb.ready) log(`knowledge base not ready at ${root}: ${kb.loadError}`);
        else log(`loaded ${kb.entries.length} entries from ${root}`);
        return kb;
      })();
    }
    return kbPromise;
  };

  /** Reload after a path change or a finished update. */
  const reloadKb = async () => {
    kbPromise = null;
    return getKb();
  };

  if (!defineTool) {
    log('dsh-tools unavailable — tools not registered');
    return;
  }

  ctx.inject(['tools'], (sctx) => {
    sctx.effect(() => {
      const disposers = [];
      const reg = (def) => disposers.push(sctx.tools.register(defineTool(def)));

      reg({
        name: 'ue_kb_search',
        description:
          'Search the LOCAL offline Unreal Engine 5.8 knowledge base (guides, Python API classes, '
          + 'Blueprint API nodes, C++ API). Use this instead of a web search for any Unreal Engine '
          + 'question: how a system works, which node/property/function exists, exact parameter names. '
          + 'Russian queries are supported (terms are mapped to English). '
          + 'Returns ranked entries with an `id` you can pass to ue_kb_get.',
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
            if (v.error) return [{ type: 'text', text: `ue_kb_search error: ${v.error}` }];
            if (!v.results?.length) return [{ type: 'text', text: `No results (base: ${v.total ?? 0} entries, ${v.root}).` }];
            const lines = [
              `UE ${v.version ?? '?'} knowledge base — ${v.results.length} of ${v.total} matches`,
              '',
            ];
            for (const r of v.results) {
              lines.push(`- [${r.kind}] **${r.title}**  (id: \`${r.id}\`, score ${r.score})`);
              if (r.url) lines.push(`  ${r.url}`);
            }
            lines.push('', 'Use `ue_kb_get` with one of the ids above to read the full text.');
            return [{ type: 'text', text: lines.join('\n') }];
          },
        },
        async execute(args) {
          const kb = await getKb();
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
            results: res.results.map((r) => ({
              kind: r.kind, title: r.title, id: r.id,
              url: r.url || '', category: r.category || '',
              score: r.score, matches: r.matches,
            })),
          };
        },
      });

      reg({
        name: 'ue_kb_get',
        description:
          'Read the full text of one entry from the LOCAL Unreal Engine knowledge base. '
          + 'Pass an `id` returned by ue_kb_search (e.g. "pyapi:MaterialEditingLibrary" or '
          + '"guide:niagara-systems-as-a-service"), or a bare name. Use this to get exact '
          + 'function signatures, properties, node inputs/outputs, or a complete guide page.',
        parameters: {
          id: { type: 'string', required: true,
            description: 'Entry id from ue_kb_search, or a class/guide name such as "Actor" or "MaterialEditingLibrary"' },
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
            if (v.error) return [{ type: 'text', text: `ue_kb_get error: ${v.error}` }];
            const head = `# ${v.title} [${v.kind}]${v.url ? `\n${v.url}` : ''}\n\n`;
            return [{ type: 'text', text: head + v.content }];
          },
        },
        async execute(args) {
          const kb = await getKb();
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
        name: 'ue_kb_status',
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
          const kb = await getKb();
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
            out.hint = 'Run ue_kb_update to download the documentation, or set knowledgePath to an existing base.';
          } else if (!st.total) {
            // An index that parses but holds nothing is the classic symptom of a
            // half-finished update or an empty data directory.
            out.hint = 'The index exists but is empty. Run ue_kb_update to download the corpus.';
          }
          return out;
        },
      });

      reg({
        name: 'ue_kb_update',
        description:
          'Update the LOCAL Unreal Engine knowledge base by downloading documentation from Epic. '
          + 'This is the ONLY tool here that uses the network, and it can take a long time '
          + '(guides are thousands of pages). Requires Python + the bundled tools directory. '
          + 'Pass `what` to limit the scope. Safe to re-run: already-downloaded pages are skipped.',
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
              const t = [`ue_kb_update failed: ${v.error}`];
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
              onLog: (line) => ctx.logger?.debug?.(`[ue-kb] ${line}`),
            });
            if (args.rebuildIndex !== false && r.ok) await reloadKb();
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

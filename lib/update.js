/**
 * Update driver: shells out to the bundled Python crawlers.
 *
 * Node cannot pass Epic's Cloudflare check (verified: browser-like TLS still
 * returns 403), while `cloudscraper` in Python does. So the network layer lives
 * in tools/*.py and this module only orchestrates it.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const PY_CANDIDATES = process.platform === 'win32'
  ? ['python', 'python3', 'py']
  : ['python3', 'python'];

function pyEnv(pluginRoot, base) {
  const env = { ...process.env };
  // The crawlers live in <plugin>/tools and write into <base>/raw and <base>.
  const vendored = path.join(pluginRoot, '.pydeps');
  if (fs.existsSync(vendored)) {
    env.PYTHONPATH = [vendored, env.PYTHONPATH].filter(Boolean).join(path.delimiter);
  }
  env.DSH_UE_KB_BASE = base;
  env.PYTHONIOENCODING = 'utf-8';
  env.PYTHONUTF8 = '1';
  return env;
}

function run(cmd, args, opts, onLog) {
  return new Promise((resolve) => {
    let tail = '';
    let child;
    try {
      child = spawn(cmd, args, { ...opts, windowsHide: true });
    } catch (err) {
      resolve({ code: -1, tail: '', error: String(err?.message ?? err) });
      return;
    }
    const push = (buf) => {
      const s = buf.toString('utf8');
      tail += s;
      if (tail.length > 20000) tail = tail.slice(-20000);
      onLog?.(s.trimEnd());
    };
    child.stdout?.on('data', push);
    child.stderr?.on('data', push);
    child.on('error', (err) => resolve({ code: -1, tail, error: String(err?.message ?? err) }));
    child.on('close', (code) => resolve({ code, tail }));
    opts.signal?.addEventListener?.('abort', () => {
      try { child.kill(); } catch { /* ignore */ }
    });
  });
}

async function findPython(pluginRoot, base, signal, onLog) {
  const env = pyEnv(pluginRoot, base);
  for (const cmd of PY_CANDIDATES) {
    const r = await run(cmd, ['-c', 'import sys; print(sys.version_info[0])'], { env, signal }, null);
    if (r.code === 0 && r.tail.trim().startsWith('3')) return cmd;
  }
  return null;
}

/**
 * @returns {Promise<{ok:boolean, command?:string, tail?:string, error?:string, hint?:string}>}
 */
export async function runUpdate({ scope = 'all', limit = 0, base, pluginRoot, signal, onLog }) {
  const tools = path.join(pluginRoot, 'tools');
  if (!fs.existsSync(tools)) {
    return { ok: false, error: `tools directory missing: ${tools}`,
      hint: 'Reinstall the plugin; the crawler scripts are part of the package.' };
  }

  const py = await findPython(pluginRoot, base, signal, onLog);
  if (!py) {
    return { ok: false, error: 'Python 3 not found on PATH',
      hint: 'Install Python 3.10+ and make sure `python` works in a terminal.' };
  }

  const env = pyEnv(pluginRoot, base);
  const baseArg = ['--base', base];
  const steps = [];

  if (scope === 'guides' || scope === 'all') {
    steps.push({ label: 'guides', script: 'crawl.py', args: ['guides', String(limit), ...baseArg] });
  }
  if (scope === 'bpapi' || scope === 'all') {
    steps.push({ label: 'blueprint-api', script: 'crawl_bpapi.py', args: [String(limit), ...baseArg] });
  }
  if (scope === 'pyapi' || scope === 'all') {
    steps.push({ label: 'python-api', script: 'crawl_pyapi.py', args: [String(limit), '6', ...baseArg] });
  }
  if (scope === 'cppapi' || scope === 'all') {
    // Core modules first (Runtime/Editor/Developer) — that is what developers
    // ask about. The plugin long tail is opt-in via scope "cppall".
    steps.push({ label: 'cpp-core', script: 'crawl_cpp_core.py', args: [String(limit), ...baseArg] });
    steps.push({ label: 'cpp-priority', script: 'fetch_cpp_priority.py', args: baseArg });
  }
  if (scope === 'cppall') {
    steps.push({ label: 'cpp-all', script: 'crawl_cppapi.py', args: [String(limit), ...baseArg] });
  }
  steps.push({ label: 'index', script: 'build_index.py', args: baseArg });

  let tail = '';
  let command = '';
  for (const step of steps) {
    const scriptPath = path.join(tools, step.script);
    if (!fs.existsSync(scriptPath)) {
      tail += `[skip] ${step.script} not found\n`;
      continue;
    }
    command = `${py} ${scriptPath} ${step.args.join(' ')}`;
    tail += `$ ${command}\n`;
    const r = await run(py, [scriptPath, ...step.args], { env, signal }, onLog);
    tail += `${r.tail || ''}\n`;
    if (r.code !== 0 && step.label !== 'index') {
      // A crawler failure is usually Cloudflare rate limiting; keep going so a
      // partially updated base still gets re-indexed.
      tail += `[warn] ${step.label} exited with code ${r.code} (often Cloudflare 429/403 — retry later)\n`;
    }
    if (r.error) {
      return { ok: false, command, tail, error: r.error };
    }
  }

  return { ok: true, command, tail,
    hint: 'Rate limiting from Epic is normal; re-running later resumes from where it stopped.' };
}

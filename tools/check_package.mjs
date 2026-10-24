#!/usr/bin/env node
/**
 * Verify that the published tarball contains everything ue_db_update needs.
 *
 * A script can exist in the repository but be missing from `files`, and the
 * failure only shows up on a fresh install — the tool silently skips the step
 * with "[skip] ... not found". This check compares what update.js invokes
 * against what npm would actually ship.
 *
 * Usage:  node tools/check_package.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));

// Every script update.js can spawn, by reading the steps it builds.
const updateSrc = fs.readFileSync(path.join(ROOT, 'lib', 'update.js'), 'utf8');
const invoked = [...updateSrc.matchAll(/script:\s*'([^']+)'/g)].map((m) => m[1]);
const unique = [...new Set(invoked)];

const shipped = new Set(pkg.files || []);
const problems = [];

for (const script of unique) {
  const rel = `tools/${script}`;
  if (!fs.existsSync(path.join(ROOT, rel))) {
    problems.push(`${rel} is invoked by update.js but does not exist on disk`);
  } else if (!shipped.has(rel)) {
    problems.push(`${rel} exists but is missing from package.json "files"`);
  }
}

// Everything in tools/ should ship, so a future script cannot be forgotten.
const toolsDir = path.join(ROOT, 'tools');
for (const f of fs.readdirSync(toolsDir)) {
  if (!f.endsWith('.py') && !f.endsWith('.mjs')) continue;
  const rel = `tools/${f}`;
  if (!shipped.has(rel)) problems.push(`${rel} exists on disk but is missing from "files"`);
}

console.log(`update.js invokes ${unique.length} scripts: ${unique.join(', ')}`);
console.log(`package.json ships ${shipped.size} files\n`);

if (problems.length) {
  console.error('PROBLEMS:');
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log('OK: every script present on disk is shipped in the package');

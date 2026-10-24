#!/usr/bin/env node
/**
 * Language contract check.
 *
 * The corpus is English-only and the plugin does not translate. The agent
 * translates the user's question before calling the tool, because it knows the
 * user's language and the plugin does not. Two things must therefore hold:
 *
 *   1. English queries resolve to sensible entries.
 *   2. A non-Latin query is REJECTED with an explicit error, not answered with
 *      an empty list — an empty list reads as "Epic documented nothing about
 *      this", which is wrong and unhelpful.
 *
 * Usage:  node tools/check_language.mjs [<base-dir>]
 */
import { Db } from '../lib/db.js';
import path from 'node:path';
import os from 'node:os';

const base = process.argv[2]
  || process.env.DSH_UE_DB_ROOT
  || path.join(os.homedir(), '.dsh', 'ue-db');

const db = new Db(base);
if (!db.ready) {
  console.error(`FAIL: database not ready at ${db.root}: ${db.loadError}`);
  process.exit(1);
}

// [English query, substring the top title must contain]
const ENGLISH = [
  ['set actor location', 'Set Actor Location'],
  ['spawn actor from class', 'Spawn Actor'],
  ['create material', 'Material'],
  ['animation blueprint', 'Animation'],
  ['save game', 'Save'],
  ['niagara', 'Niagara'],
  ['replication', 'Replication'],
  ['umg widget', 'Widget'],
];

// Queries that must be rejected rather than answered.
const NON_LATIN = ['создать материал', 'материал', '创建材质', 'マテリアル'];

let failed = 0;

console.log('English queries:');
for (const [query, expect] of ENGLISH) {
  const r = db.search(query, { limit: 3 });
  const titles = (r.results || []).map((x) => x.title);
  const hit = titles.some((t) => t.toLowerCase().includes(expect.toLowerCase()));
  if (!hit) failed++;
  console.log(`  ${hit ? 'OK  ' : 'MISS'} ${query}`);
  if (!hit) console.log(`        expected "${expect}", got: ${titles.join(' | ') || '(none)'}`);
}

console.log('\nNon-Latin queries must be rejected, not silently empty:');
for (const query of NON_LATIN) {
  const r = db.search(query, { limit: 3 });
  const rejected = Boolean(r.untranslated) && Boolean(r.error);
  if (!rejected) failed++;
  console.log(`  ${rejected ? 'OK  ' : 'FAIL'} ${query}`);
  if (!rejected) console.log(`        expected an \`untranslated\` error, got: ${JSON.stringify(r).slice(0, 120)}`);
}

const total = ENGLISH.length + NON_LATIN.length;
console.log(`\n${total - failed}/${total} language checks passed`);
process.exit(failed ? 1 : 0);

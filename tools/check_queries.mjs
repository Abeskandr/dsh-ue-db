#!/usr/bin/env node
/**
 * Query smoke test for the knowledge base.
 *
 * Complements check_kb.py: that one verifies every file opens, this one verifies
 * that representative queries still resolve to the right kind of answer.
 *
 * Usage:  node tools/check_queries.mjs [<base-dir>]
 */
import { Kb } from '../lib/kb.js';
import path from 'node:path';
import os from 'node:os';

const base = process.argv[2]
  || process.env.DSH_UE_KB_ROOT
  || path.join(os.homedir(), '.dsh', 'ue-kb');

const kb = new Kb(base);
const st = kb.status();
if (!st.ready) {
  console.error(`FAIL: knowledge base not ready at ${st.root}: ${st.error}`);
  process.exit(1);
}

console.log(`base: ${st.root}`);
console.log(`entries: ${st.total} ${JSON.stringify(st.byKind)}\n`);

// [query, kind filter, substring the top title must contain]
const CASES = [
  ['AActor', 'cppapi', 'AActor'],
  ['UObject', 'cppapi', 'UObject'],
  ['UGameplayStatics', 'cppapi', 'UGameplayStatics'],
  ['UCharacterMovementComponent', 'cppapi', 'UCharacterMovementComponent'],
  ['Set Actor Location', 'bpapi', 'Set Actor Location'],
  ['Spawn Actor from Class', 'bpapi', 'Spawn Actor'],
  ['MaterialEditingLibrary', 'pyapi', 'MaterialEditingLibrary'],
  ['как создать переменную в блюпринте', null, 'Variable'],
  ['как сохранить игру', null, 'Save'],
];

let failed = 0;
for (const [query, kind, expect] of CASES) {
  const r = kb.search(query, { limit: 3, ...(kind ? { kind } : {}) });
  const titles = (r.results || []).map((x) => x.title);
  const hit = titles.some((t) => t.toLowerCase().includes(expect.toLowerCase()));
  if (!hit) failed++;
  const mark = hit ? 'OK  ' : 'MISS';
  console.log(`${mark} ${query}`);
  if (!hit) console.log(`       expected "${expect}" in top 3, got: ${titles.join(' | ') || '(none)'}`);
}

console.log(`\n${CASES.length - failed}/${CASES.length} queries passed`);
process.exit(failed ? 1 : 0);

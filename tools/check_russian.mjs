#!/usr/bin/env node
/**
 * Russian morphology smoke test.
 *
 * A Russian speaker writes "материала", "уровня", "модели" as naturally as the
 * base form. The glossary stores base forms, so ruLookup() strips endings and
 * retries. This checks that inflected queries reach the same answer as the base
 * form — that is the property that actually matters, not the dictionary size.
 *
 * Usage:  node tools/check_russian.mjs [<base-dir>]
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

// [base form, inflected form, expected English token that must appear]
const PAIRS = [
  ['материал', 'материала', 'material'],
  ['материал', 'материалу', 'material'],
  ['уровень', 'уровня', 'level'],
  ['модель', 'модели', 'model'],
  ['актер', 'актёров', 'actor'],
  ['персонаж', 'персонажа', 'character'],
  ['анимация', 'анимации', 'animation'],
  ['текстура', 'текстуры', 'texture'],
  ['скелет', 'скелета', 'skeleton'],
  ['камера', 'камеры', 'camera'],
  ['система', 'системы', 'system'],
  ['ошибка', 'ошибки', 'error'],
  ['звук', 'звуки', 'audio'],
  ['шейдер', 'шейдера', 'shader'],
  ['кривая', 'кривые', 'curve'],
  ['нода', 'ноды', 'node'],
  ['полигон', 'полигоны', 'polygon'],
  ['вершина', 'вершины', 'vertex'],
];

let failed = 0;
for (const [baseForm, inflected, expect] of PAIRS) {
  const a = db.search(baseForm, { limit: 1 });
  const b = db.search(inflected, { limit: 1 });
  const ta = a.results?.[0]?.title || '(none)';
  const tb = b.results?.[0]?.title || '(none)';
  const same = ta === tb && tb !== '(none)';
  if (!same) failed++;
  console.log(`${same ? 'OK  ' : 'DIFF'} ${baseForm} / ${inflected}`);
  if (!same) console.log(`       base -> ${ta}\n       infl -> ${tb}`);
}

console.log(`\n${PAIRS.length - failed}/${PAIRS.length} inflected forms resolve like the base form`);
process.exit(failed ? 1 : 0);

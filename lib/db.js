/**
 * UE knowledge base search engine — pure Node, no dependencies.
 *
 * Loads prebuilt JSON indexes from a user-chosen knowledge directory and
 * answers queries with BM25-style scoring over title, keywords and body text.
 * Russian queries are mapped through a UE term dictionary (ru -> en), because
 * the corpus is English and the user asks in Russian.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

/** Russian/mixed UE terminology -> English tokens actually present in the corpus. */
const RU_EN = {
  'материал': 'material', 'материалы': 'material', 'материалов': 'material',
  'текстура': 'texture', 'текстуры': 'texture', 'текстур': 'texture',
  'меш': 'mesh', 'меша': 'mesh', 'меши': 'mesh', 'мешей': 'mesh',
  'скелет': 'skeleton', 'скелета': 'skeleton', 'кости': 'bone', 'кость': 'bone',
  'анимация': 'animation', 'анимации': 'animation', 'анимацию': 'animation',
  'актор': 'actor', 'актора': 'actor', 'актеры': 'actor', 'акторов': 'actor',
  'класс': 'class', 'классу': 'class', 'класса': 'class', 'классом': 'class',
  'как': '', 'что': '', 'где': '', 'почему': '', 'зачем': '',
  'в': '', 'на': '', 'с': '', 'и': '', 'или': '', 'не': '', 'это': '', 'к': '', 'у': '', 'мне': '', 'можно': '',
  'брюпринт': 'blueprint', 'блюпринт': 'blueprint', 'блюпринты': 'blueprint',
  'блюпринтов': 'blueprint', 'блюпринта': 'blueprint', 'блюпринте': 'blueprint',
  'привести': 'cast convert', 'приведение': 'cast', 'каст': 'cast',
  'переменную': 'variable', 'переменной': 'variable',
  'создать': 'create', 'создание': 'create', 'сделать': 'make create',
  'удалить': 'delete remove',
  'уровень': 'level', 'уровня': 'level', 'уровни': 'level', 'левел': 'level',
  'сцена': 'scene', 'сцены': 'scene', 'камера': 'camera', 'камеры': 'camera',
  'свет': 'light', 'света': 'light', 'освещение': 'lighting', 'тени': 'shadow',
  'звук': 'audio sound', 'звука': 'audio sound', 'аудио': 'audio', 'музыка': 'music',
  'частицы': 'particles niagara', 'эффект': 'effect', 'эффекты': 'effect',
  'физика': 'physics', 'коллизия': 'collision', 'коллизии': 'collision',
  'столкновение': 'collision', 'пересечение': 'overlap',
  'интерфейс': 'interface ui', 'меню': 'menu ui', 'виджет': 'widget',
  'виджеты': 'widget', 'кнопка': 'button', 'худ': 'hud',
  'сеть': 'network', 'сетевой': 'network', 'репликация': 'replication',
  'мультиплеер': 'multiplayer', 'сервер': 'server', 'клиент': 'client',
  'ввод': 'input', 'управление': 'input control', 'клавиша': 'key input',
  'сохранение': 'save', 'сохранить': 'save', 'сохранять': 'save', 'загрузка': 'load', 'загрузить': 'load', 'загрузил': 'load',
  'игра': 'game', 'игры': 'game', 'игру': 'game', 'игре': 'game', 'игровой': 'game',
  'сделать': 'make create', 'сделай': 'make', 'настроить': 'setup configure', 'настройка': 'setup configure',
  'дождь': 'rain', 'дождя': 'rain', 'снег': 'snow', 'огонь': 'fire', 'взрыв': 'explosion',

  'ассет': 'asset', 'ассеты': 'asset', 'ресурс': 'asset', 'ресурсы': 'asset',
  'папка': 'folder directory', 'каталог': 'directory',
  'проект': 'project', 'проекта': 'project', 'сборка': 'build', 'собрать': 'build',
  'компиляция': 'compile', 'скомпилировать': 'compile', 'ошибка': 'error',
  'оптимизация': 'optimization performance', 'производительность': 'performance',
  'лаг': 'performance lag', 'фпс': 'fps performance',
  'создать': 'create', 'сделать': 'make create', 'удалить': 'delete remove',
  'изменить': 'change edit modify', 'получить': 'get', 'найти': 'find get',
  'установить': 'set', 'добавить': 'add', 'убрать': 'remove',
  'нужно': 'need', 'через': 'via through', 'для': 'for', 'при': 'on',
  'ландшафт': 'landscape', 'ландшафта': 'landscape', 'террейн': 'landscape terrain',
  'растительность': 'foliage', 'трава': 'foliage grass',
  'материнский': 'parent', 'дочерний': 'child', 'экземпляр': 'instance',
  'шейдер': 'shader', 'шейдеры': 'shader', 'шейдеров': 'shader',
  'постобработка': 'post process', 'туман': 'fog', 'вода': 'water',
  'оружие': 'weapon', 'персонаж': 'character', 'персонажа': 'character',
  'движение': 'movement', 'перемещение': 'movement', 'прыжок': 'jump',
  'инвентарь': 'inventory', 'предмет': 'item', 'урон': 'damage',
  'здоровье': 'health', 'способность': 'ability', 'способности': 'ability',
  'ии': 'ai', 'враг': 'enemy ai', 'навмеш': 'navmesh navigation',
  'навигация': 'navigation', 'путь': 'path navigation',
  'таймлайн': 'timeline', 'событие': 'event', 'события': 'event',
  'функция': 'function', 'функции': 'function', 'переменная': 'variable',
  'переменные': 'variable', 'макрос': 'macro', 'библиотека': 'library',
  'класс': 'class', 'класса': 'class', 'структура': 'struct', 'перечисление': 'enum',
  'система': 'system', 'подсистема': 'subsystem', 'плагин': 'plugin',
  'плагины': 'plugin', 'модуль': 'module', 'пакет': 'package plugin',
  'ниагара': 'niagara', 'метазвук': 'metasound', 'кварц': 'quartz',
  'секвенсор': 'sequencer', 'синематика': 'cinematic sequencer',
  'рендер': 'render', 'рендеринг': 'rendering', 'отрисовка': 'rendering',
  'освещение': 'lighting', 'тень': 'shadow', 'отражения': 'reflection',
  'люмен': 'lumen', 'нанит': 'nanite', 'виртуальная': 'virtual',
  'геометрия': 'geometry', 'полигон': 'polygon', 'вершина': 'vertex',
  'развертка': 'uv unwrap', 'нормали': 'normals',
  'морф': 'morph', 'блендшейп': 'morph blend shape',
  'риг': 'rig', 'риггинг': 'rigging', 'контролриг': 'control rig',
  'ретаргет': 'retarget', 'ретаргетинг': 'retargeting',
  'кривая': 'curve', 'график': 'graph curve', 'нода': 'node',
  'ноды': 'node', 'узел': 'node', 'узлы': 'node', 'пин': 'pin',
  'контент': 'content', 'браузер': 'browser content browser',
  'редактор': 'editor', 'окно': 'window panel', 'панель': 'panel',
  'настройки': 'settings', 'конфигурация': 'config settings',
  'консоль': 'console', 'команда': 'command', 'лог': 'log',
  'отладка': 'debug', 'дебаг': 'debug', 'профилирование': 'profiling',
  'версия': 'version', 'обновление': 'update upgrade', 'миграция': 'migration',
  'упаковка': 'packaging cook', 'билд': 'build', 'упаковать': 'package cook',

  'актёр': 'actor', 'оружия': 'weapon', 'оружие': 'weapon', 'оружий': 'weapon',
  'актер': 'actor', 'актера': 'actor', 'актеры': 'actor', 'актеров': 'actor',
  // --- topped up by tools/topup_glossary.py ---
  'открыть': 'open', 'закрыть': 'close', 'запустить': 'run start',
  'запуск': 'run', 'остановить': 'stop', 'включить': 'enable',
  'выключить': 'disable', 'переключить': 'toggle switch', 'выбрать': 'select',
  'выделить': 'select', 'копировать': 'copy', 'вставить': 'paste',
  'переименовать': 'rename', 'проверить': 'check verify', 'проверка': 'check',
  'исправить': 'fix', 'починить': 'fix', 'сломать': 'break',
  'обновить': 'update', 'изменение': 'change', 'удаление': 'delete',
  'найтись': 'find', 'актёра': 'actor', 'актёры': 'actor',
  'актёров': 'actor', 'актеров': 'actor', 'модель': 'mesh model',
  'модели': 'mesh model', 'моделей': 'mesh model', 'мира': 'world level',
  'мир': 'world', 'материала': 'material', 'материалу': 'material',
  'материалом': 'material', 'материале': 'material', 'ассета': 'asset',
  'ассетов': 'asset', 'персонажи': 'character', 'персонажей': 'character',
  'уровнем': 'level', 'классы': 'class', 'классов': 'class',
  'системы': 'system', 'ошибки': 'error', 'ошибок': 'error',
  'папки': 'folder directory', 'папок': 'folder directory', 'пути': 'path',
  'предметы': 'item', 'предметов': 'item', 'враги': 'enemy ai',
  'врагов': 'enemy ai', 'кнопки': 'button', 'кнопок': 'button',
  'клавиши': 'key input', 'клавиш': 'key input', 'кривые': 'curve',
  'кривых': 'curve', 'полигоны': 'polygon', 'полигонов': 'polygon',
  'вершины': 'vertex', 'вершин': 'vertex', 'шейдера': 'shader',
  'звуки': 'audio sound', 'звуков': 'audio sound', 'музыки': 'music',
  'шум': 'noise audio', 'кадры': 'frame fps', 'лаги': 'performance lag',
  'тест': 'test', 'тесты': 'test', 'тестов': 'test',
  'столкновения': 'collision', 'столкновений': 'collision', 'анимационный': 'animation',
  'голубой': 'blue', 'мышь': 'mouse input', 'какой': '',
  'какие': '', 'какая': '', 'который': '',
  'которая': '', 'которые': '', 'когда': '',
  'надо': '', 'нельзя': '', 'есть': '',
  'нет': '', 'этот': '', 'эта': '',
  'эти': '', 'этом': '', 'этого': '',
  'до': '', 'по': '', 'от': '',
  'из': '', 'простой': 'simple', 'проще': 'simple',
  'лучше': 'better', 'лучший': 'best', 'быстрый': 'fast',
  'быстрее': 'fast', 'медленный': 'slow', 'пример': 'example',
  'примеры': 'example', 'примеров': 'example', 'способ': 'way method',
  'способы': 'way method', 'вариант': 'option', 'варианты': 'option',
};


// Russian morphology: a query says "материала" or "уровня" as readily as the
// base form, so a miss in the glossary retries with the ending stripped.
// Ordered longest-first; the first suffix that leaves a plausible stem wins.
const RU_SUFFIXES = [
  'ованиями', 'ованиям', 'ования', 'ование',
  'аниями', 'аниям', 'ание', 'ания',
  'ениями', 'ениям', 'ение', 'ения',
  'иями', 'иям', 'ией', 'ия',
  'ями', 'ям', 'ах', 'ям', 'ов', 'ев', 'ей',
  'ами', 'ого', 'ему', 'ому', 'ыми', 'ими',
  'ая', 'яя', 'ое', 'ее', 'ый', 'ий', 'ой',
  'ую', 'юю', 'ые', 'ие', 'ых', 'их',
  'а', 'е', 'и', 'й', 'о', 'у', 'ы', 'ь', 'я',
];

function ruStem(word) {
  if (word.length < 4) return word;
  for (const suf of RU_SUFFIXES) {
    if (word.length - suf.length < 3) continue;
    if (word.endsWith(suf)) return word.slice(0, -suf.length);
  }
  return word;
}

/** Glossary lookup with a morphology fallback. Returns undefined when unknown. */
function ruLookup(word) {
  if (Object.prototype.hasOwnProperty.call(RU_EN, word)) return RU_EN[word];
  // Russian writers are inconsistent about "ё": актёр/актер, шёл/шел.
  const withoutYo = word.replace(/\u0451/g, '\u0435');
  if (withoutYo !== word && Object.prototype.hasOwnProperty.call(RU_EN, withoutYo)) {
    return RU_EN[withoutYo];
  }
  const stemmed = ruStem(word);
  if (stemmed !== word && Object.prototype.hasOwnProperty.call(RU_EN, stemmed)) {
    return RU_EN[stemmed];
  }
  // A stemmed form may itself be unknown while its own base is known; try one
  // more strip for the longest compounds.
  const again = ruStem(stemmed);
  if (again !== stemmed && Object.prototype.hasOwnProperty.call(RU_EN, again)) {
    return RU_EN[again];
  }
  return undefined;
}

const STOP = new Set([
  'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'is',
  'are', 'how', 'do', 'i', 'my', 'it', 'this', 'that', 'can', 'you', 'what',
  'when', 'where', 'which', 'be', 'from', 'at', 'as', 'by', 'not', 'use',
  'using', 'set', 'make', 'want',
]);

// Cyrillic spelled with escapes so the regex never depends on file encoding.
const CYR = '\u0410-\u044f\u0401\u0451';
const CYR_ONLY = /^[\u0430-\u044f\u0451]+$/;
const WORD_RE = new RegExp(`[A-Za-z${CYR}_][A-Za-z${CYR}0-9_]+`, 'g');

/** Split text into lowercase tokens; keeps Cyrillic so the dictionary can map it. */
function tokenize(text) {
  const out = [];
  const s = String(text ?? '');
  let m;
  WORD_RE.lastIndex = 0;
  while ((m = WORD_RE.exec(s))) {
    const raw = m[0];
    const w = raw.toLowerCase();
    if (w.length < 2) continue;
    if (CYR_ONLY.test(w)) {
      const mapped = ruLookup(w);
      if (mapped) for (const t of mapped.split(/\s+/)) if (t) out.push(t);
      out.push(w);
    } else {
      if (!STOP.has(w)) out.push(w);
      // Unreal type naming: AActor, UObject, FVector, ENetRole, TArray.
      // Users type the prefixed form; class docs index the bare name.
      if (raw.length > 2 && /^[AUFET][A-Z]/.test(raw)) out.push(w.slice(1));
    }
  }
  return out;
}

function stem(w) {
  if (w.length <= 4) return w;
  for (const suf of ['ization', 'ations', 'ation', 'ings', 'ing', 'ers',
    'ies', 'ied', 'es', 'ed', 's']) {
    if (w.length > suf.length + 3 && w.endsWith(suf)) return w.slice(0, -suf.length);
  }
  return w;
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

/** Slug-safe file stem matching crawler output. */
export function slugKey(str) {
  const s = String(str);
  // '/' -> '__' is reversible, so tree paths keep their identity. Epic also
  // publishes sibling nodes whose names differ only by a trailing '-' (a
  // truncated long name vs the untruncated one); stripping separators merged
  // 324 such pairs into one id and hid them from search.
  const reversible = s.replace(/\//g, '__');
  if (/^[A-Za-z0-9._-]+$/.test(reversible)) return reversible;
  // Anything that still needs lossy replacement gets a short digest, so two
  // distinct entries can never collapse onto the same id.
  const clean = reversible.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '') || 'page';
  return `${clean}~${createHash('sha1').update(s).digest('hex').slice(0, 8)}`;
}

export class Db {
  constructor(rootDir = null, logger = null) {
    this.root = null;
    this.logger = logger;
    this.entries = [];
    this.byId = new Map();
    this.df = new Map();
    this.N = 0;
    this.meta = {};
    this.ready = false;
    this.loadError = null;
    if (rootDir) this.load(rootDir);
  }

  static findIndexes(root) {
    const out = [];
    for (const [file, layout] of [['index-ue.json', 'ue'], ['index.json', 'dbv']]) {
      const p = path.join(root, file);
      if (fs.existsSync(p)) out.push({ file, layout, path: p });
    }
    return out;
  }

  load(rootDir) {
    this.root = path.resolve(rootDir);
    this.entries = [];
    this.byId.clear();
    this.df.clear();
    this.ready = false;
    this.loadError = null;
    this.meta = {};

    const idx = Db.findIndexes(this.root);
    if (!idx.length) {
      this.loadError = `No index file found in ${this.root} (looked for index-ue.json, index.json)`;
      return false;
    }
    let loadedAny = false;
    for (const { path: p, layout } of idx) {
      const data = readJson(p);
      if (!data) continue;
      if (layout === 'ue') this._loadUeIndex(data, path.dirname(p));
      else this._loadDbvIndex(data, path.dirname(p));
      loadedAny = true;
    }
    if (!loadedAny) {
      this.loadError = 'Index files exist but could not be parsed';
      return false;
    }
    this._buildStats();
    this.ready = true;
    return true;
  }

  _add(entry) {
    const id = `${entry.kind}:${entry.key}`;
    if (this.byId.has(id)) return;
    this.byId.set(id, entry);
    this.entries.push(entry);
  }

  _loadUeIndex(data, baseDir) {
    Object.assign(this.meta, {
      version: data.version || '5.8',
      built: data.built || null,
      guideCount: (data.guides || []).length,
      pyapiCount: (data.pyapi || []).length,
      bpapiCount: (data.bpapi || []).length,
      cppapiCount: (data.cppapi || []).length,
      layout: 'ue',
    });
    for (const g of data.guides || []) {
      this._add({ key: slugKey(g.slug), kind: 'guide', title: g.title || g.slug,
        file: path.join(baseDir, g.file), url: g.url || '', category: g.category || '',
        size: g.size || 0, indexTerms: g.terms || null });
    }
    for (const c of data.pyapi || []) {
      this._add({ key: slugKey(c.name), kind: 'pyapi', title: c.title || c.name,
        file: path.join(baseDir, c.file), url: c.url || '', category: c.category || 'python-api',
        size: c.size || 0, indexTerms: c.terms || null });
    }
    for (const b of data.bpapi || []) {
      this._add({ key: slugKey(b.path), kind: 'bpapi', title: b.title || b.path,
        file: path.join(baseDir, b.file), url: b.url || '', category: b.category || 'blueprint-api',
        size: b.size || 0, indexTerms: b.terms || null });
    }
    for (const x of data.cppapi || []) {
      this._add({ key: slugKey(x.name), kind: 'cppapi', title: x.title || x.name,
        file: path.join(baseDir, x.file), url: x.url || '', category: x.category || 'cpp-api',
        size: x.size || 0, indexTerms: x.terms || null });
    }
  }

  _loadDbvIndex(data, baseDir) {
    const classes = data.classes || {};
    const gIdx = readJson(path.join(baseDir, 'index_guides.json'));
    const guides = (gIdx && gIdx.guides) || {};
    Object.assign(this.meta, {
      version: data.version || '?',
      built: data.updated || null,
      guideCount: Object.keys(guides).length,
      pyapiCount: Object.keys(classes).length,
      bpapiCount: 0,
      cppapiCount: 0,
      layout: 'dbv',
    });
    for (const [name, m] of Object.entries(classes)) {
      this._add({ key: slugKey(name), kind: 'pyapi', title: name,
        file: path.join(baseDir, m.file || path.join('classes', `${name}.md`)),
        url: m.url || '', category: m.category || 'python-api', size: 0,
        indexTerms: m.keywords || null });
    }
    for (const [slug, m] of Object.entries(guides)) {
      const chunks = m.chunks || [];
      this._add({ key: slugKey(slug), kind: 'guide', title: m.title || slug,
        file: chunks.length ? path.join(baseDir, chunks[0].file) : '',
        url: m.url || '', category: m.category || '', size: 0,
        indexTerms: m.keywords || null, isGuideRoot: true, chunks });
    }
  }

  _buildStats() {
    this.N = this.entries.length;
    this.df.clear();
    for (const e of this.entries) {
      const terms = new Set();
      for (const t of tokenize(e.title)) terms.add(stem(t));
      for (const t of e.indexTerms || []) terms.add(stem(String(t).toLowerCase()));
      for (const t of terms) this.df.set(t, (this.df.get(t) || 0) + 1);
    }
  }

  /** BM25-lite scoring: title > keywords > body (body only for the shortlist). */
  search(query, { limit = 8, kind = null } = {}) {
    if (!this.ready) return { error: this.loadError || 'knowledge base not loaded' };
    const qterms = [...new Set(tokenize(query).map(stem))].filter((t) => t.length > 1);
    if (!qterms.length) return { error: 'empty query after tokenization' };

    const phrase = String(query).toLowerCase().trim();
    const scored = [];

    for (const e of this.entries) {
      if (kind && e.kind !== kind) continue;
      const titleTerms = new Set(tokenize(e.title).map(stem));
      const kwTerms = new Set((e.indexTerms || []).map((t) => stem(String(t).toLowerCase())));
      const titleLow = e.title.toLowerCase();

      // Exact class-name hit: 'AActor' should resolve entry 'Actor'.
      const rawQuery = String(query).trim();
      const bare = rawQuery.replace(/^unreal\./i, '').replace(/^[AUFET](?=[A-Z])/, '').toLowerCase();
      const titleBare = titleLow.replace(/^unreal\./, '');
      const exactClass = bare.length > 2 && (titleBare === bare || titleLow === phrase);

      let score = exactClass ? 500 : 0;
      let matched = exactClass ? Math.max(2, qterms.length) : 0;
      let bodyOnly = 0;
      for (const q of qterms) {
        const dfq = this.df.get(q) || 0;
        const idf = Math.log(1 + (this.N - dfq + 0.5) / (dfq + 0.5));
        const w = idf > 0 ? idf : 1;
        let hit = 0;
        if (titleTerms.has(q)) hit = 10;
        // Substring only for longer tokens: "via" must not match "Trivial".
        else if (q.length >= 5 && titleLow.includes(q)) hit = 4;
        else if (kwTerms.has(q)) hit = 1.2;
        // A category hit is real signal: "niagara" should favour the
        // Visual Effects section over an unrelated page that mentions it once.
        else if ((e.category || '').toLowerCase().includes(q)) hit = 2.2;
        if (hit) {
          score += hit * w;
          matched += 1;
          if (hit <= 1.2) bodyOnly += 1;
        }
      }
      // An entry whose only evidence is weak body/keyword noise should not
      // outrank a real title match.
      if (matched > 0 && bodyOnly === matched) score *= 0.35;

      const keyLow = String(e.key).toLowerCase();
      if (phrase && (keyLow === phrase || titleLow === phrase)) {
        score += 60;
        matched = Math.max(matched, 2);
      } else if (phrase.length >= 4 && (keyLow.includes(phrase) || titleLow.includes(phrase))) {
        score += 15;
        matched = Math.max(matched, 1);
      }

      // Corpus balance: 52k Blueprint nodes outnumber 3.6k guides 14:1, so a
      // node whose title happens to reuse a query word otherwise buries the
      // conceptual article. Guides and C++ classes answer "how does X work"
      // better than a node stub, so they are nudged up.
      if (e.kind === 'guide') score *= 1.15;
      else if (e.kind === 'cppapi') score *= 1.1;

      // Coverage matters more than raw score: an entry that hits several
      // distinct query concepts beats one that repeats a single common word.
      if (matched > 1) score *= 1 + 0.8 * (matched - 1);
      // Entries matching one common term only should not flood the top.
      else if (matched === 1 && qterms.length > 2) score *= 0.5;
      if (score > 0) scored.push({ entry: e, score, matched });
    }

    scored.sort((a, b) => b.score - a.score || b.matched - a.matched);
    const top = scored.slice(0, Math.max(1, limit));

    const words = qterms.slice(0, 6);
    for (const item of top) {
      try {
        const text = this._readEntry(item.entry, 1);
        if (!text) continue;
        const low = text.toLowerCase();
        let bodyHits = 0;
        for (const w of words) {
          let idx = 0;
          let c = 0;
          while ((idx = low.indexOf(w, idx)) !== -1 && c < 12) {
            c += 1;
            idx += w.length;
          }
          bodyHits += c;
        }
        item.bodyHits = bodyHits;
        item.score += Math.min(18, bodyHits * 0.6);
      } catch { /* ignore */ }
    }
    top.sort((a, b) => b.score - a.score);

    return {
      query,
      terms: qterms,
      total: scored.length,
      results: top.map((t) => ({
        kind: t.entry.kind,
        title: t.entry.title,
        id: t.entry.key,
        url: t.entry.url,
        category: t.entry.category,
        score: Math.round(t.score * 10) / 10,
        matches: t.matched,
      })),
    };
  }

  _readEntry(e, chunkLimit = 0) {
    if (e.isGuideRoot && e.chunks && e.chunks.length) {
      const parts = [];
      const cs = chunkLimit ? e.chunks.slice(0, chunkLimit) : e.chunks;
      for (const c of cs) {
        const f = path.join(this.root, c.file);
        if (fs.existsSync(f)) parts.push(fs.readFileSync(f, 'utf8'));
      }
      return parts.join('\n\n');
    }
    return fs.existsSync(e.file) ? fs.readFileSync(e.file, 'utf8') : '';
  }

  get(id, { maxChars = 20000 } = {}) {
    if (!this.ready) return { error: this.loadError || 'knowledge base not loaded' };
    let entry = this.byId.get(id);
    if (!entry) {
      for (const k of ['guide', 'pyapi', 'bpapi', 'cppapi']) {
        const c = this.byId.get(`${k}:${id}`);
        if (c) {
          entry = c;
          break;
        }
      }
    }
    if (!entry) {
      const low = String(id).toLowerCase();
      const cands = this.entries.filter((e) => e.key.toLowerCase() === low
        || e.title.toLowerCase() === low
        || e.key.toLowerCase() === slugKey(id));
      if (cands.length === 1) entry = cands[0];
    }
    if (!entry) return { error: `not found: ${id}` };

    const content = this._readEntry(entry);
    if (!content) return { error: `file missing for ${id}`, file: entry.file };
    const truncated = content.length > maxChars;
    return {
      kind: entry.kind,
      title: entry.title,
      url: entry.url,
      truncated,
      chars: content.length,
      content: truncated
        ? `${content.slice(0, maxChars)}\n\n[... truncated ${content.length - maxChars} chars; raise maxChars to read more]`
        : content,
    };
  }

  status() {
    const byKind = {};
    for (const e of this.entries) byKind[e.kind] = (byKind[e.kind] || 0) + 1;
    return {
      ready: this.ready,
      root: this.root,
      error: this.loadError,
      version: this.meta.version || null,
      built: this.meta.built || null,
      total: this.entries.length,
      byKind,
      layout: this.meta.layout || null,
    };
  }
}

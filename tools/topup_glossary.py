# -*- coding: utf-8 -*-
"""Top up the Russian glossary and add morphology-tolerant lookup.

Two problems were found by tools/check_glossary.py:

1. 87 common words were simply absent (открыть, модель, шум, какой, ...).
2. Far worse: only the nominative form was mapped. A Russian speaker writes
   "материала", "материалу", "модели", "уровня" as naturally as the base form,
   and every one of those missed the glossary entirely.

Listing every inflection is hopeless, so the fix is a light Russian stemmer:
strip a common ending, retry the lookup. That covers regular nouns, adjectives
and verb forms without a dependency.
"""
import io
import re

DB = r"C:\Users\Abesk\Documents\deepseek-harness\default-workspace\ue-kb-work\plugin\lib\db.js"

# Words that were missing outright. Service words map to '' (they are noise).
ADDITIONS = {
    # verbs / actions
    "открыть": "open", "закрыть": "close", "запустить": "run start", "запуск": "run",
    "остановить": "stop", "включить": "enable", "выключить": "disable",
    "переключить": "toggle switch", "выбрать": "select", "выделить": "select",
    "копировать": "copy", "вставить": "paste", "переименовать": "rename",
    "проверить": "check verify", "проверка": "check", "исправить": "fix",
    "починить": "fix", "сломать": "break", "сломать": "break",
    "обновить": "update", "изменение": "change", "удаление": "delete",
    "найтись": "find", "добавить": "add",
    # nouns (inflected forms that were missing)
    "актёра": "actor", "актёры": "actor", "актёров": "actor", "актеров": "actor",
    "модель": "mesh model", "модели": "mesh model", "моделей": "mesh model",
    "мира": "world level", "мир": "world",
    "материала": "material", "материалу": "material", "материалом": "material",
    "материале": "material", "материалов": "material",
    "ассета": "asset", "ассетов": "asset",
    "персонажи": "character", "персонажей": "character",
    "уровня": "level", "уровнем": "level",
    "классы": "class", "классов": "class",
    "системы": "system", "система": "system",
    "ошибки": "error", "ошибок": "error",
    "папки": "folder directory", "папок": "folder directory",
    "пути": "path", "путь": "path",
    "предметы": "item", "предметов": "item",
    "враги": "enemy ai", "врагов": "enemy ai",
    "кнопки": "button", "кнопок": "button",
    "клавиши": "key input", "клавиш": "key input",
    "кривые": "curve", "кривых": "curve",
    "полигоны": "polygon", "полигонов": "polygon",
    "вершины": "vertex", "вершин": "vertex",
    "шейдера": "shader", "шейдеров": "shader",
    "звуки": "audio sound", "звуков": "audio sound",
    "музыки": "music", "шум": "noise audio",
    "кадры": "frame fps", "лаги": "performance lag",
    "тест": "test", "тесты": "test", "тестов": "test",
    "столкновения": "collision", "столкновений": "collision",
    "анимационный": "animation", "голубой": "blue", "мышь": "mouse input",
    # service words -> noise
    "какой": "", "какие": "", "какая": "", "который": "", "которая": "",
    "которые": "", "когда": "", "где": "", "почему": "", "зачем": "",
    "надо": "", "нужно": "", "нельзя": "", "есть": "", "нет": "",
    "этот": "", "эта": "", "эти": "", "этом": "", "этого": "",
    "до": "", "по": "", "от": "", "из": "", "при": "", "для": "",
    "простой": "simple", "проще": "simple", "лучше": "better",
    "лучший": "best", "быстрый": "fast", "быстрее": "fast", "медленный": "slow",
    "пример": "example", "примеры": "example", "примеров": "example",
    "способ": "way method", "способы": "way method",
    "вариант": "option", "варианты": "option",
}


def js_object(entries):
    lines = []
    items = list(entries.items())
    for i in range(0, len(items), 3):
        chunk = items[i:i + 3]
        parts = []
        for k, v in chunk:
            kk = k.replace("'", "\\'")
            vv = v.replace("'", "\\'")
            parts.append(f"'{kk}': '{vv}'")
        lines.append("  " + ", ".join(parts) + ",")
    return "\n".join(lines)


def main():
    src = io.open(DB, encoding="utf-8").read()

    # 1. Insert additions into RU_EN, before the closing brace of the map.
    i = src.find("const RU_EN = {")
    j = src.find("};", i)
    block = src[i:j]
    existing = dict(re.findall(r"'([^']+)':\s*'([^']*)'", block))

    added = {k: v for k, v in ADDITIONS.items() if k not in existing}
    if added:
        insertion = "\n  // --- topped up by tools/topup_glossary.py ---\n" + js_object(added) + "\n"
        src = src[:j] + insertion + src[j:]

    # 2. Morphology-tolerant lookup: add a stem function and use it as fallback.
    if "function ruStem(" not in src:
        stem_fn = '''
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
'''
        anchor = "const STOP = new Set(["
        src = src.replace(anchor, stem_fn + "\n" + anchor, 1)

        # Use ruLookup in tokenize
        src = src.replace(
            "      const mapped = RU_EN[w];\n      if (mapped) for (const t of mapped.split(/\\s+/)) if (t) out.push(t);",
            "      const mapped = ruLookup(w);\n      if (mapped) for (const t of mapped.split(/\\s+/)) if (t) out.push(t);",
            1,
        )

    io.open(DB, "w", encoding="utf-8", newline="\n").write(src)
    print(f"added {len(added)} entries; stemmer present: {'ruStem' in src}")


if __name__ == "__main__":
    main()

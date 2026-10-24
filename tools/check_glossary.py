#!/usr/bin/env python3
"""Find Russian Unreal Engine words the glossary does not cover.

Reads the RU_EN map out of lib/db.js, then checks a broad list of words a
Russian-speaking Unreal developer is likely to type. Anything missing is
reported so the glossary can be topped up deliberately, instead of being
discovered when a query silently returns nothing.

Usage:  python tools/check_glossary.py [--base <dir>]
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dbpaths import base_from_argv

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_JS = os.path.join(PLUGIN_ROOT, "lib", "db.js")


def load_glossary():
    src = io.open(DB_JS, encoding="utf-8").read()
    i = src.find("const RU_EN = {")
    if i < 0:
        raise SystemExit("RU_EN map not found in lib/db.js")
    j = src.find("};", i)
    block = src[i:j]
    return dict(re.findall(r"'([^']+)':\s*'([^']*)'", block))


# Words grouped by area. Not exhaustive — a representative slice of what a
# Russian-speaking UE developer actually types.
CANDIDATES = {
    "действия": """создать создать создание сделай сделать удалить удаление изменить изменение
        получить найти найтись установить настройка настроить добавить добавить убрать
        открыть закрыть сохранить сохранение загрузить загрузка запустить запуск остановить
        включить выключить переключить выбрать выделить копировать вставить переименовать
        проверить проверка исправить починить сломать обновить обновление""",
    "объекты": """актор актёр актора актеров актёры персонаж персонажа персонажи
        уровень уровня уровни левел сцена сцены мир мира
        камера камеры свет света освещение тень тени тени
        меш меша меши мешей модель модели геометрия полигон полигоны вершина вершины
        материал материалы материала материалу текстура текстуры текстур
        скелет скелета кости кость анимация анимации анимацию анимационный
        блюпринт блюпринта блюпринты блюпринтов блюпринте голубой
        ассет ассеты ассета ресурс ресурсы папка папки каталог
        звук звука звуки аудио музыка музыки шум
        частицы эффект эффекты ниагара
        физика коллизия коллизии столкновение столкновения пересечение
        интерфейс меню виджет виджеты кнопка кнопки панель окно
        сеть сетевой репликация мультиплеер сервер клиент
        ввод управление клавиша клавиши кнопка мышь
        проект проекта сборка билд компиляция ошибка ошибки
        оптимизация производительность лаг лаги фпс кадры
        шейдер шейдеры шейдера постобработка туман вода дождь снег огонь взрыв
        ландшафт ландшафта террейн растительность трава
        оружие оружия персонаж персонажа движение перемещение прыжок
        инвентарь предмет предметы урон здоровье способность способности
        ии враг враги навмеш навигация путь пути
        таймлайн событие события функция функции переменная переменные
        макрос библиотека класс классы класса структура перечисление
        система системы подсистема плагин плагины модуль пакет
        метазвук кварц секвенсор синематика рендер рендеринг отрисовка
        люмен нанит виртуальная развертка нормали
        морф блендшейп риг риггинг контролриг ретаргет ретаргетинг
        кривая кривые график нода ноды узел узлы пин контент браузер
        редактор настройки конфигурация консоль команда лог версия миграция
        упаковка упаковать тест тесты отладка дебаг профилирование""",
    "служебное": """как что где почему зачем когда какой какие который которая
        можно нужно надо нельзя есть нет это этот эта эти
        через для при на в с и или не к у от до по из
        лучший лучше проще простой быстрый быстрее медленный
        пример примеры способ способы вариант варианты""",
}


def main():
    ru_en = load_glossary()
    print(f"glossary size: {len(ru_en)} entries\n")

    total_missing = 0
    for group, words in CANDIDATES.items():
        uniq = sorted(set(w for w in words.split() if w))
        missing = [w for w in uniq if w not in ru_en]
        covered = len(uniq) - len(missing)
        print(f"{group}: {covered}/{len(uniq)} covered, {len(missing)} missing")
        if missing:
            # Print in chunks so the console stays readable.
            for i in range(0, len(missing), 10):
                print("    " + " ".join(missing[i:i + 10]))
        total_missing += len(missing)

    print(f"\ntotal missing: {total_missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

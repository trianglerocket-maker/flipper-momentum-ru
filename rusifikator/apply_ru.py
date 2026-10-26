# -*- coding: utf-8 -*-
"""
Русификация Momentum: накладывается на ЧИСТЫЕ исходники (каждый запуск сначала
возвращает их через git), поэтому скрипт можно гонять повторно после правок словаря.

1. шрифты с кириллицей (make_fonts.py)
2. текстовый движок под UTF-8 (patch_gui.py)
3. надписи на экране (ru_dict.RU / OVERRIDE) — только литералы в функциях вывода
4. русские подписи приложений в главном меню и списке настроек (ru_dict.APP_NAMES)

Запуск: python apply_ru.py [путь к Momentum]
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import make_fonts  # noqa: E402
import patch_gui  # noqa: E402
from ru_dict import APP_NAMES, OVERRIDE, RU  # noqa: E402
from ui_strings import find_sites, iter_files  # noqa: E402

FW = sys.argv[1] if len(sys.argv) > 1 else 'momentum-firmware'


def restore():
    subprocess.run(['git', '-C', FW, 'checkout', '--', 'applications', 'lib/u8g2', 'scripts/fbt'], check=True)
    # приложения набора Momentum — отдельный git (подмодуль applications/external)
    subprocess.run(['git', '-C', os.path.join(FW, 'applications', 'external'), 'checkout', '--', '.'],
                   check=True)


SPEC = re.compile(r'%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|z|j|t)?[diouxXeEfgGcspn%]')


def load_ext():
    """Переводы приложений набора: ext_tr/out_*.json, ключ '<app>|<english>'.
    Строка, где потерян форматный код или есть недопустимые символы, остаётся английской."""
    ext, bad = {}, 0
    for i in range(1, 100):
        path = os.path.join(HERE, 'ext_tr', f'out_{i}.json')
        if not os.path.exists(path):
            continue
        for key, ru in json.load(open(path, encoding='utf-8')).items():
            en = key.split('|', 1)[1]
            ok = (SPEC.findall(en) == SPEC.findall(ru) and ru.count('\\n') <= en.count('\\n')
                  and '"' not in ru.replace('\\"', '') and not set(ru) & set('ёЁ«»—…'))
            if ok:
                ext[key] = ru
            else:
                bad += 1
    return ext, bad


def translate_ext():
    ext, bad = load_ext()
    if not ext:
        print('приложения набора: переводов нет, пропуск')
        return
    root = os.path.join(FW, 'applications', 'external')
    games_path = os.path.join(HERE, 'ext_tr', 'games.txt')
    games = set(open(games_path, encoding='utf-8').read().split()) if os.path.exists(games_path) else set()
    files = sites = 0
    for app in sorted(os.listdir(root)):
        if app in games:          # игры не переводятся (решение Игоря)
            continue
        for dirpath, _, names in os.walk(os.path.join(root, app)):
            for name in names:
                if not name.endswith(('.c', '.h', '.cpp')):
                    continue
                path = os.path.join(dirpath, name)
                text = open(path, encoding='utf-8', errors='surrogateescape', newline='').read()
                reps = [(s, e, ext[f'{app}|{raw}']) for func, s, e, raw in find_sites(text)
                        if f'{app}|{raw}' in ext and ext[f'{app}|{raw}'] != raw]
                if not reps:
                    continue
                for s, e, ru in sorted(reps, reverse=True):
                    text = text[:s] + '"' + ru + '"' + text[e:]
                open(path, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(text)
                files += 1
                sites += len(reps)
    print(f'приложения набора: {sites} мест в {files} файлах (отбраковано переводов: {bad})')


def translate():
    files = sites = 0
    for path in iter_files(FW):
        text = open(path, encoding='utf-8', newline='').read()
        reps = []
        for func, s, e, raw in find_sites(text):
            ru = OVERRIDE.get(f'{func}|{raw}', RU.get(raw))
            if ru is not None and ru != raw:
                reps.append((s, e, ru))
        if not reps:
            continue
        for s, e, ru in sorted(reps, reverse=True):
            text = text[:s] + '"' + ru + '"' + text[e:]
        open(path, 'w', encoding='utf-8', newline='').write(text)
        files += 1
        sites += len(reps)
    print(f'надписи: {sites} мест в {files} файлах')


def load_ext2():
    """Вторая волна: ext2_tr/out_*.json, ключ '<NAME|ARR|FMT>|<app>|<english>'."""
    import glob
    tr, bad = {}, 0
    for path in sorted(glob.glob(os.path.join(HERE, 'ext2_tr', 'out_*.json'))):
        for key, ru in json.load(open(path, encoding='utf-8')).items():
            kind, app, en = key.split('|', 2)
            ok = (SPEC.findall(en) == SPEC.findall(ru) and ru.count('\\n') <= en.count('\\n')
                  and '"' not in ru.replace('\\"', '') and not set(ru) & set('ёЁ«»—…'))
            if kind == 'NAME':
                ok = ok and len(ru.encode('utf-8')) <= 31 and '\\' not in ru
            if ok:
                tr[key] = ru
            else:
                bad += 1
    return tr, bad


def translate_ext2():
    """Таблицы значений и шаблоны (по точным безопасным местам) + названия программ.
    Выполняется ПЕРВЫМ, на чистых исходниках: позиции ищутся заново той же проверкой."""
    import ext2_prepare as e2
    tr, bad = load_ext2()
    if not tr:
        print('вторая волна: переводов нет, пропуск')
        return
    games = set(open(os.path.join(HERE, 'ext_tr', 'games.txt'), encoding='utf-8').read().split())
    fonts = set(open(os.path.join(HERE, 'ext_tr', 'skipped_custom_fonts.txt'), encoding='utf-8').read().split())
    part6 = {x['app'] for x in json.load(open(os.path.join(HERE, 'ext_tr', 'in_6.json'), encoding='utf-8'))}

    def apply_app(app, repo, prefix):
        rels = subprocess.run(['git', '-C', repo, 'ls-files', prefix], capture_output=True, text=True,
                              check=True).stdout.split('\n')
        raw = {r: open(os.path.join(repo, r), encoding='utf-8', errors='surrogateescape', newline='').read()
               for r in rels if r.endswith(('.c', '.h'))}
        clean = {r: e2.blank_comments(t) for r, t in raw.items()}
        by_file = {}
        for kind, en, ctx, rel, s, e in e2.occurrences(clean):
            ru = tr.get(f'{kind}|{app}|{en}')
            if ru is None or ru == en:
                continue
            # snprintf пишет в буфер фиксированного размера, рассчитанный на английский:
            # русский (2 байта на букву) берём, только если он не длиннее в байтах
            if ctx.startswith('snprintf') and len(ru.encode('utf-8')) > len(en.encode('utf-8')):
                continue
            by_file.setdefault(rel, []).append((s, e, ru))
        n = 0
        for rel, reps in by_file.items():
            text = raw[rel]
            for s, e, ru in sorted(set(reps), reverse=True):
                text = text[:s] + '"' + ru + '"' + text[e:]
            open(os.path.join(repo, rel), 'w', encoding='utf-8', errors='surrogateescape', newline='').write(text)
            n += len(reps)
        return n

    sites = 0
    for prefix in e2.MAIN_FAP:
        sites += apply_app(prefix.split('/')[-1], FW, prefix)
    ext_root = os.path.join(FW, 'applications', 'external')
    names = 0
    for app in sorted(os.listdir(ext_root)):
        if not os.path.isdir(os.path.join(ext_root, app)) or app in games or app in part6:
            continue
        if app not in fonts:
            sites += apply_app(app, ext_root, app)
        for dirpath, _, files in os.walk(os.path.join(ext_root, app)):
            if 'application.fam' not in files:
                continue
            fam = os.path.join(dirpath, 'application.fam')
            t = open(fam, encoding='utf-8', errors='surrogateescape', newline='').read()
            for key, ru in tr.items():
                kind, a, en = key.split('|', 2)
                if kind == 'NAME' and a == app and ru != en and f'name="{en}"' in t:
                    t = t.replace(f'name="{en}"', f'name="{ru}"')
                    names += 1
            open(fam, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(t)
    print(f'вторая волна: {sites} мест (таблицы и шаблоны), {names} названий программ; отбраковано {bad}')


def patch_build_scripts():
    """Сборщик (на ПК) читал описания приложений в кодировке Windows и пускал в название
    программы только латиницу. Русские названия (<=31 байта UTF-8, проверено при загрузке
    переводов) требуют UTF-8. На приборе название — обычная строка с нулём в конце."""
    edits = {
        os.path.join(FW, 'scripts', 'fbt', 'appmanifest.py'): [
            ('with open(app_manifest_path, "rt") as manifest_file:',
             'with open(app_manifest_path, "rt", encoding="utf-8") as manifest_file:')],
        os.path.join(FW, 'scripts', 'fbt', 'elfmanifest.py'): [
            ('bytes(self.name.encode("ascii")),', 'bytes(self.name.encode("utf-8")),')],
    }
    for path, reps in edits.items():
        src = open(path, encoding='utf-8', newline='').read()
        for old, new in reps:
            assert old in src, (os.path.basename(path), old)
            src = src.replace(old, new)
        open(path, 'w', encoding='utf-8', newline='').write(src)
    print('сборщик: описания приложений и названия в UTF-8')


def c_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def patch_loader_menu():
    path = os.path.join(FW, 'applications', 'services', 'loader', 'loader_menu.c')
    src = open(path, encoding='utf-8', newline='').read()
    table = ''.join(f'        {{{c_str(en)}, {c_str(ru)}}},\n' for en, ru in APP_NAMES.items() if en != ru)
    helper = (
        '\n// Русская подпись пункта меню. Внутреннее имя приложения (по нему оно\n'
        '// запускается и хранится в списке меню) не меняется.\n'
        'static const char* ru_app_label(const char* name) {\n'
        '    static const char* const labels[][2] = {\n' + table +
        '    };\n'
        '    for(size_t i = 0; i < COUNT_OF(labels); i++) {\n'
        '        if(strcmp(name, labels[i][0]) == 0) return labels[i][1];\n'
        '    }\n'
        '    return name;\n'
        '}\n')
    edits = [
        ('\nstatic void loader_menu_add_app_entry(', helper + '\nstatic void loader_menu_add_app_entry('),
        ('''    menu_add_item(
        app->primary_menu,
        name,
        icon,''', '''    menu_add_item(
        app->primary_menu,
        ru_app_label(name),
        icon,'''),
        ('''        app->primary_menu,
        LOADER_APPLICATIONS_NAME,''', '''        app->primary_menu,
        ru_app_label(LOADER_APPLICATIONS_NAME),'''),
        ('''        last->name,''', '''        ru_app_label(last->name),'''),
        ('''            FLIPPER_SETTINGS_APPS[i].name,
            i,''', '''            ru_app_label(FLIPPER_SETTINGS_APPS[i].name),
            i,'''),
    ]
    for old, new in edits:
        assert src.count(old) == 1, ('loader_menu.c', old[:60])
        src = src.replace(old, new)
    open(path, 'w', encoding='utf-8', newline='').write(src)
    print('главное меню: русские подписи приложений')


def main():
    restore()
    patch_build_scripts()
    translate_ext2()   # первым: по чистым исходникам
    make_fonts.FW = FW
    make_fonts.FONTS_C = os.path.join(FW, 'lib', 'u8g2', 'u8g2_fonts.c')
    make_fonts.main()
    patch_gui.main(FW)
    translate()      # до правки меню: литерал "Settings" в loader_menu.c переводится словарём
    patch_loader_menu()
    translate_ext()


if __name__ == '__main__':
    main()

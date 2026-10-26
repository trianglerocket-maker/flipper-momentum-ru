# -*- coding: utf-8 -*-
"""
Вторая волна перевода: то, что не попало в вызовы вывода напрямую.

A  NAME — названия программ меню «Приложения» (application.fam name=, apptype EXTERNAL).
B  ARR  — таблицы строк (const char* x[] = {...}), которые используются ТОЛЬКО внутри
          вызовов вывода на экран (иначе таблица не трогается: там могут быть ключи файлов).
C  FMT  — шаблоны furi_string_printf / furi_string_cat_printf / snprintf, результат которых
          уходит на экран и НИГДЕ не попадает в файл, сравнение или разбор.
          Файлы *_render.c приложения NFC — целиком (они только рисуют сведения о карте).

Только код приложений на карте (.fap): встроенные в прошивку части (Sub-GHz, Архив, службы,
часы, FindMy, updater) не трогаются — у прошивки нет места.
Игры, приложения со своими шрифтами и часть 6 первой волны не трогаются.
Выход: ext2_tr/in_N.json — [{"key", "app", "kind", "en", "ctx"}].
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ui_strings import UI_FUNCS, blank_comments, call_args_span  # noqa: E402

FW = 'momentum-firmware'
EXT = os.path.join(FW, 'applications', 'external')
OUT = os.path.join(HERE, 'ext2_tr')
PART = 450

MAIN_FAP = ['applications/main/' + a for a in
            ('bad_usb', 'gpio', 'ibutton', 'infrared', 'lfrfid', 'momentum_app', 'nfc', 'onewire', 'u2f')]
MAIN_FAP += ['applications/settings/' + a for a in
             ('about', 'bt_settings_app', 'desktop_settings', 'dolphin_passport', 'expansion_settings_app',
              'input_settings_app', 'notification_settings', 'power_settings_app', 'storage_settings', 'system')]
MAIN_FAP += ['applications/system/hid_app', 'applications/system/js_app']

ARRAY = re.compile(r'(?:static\s+)?const\s+char\s*\*\s*(?:const\s+)?(\w+)\s*\[[^\]]*\]\s*=\s*\{(.*?)\};', re.S)
LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')
PRINTF = re.compile(r'\b(furi_string_printf|furi_string_cat_printf|snprintf)\s*\(')
SPEC = re.compile(r'%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|z|j|t)?[diouxXeEfgGcspn%]')
WORD = re.compile(r'[A-Za-z]{3,}')
RISKY = re.compile(r'\b(flipper_format_\w+|storage_\w+|stream_\w+|file_\w+|furi_string_cmp\w*|furi_string_equal\w*|'
                   r'furi_string_search\w*|furi_string_start_with\w*|furi_string_end_with\w*|strcmp|strncmp|'
                   r'strcasecmp|strncasecmp|strstr|sscanf|atoi|strtol\w*|\w*_save\w*|\w*_load\w*|\w*_write\w*|'
                   r'\w*_parse\w*|FURI_LOG_\w|furi_log\w*|\w*_send\w*|\w*_tx\w*|uart_\w+|cli_\w+|printf)\s*\(')
UI_CALL = re.compile(r'\b(' + '|'.join(sorted(UI_FUNCS + ['text_box_set_text', 'furi_string_get_cstr'],
                                             key=len, reverse=True)) + r')\s*\(')


def spans(text, regex):
    res = []
    for m in regex.finditer(text):
        close = call_args_span(text, m.end() - 1)
        if close > 0:
            res.append((m.end(), close))
    return res


def inside(pos, sp):
    return any(a <= pos < b for a, b in sp)


def git_show(repo, rel):
    return subprocess.run(['git', '-C', repo, 'show', 'HEAD:' + rel], capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


def is_text(s):
    plain = SPEC.sub('', s)
    return bool(WORD.search(plain)) and not s.startswith(('/', '.', '%s/', 'http')) and '/ext/' not in s


def app_sources(repo, prefix):
    rels = subprocess.run(['git', '-C', repo, 'ls-files', prefix], capture_output=True, text=True,
                          check=True).stdout.split('\n')
    return {r: blank_comments(git_show(repo, r)) for r in rels if r.endswith(('.c', '.h'))}


def scan_app(app, srcs):
    seen, out = set(), []
    for kind, en, ctx, rel, s, e in occurrences(srcs):
        key = f'{kind}|{app}|{en}'
        if key not in seen:
            seen.add(key)
            out.append({'key': key, 'app': app, 'kind': kind, 'en': en, 'ctx': ctx})
    return out


def occurrences(srcs):
    """Все безопасные места: (kind, en, ctx, файл, начало, конец литерала с кавычками).
    srcs — тексты без комментариев (позиции совпадают с исходником)."""
    items = []
    ui_spans = {r: spans(t, UI_CALL) for r, t in srcs.items()}
    risky_spans = {r: spans(t, RISKY) for r, t in srcs.items()}
    # B: таблицы, которые встречаются только внутри вызовов вывода
    for rel, t in srcs.items():
        for m in ARRAY.finditer(t):
            name, body = m.group(1), m.group(2)
            ok, used = True, False
            ident = re.compile(r'\b' + re.escape(name) + r'\b')
            for r2, t2 in srcs.items():
                for u in ident.finditer(t2):
                    if r2 == rel and m.start() <= u.start() < m.end():
                        continue                      # само определение
                    before = t2[max(0, u.start() - 40):u.start()]
                    if re.search(r'(sizeof|COUNT_OF)\s*\(\s*$', before):
                        continue
                    if inside(u.start(), ui_spans[r2]) and not inside(u.start(), risky_spans[r2]):
                        used = True
                    else:
                        ok = False
            if ok and used:
                for lm in LIT.finditer(body):
                    if is_text(lm.group(1)):
                        a = m.start(2) + lm.start()
                        items.append(('ARR', lm.group(1), f'{name}[] in {os.path.basename(rel)}',
                                      rel, a, a + len(lm.group(0))))
    # C: шаблоны, результат которых уходит на экран
    for rel, t in srcs.items():
        render = rel.endswith('_render.c') and '/nfc/' in rel.replace('\\', '/')
        for m in PRINTF.finditer(t):
            close = call_args_span(t, m.end() - 1)
            if close < 0:
                continue
            args = t[m.end():close]
            target = args.split(',', 1)[0].strip()
            lit = LIT.search(args)
            if not lit or not is_text(lit.group(1)):
                continue
            if not render:
                if not target or not re.match(r'^[\w\->.\[\]]+$', target):
                    continue
                tgt = re.compile(re.escape(target) + r'(?![\w])')
                shown = risky = False
                for u in tgt.finditer(t):
                    if inside(u.start(), risky_spans[rel]):
                        risky = True
                    elif inside(u.start(), ui_spans[rel]):
                        shown = True
                if risky or not shown:
                    continue
            a = m.end() + lit.start()
            items.append(('FMT', lit.group(1), f'{m.group(1)} in {os.path.basename(rel)}',
                          rel, a, a + len(lit.group(0))))
    return items


def fam_names(app_dir):
    names = []
    for r, _, fs in os.walk(app_dir):
        for f in fs:
            if f == 'application.fam':
                t = open(os.path.join(r, f), encoding='utf-8', errors='replace').read()
                for block in re.split(r'\bApp\s*\(', t)[1:]:
                    nm = re.search(r'\bname\s*=\s*"([^"]+)"', block)
                    ty = re.search(r'apptype\s*=\s*FlipperAppType\.(\w+)', block)
                    if nm and ty and ty.group(1) == 'EXTERNAL':
                        names.append(nm.group(1))
    return names


def main():
    games = set(open(os.path.join(HERE, 'ext_tr', 'games.txt'), encoding='utf-8').read().split())
    fonts = set(open(os.path.join(HERE, 'ext_tr', 'skipped_custom_fonts.txt'), encoding='utf-8').read().split())
    part6 = {x['app'] for x in json.load(open(os.path.join(HERE, 'ext_tr', 'in_6.json'), encoding='utf-8'))}
    all_items = []
    for prefix in MAIN_FAP:
        all_items += scan_app(prefix.split('/')[-1], app_sources(FW, prefix))
    for app in sorted(os.listdir(EXT)):
        if not os.path.isdir(os.path.join(EXT, app)) or app in games or app in part6:
            continue
        if app not in fonts:
            all_items += scan_app(app, app_sources(EXT, app))
        for nm in fam_names(os.path.join(EXT, app)):
            all_items.append({'key': f'NAME|{app}|{nm}', 'app': app, 'kind': 'NAME', 'en': nm,
                              'ctx': 'app name in Apps menu, max 15 Russian letters'})
    os.makedirs(OUT, exist_ok=True)
    by_app = {}
    for it in all_items:
        by_app.setdefault(it['app'], []).append(it)
    parts, cur = [], []
    for app, items in by_app.items():
        if cur and len(cur) + len(items) > PART:
            parts.append(cur)
            cur = []
        cur += items
    if cur:
        parts.append(cur)
    for i, p in enumerate(parts, 1):
        json.dump(p, open(os.path.join(OUT, f'in_{i}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    kinds = {}
    for it in all_items:
        kinds[it['kind']] = kinds.get(it['kind'], 0) + 1
    print('всего', len(all_items), kinds, 'частей', len(parts), [len(p) for p in parts])


if __name__ == '__main__':
    main()

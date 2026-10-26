# -*- coding: utf-8 -*-
"""
Поиск надписей интерфейса в исходниках Momentum.

Берутся ТОЛЬКО строковые литералы, переданные прямо в функции вывода на экран
(меню, кнопки, окна, заголовки, canvas_draw_str…). Строки для файлов, протоколов,
путей и т.п. не трогаются — значит, перевод не может сломать сохранение/чтение данных.

find_sites(text) -> [(func, start, end, literal_text)] — позиции литералов в тексте файла.
"""
import os
import re

UI_FUNCS = [
    'submenu_add_item', 'submenu_add_item_ex', 'submenu_add_lockable_item', 'submenu_set_header',
    'variable_item_list_add', 'variable_item_set_current_value_text', 'variable_item_list_set_header',
    'widget_add_string_element', 'widget_add_string_multiline_element', 'widget_add_text_box_element',
    'widget_add_text_scroll_element', 'widget_add_button_element',
    'dialog_ex_set_header', 'dialog_ex_set_text', 'dialog_ex_set_left_button_text',
    'dialog_ex_set_center_button_text', 'dialog_ex_set_right_button_text',
    'dialog_message_set_header', 'dialog_message_set_text', 'dialog_message_set_buttons',
    'popup_set_header', 'popup_set_text',
    'canvas_draw_str', 'canvas_draw_str_aligned',
    'elements_button_left', 'elements_button_right', 'elements_button_center',
    'elements_button_up', 'elements_button_down',
    'elements_multiline_text', 'elements_multiline_text_aligned', 'elements_multiline_text_framed',
    'elements_text_box', 'elements_bubble_str', 'elements_scrollable_text_line_str',
    'text_input_set_header_text', 'byte_input_set_header_text', 'number_input_set_header_text',
    'button_menu_add_item', 'button_panel_add_label', 'menu_add_item',
    'text_box_set_text', 'file_browser_set_header', 'loading_set_text',
]

_CALL = re.compile(r'\b(' + '|'.join(sorted(UI_FUNCS, key=len, reverse=True)) + r')\s*\(')
_LETTER = re.compile(r'[A-Za-z]')


def blank_comments(t):
    """Заменить комментарии пробелами (позиции символов сохраняются)."""
    out, i, n = list(t), 0, len(t)
    while i < n:
        c = t[i]
        if c == '"' or c == "'":
            q = c
            i += 1
            while i < n and t[i] != q:
                i += 2 if t[i] == '\\' else 1
            i += 1
        elif t.startswith('//', i):
            j = t.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = ' '
            i = j
        elif t.startswith('/*', i):
            j = t.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != '\n':
                    out[k] = ' '
            i = j
        else:
            i += 1
    return ''.join(out)


def call_args_span(t, open_pos):
    """Конец аргументов вызова (позиция закрывающей скобки)."""
    depth, i, n = 0, open_pos, len(t)
    while i < n:
        c = t[i]
        if c == '"' or c == "'":
            q = c
            i += 1
            while i < n and t[i] != q:
                i += 2 if t[i] == '\\' else 1
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def literals_in(t, a, b):
    """Строковые литералы в t[a:b] -> [(start, end, raw_inner)]; end — после кавычки."""
    res, i = [], a
    while i < b:
        c = t[i]
        if c == "'":
            i += 1
            while i < b and t[i] != "'":
                i += 2 if t[i] == '\\' else 1
            i += 1
        elif c == '"':
            j = i + 1
            while j < b and t[j] != '"':
                j += 2 if t[j] == '\\' else 1
            res.append((i, j + 1, t[i + 1:j]))
            i = j + 1
        else:
            i += 1
    return res


def group_adjacent(t, lits):
    """Склеить соседние литералы "a" "b" (между ними только пробелы)."""
    groups = []
    for s, e, raw in lits:
        if groups and t[groups[-1][-1][1]:s].strip() == '':
            groups[-1].append((s, e, raw))
        else:
            groups.append([(s, e, raw)])
    return groups


def find_sites(text):
    clean = blank_comments(text)
    sites = []
    for m in _CALL.finditer(clean):
        open_pos = m.end() - 1
        close = call_args_span(clean, open_pos)
        if close < 0:
            continue
        for g in group_adjacent(clean, literals_in(clean, open_pos + 1, close)):
            raw = ''.join(x[2] for x in g)
            if not _LETTER.search(raw) or raw.startswith('/') or raw.startswith('\\e'):
                continue
            sites.append((m.group(1), g[0][0], g[-1][1], raw))
    return sites


SCOPE = [
    'applications/main', 'applications/services', 'applications/settings', 'applications/system',
]
SKIP_DIRS = ('/cli', '/rpc', '/tests', '/unit_tests', 'js_app/modules', 'js_app/examples')


def iter_files(fw):
    for top in SCOPE:
        for root, dirs, files in os.walk(os.path.join(fw, top)):
            r = root.replace('\\', '/')
            if any(s in r for s in SKIP_DIRS):
                continue
            for f in files:
                if f.endswith(('.c', '.h', '.cpp')):
                    yield os.path.join(root, f)

# -*- coding: utf-8 -*-
"""
Добавить кириллицу в шрифты прошивки Momentum.

- FontPrimary   (u8g2_font_helvB08_tr)      — латиница прибора + кириллица из cyr_glyphs.PRIMARY
- FontSecondary (u8g2_font_haxrcorp4089_tr) — латиница прибора + кириллица из готового
  u8g2_font_haxrcorp4089_t_cyrillic (u8g2) + дорисованные э/Ё/ё

Массивы заменяются в lib/u8g2/u8g2_fonts.c под ТЕМИ ЖЕ именами: вся прошивка и
приложения, которые зовут эти шрифты, получают кириллицу без других правок.
Метрики шрифтов (высота строки и т.п.) не меняются — вёрстка экранов не едет.
Исходный u8g2_fonts.c сохраняется рядом (orig_u8g2_fonts.c) и всегда берётся как основа.

Запуск: python make_fonts.py <путь к Momentum>
"""
import os
import re
import shutil
import sys

from PIL import Image

from cyr_glyphs import ALIASES, PRIMARY, SECONDARY_EXTRA
from u8g2font import decode_font, encode_font, read_c_font, render, to_c

HERE = os.path.dirname(os.path.abspath(__file__))
FW = sys.argv[1] if len(sys.argv) > 1 else 'momentum-firmware'
FONTS_C = os.path.join(FW, 'lib', 'u8g2', 'u8g2_fonts.c')
ORIG = os.path.join(HERE, 'orig_u8g2_fonts.c')
UPSTREAM = os.path.join(HERE, 'u8g2_cyrillic_fonts.c')

# Буквы, которые должны быть в шрифте; двойники латиницы (ALIASES) прошивка подставляет сама.
CYR = [chr(c) for c in range(0x410, 0x450) if chr(c) not in ALIASES]


def drawn(ch, y, rows):
    """Глиф из рисунка: пустые поля обрезаются, сдвиг курсора = ширина рисунка + 1."""
    w = len(rows[0])
    assert all(len(r) == w for r in rows), ch
    cols = [c for c in range(w) if any(r[c] == '#' for r in rows)]
    c0, c1 = cols[0], cols[-1]
    used = [i for i, r in enumerate(rows) if '#' in r]
    r0, r1 = used[0], used[-1]
    bm = [''.join('1' if r[c] == '#' else '0' for c in range(c0, c1 + 1)) for r in rows[r0:r1 + 1]]
    return dict(enc=ord(ch), w=c1 - c0 + 1, h=r1 - r0 + 1, x=c0,
                y=y + (len(rows) - 1 - r1), d=w + 1, bitmap=bm)


def build_primary():
    h, g = decode_font(read_c_font(ORIG, 'u8g2_font_helvB08_tr'))
    for ch, (y, rows) in PRIMARY.items():
        g[ord(ch)] = drawn(ch, y, rows)
    missing = [c for c in CYR if ord(c) not in g]
    assert not missing, ('Primary без букв', missing)
    return h, g


def build_secondary():
    h, g = decode_font(read_c_font(ORIG, 'u8g2_font_haxrcorp4089_tr'))
    _, cg = decode_font(read_c_font(UPSTREAM, 'u8g2_font_haxrcorp4089_t_cyrillic'))
    for k, v in cg.items():
        if 0x400 <= k < 0x460 and chr(k) not in ALIASES:
            g[k] = v
        elif chr(k) in ALIASES:
            lat = g[ord(ALIASES[chr(k)])]
            same = all(lat[f] == v[f] for f in ('w', 'h', 'x', 'y', 'd', 'bitmap'))
            assert same or chr(k) in 'Ёё', ('двойник отличается от латиницы', chr(k))
    for ch, (y, rows) in SECONDARY_EXTRA.items():
        g[ord(ch)] = drawn(ch, y, rows)
    missing = [c for c in CYR if ord(c) not in g]
    assert not missing, ('Secondary без букв', missing)
    return h, g


def replace_array(src, name, c_code):
    pat = re.compile(r'const uint8_t ' + re.escape(name) + r'\[\d+\] U8G2_FONT_SECTION\("' +
                     re.escape(name) + r'"\) =.*?;\n', re.S)
    assert len(pat.findall(src)) == 1, name
    return pat.sub(lambda m: c_code, src)


def with_aliases(g):
    """Глифы так, как их увидит прибор: двойники берутся из латиницы."""
    g = dict(g)
    for cyr, lat in ALIASES.items():
        g.setdefault(ord(cyr), g[ord(lat)])
    return g


def preview(fonts, path):
    lines = []
    for title, (h, g) in fonts:
        g = with_aliases(g)
        for text in ['Настройки  Архив  Приложения',
                     'Сохранить? Удалить файл',
                     'Частота: 433.92 МГц  Sub-GHz',
                     'ЁЖЗИЙЛПУФЦЧШЩЪЫЬЭЮЯ Бб Дд',
                     'ёжзийлпуфцчшщъыьэюя бвгдк']:
            lines.append(render(g, h, text))
            lines.append(['.' * 10] * 2)
    width = max(len(r[0]) for r in lines)
    rows = [r.ljust(width, '.') for block in lines for r in block]
    sc = 4
    im = Image.new('RGB', (width * sc, len(rows) * sc), (255, 130, 0))
    px = im.load()
    for yy, r in enumerate(rows):
        for xx, ch in enumerate(r):
            if ch in '#?':
                for a in range(sc):
                    for b in range(sc):
                        px[xx * sc + a, yy * sc + b] = (0, 0, 0)
    im.save(path)


def main():
    if not os.path.exists(ORIG):
        shutil.copy(FONTS_C, ORIG)
    src = open(ORIG, 'r', encoding='latin-1').read()
    built = []
    for name, (h, g) in [('u8g2_font_helvB08_tr', build_primary()),
                         ('u8g2_font_haxrcorp4089_tr', build_secondary())]:
        font = encode_font(g, h)          # внутри — проверка поиском и распаковкой u8g2
        src = replace_array(src, name, to_c(name, font))
        built.append((name, (h, g)))
        print(f'{name}: глифов {len(g)}, {len(font)} байт')
    with open(FONTS_C, 'w', encoding='latin-1', newline='\n') as fh:
        fh.write(src)
    preview(built, os.path.join(HERE, 'fonts_preview.png'))
    print('записано в', FONTS_C)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
Портрет BMO для паспорта Flipper Zero: 3 картинки 46x49, 1 бит.

Компоновка повторяет родной портрет дельфина (образцы — ..\\passport_ref):
рамка со скруглёнными углами, фон в шахматную клетку, фигура белая
с чёрным контуром, крупно, уходит за нижний край рамки.

BMO в три четверти: лицевая панель с экраном-лицом, узкий левый бок
с решёткой динамика, под экраном щель картриджа и кнопка, ниже крестовина
и кнопки (треугольник, малая и большая круглые) — как на модели из мультфильма.

Настроения (как BMO выражает их в «Adventure Time»):
- happy — глаза-точки, открытый рот-«D» с языком (смеётся);
- okay  — глаза-точки, лёгкая улыбка;
- bad   — грустные бровки (внутренние концы вверх), рот дугой вниз.

Запуск: python _make_bmo_passport.py
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), 'passport_ref')
W, H = 46, 49


def frame_and_background():
    """Рамка паспорта и шахматный фон — как у родных картинок."""
    c = np.zeros((H, W), bool)
    yy, xx = np.mgrid[0:H, 0:W]
    c[(xx + yy) % 2 == 0] = True                       # шахматка
    c[0, 3:43] = c[48, 3:43] = True                    # верх/низ рамки
    c[3:46, 0] = c[3:46, 45] = True                    # бока
    for (x, y) in [(2, 1), (3, 1), (1, 2), (2, 2), (0, 3), (1, 3)]:   # скругления
        c[y, x] = True                                 # верх-лево
        c[H - 1 - y, x] = True                         # низ-лево
    for (x, y) in [(41, 1), (42, 1), (43, 1), (42, 2), (43, 2), (44, 2), (43, 3), (44, 3), (45, 3)]:
        c[y, x] = True                                 # верх-право (толще — «тень»)
        c[H - 1 - y, x] = True                         # низ-право
    for (x, y) in [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (0, 2)]:  # вне скругления
        c[y, x] = c[H - 1 - y, x] = False
    for (x, y) in [(43, 0), (44, 0), (45, 0), (44, 1), (45, 1), (45, 2)]:
        c[y, x] = c[H - 1 - y, x] = False
    return c


def check_frame_against_ref(base):
    """Рамка и фон должны совпасть с образцом везде, где на образце нет дельфина."""
    ref = np.array(Image.open(os.path.join(REF, 'passport_happy_46x49.png')).convert('L')) < 128
    diff = np.argwhere(base != ref)
    # дельфин занимает середину и низ-лево; верхние 5 строк и правые 2 столбца — только фон
    zone = [(y, x) for y, x in diff if y <= 4 or x >= 44 or y == 48]
    assert not zone, f'рамка/фон не совпали с образцом: {zone[:10]}'


def put(c, pts, v=True):
    for x, y in pts:
        if 0 <= x < W and 0 <= y < H:
            c[y, x] = v


def line(c, x0, y0, x1, y1, v=True):
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    put(c, [(int(np.floor(x0 + (x1 - x0) * i / n + .5)), int(np.floor(y0 + (y1 - y0) * i / n + .5)))
            for i in range(n + 1)], v)


def sprite(c, x0, y0, rows):
    """Нарисовать по шаблону: '#' — чёрный, '.' — белый, ' ' — не трогать."""
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == '#':
                put(c, [(x0 + dx, y0 + dy)], True)
            elif ch == '.':
                put(c, [(x0 + dx, y0 + dy)], False)


def body(c):
    # левый бок (три четверти): верхняя кромка уходит назад-вниз
    side_top = {}
    for i in range(6):                                  # x от 10 до 5
        side_top[10 - i] = 5 + rnd(3 * i / 5)
    for x in range(5, 11):
        c[side_top[x]:48, x] = False                    # белая заливка бока
    line(c, 10, 5, 5, 8)                                # верхняя кромка бока
    c[8:48, 5] = True                                   # задняя кромка бока
    put(c, [(7, 12), (7, 14), (7, 16)])                 # решётка динамика
    # лицевая панель
    c[5:48, 10:42] = False
    c[5, 11:41] = True
    c[6:48, 10] = True
    c[6:48, 41] = True
    # экран
    c[8, 14:38] = c[30, 14:38] = True
    c[9:30, 13] = c[9:30, 38] = True
    # щель картриджа и кнопка рядом
    c[33:35, 14:30] = True
    sprite(c, 33, 33, ['##', '##'])
    # крестовина
    sprite(c, 14, 37, ['  ###  ',
                       '  #.#  ',
                       '###.###',
                       '#.....#',
                       '###.###',
                       '  #.#  ',
                       '  ###  '])
    # две чёрточки под крестовиной
    c[46, 13:16] = c[46, 18:21] = True
    # треугольная кнопка, малая и большая круглые
    sprite(c, 26, 38, ['  #  ',
                       ' ### ',
                       '#####'])
    sprite(c, 33, 36, ['.##.',
                       '#..#',
                       '#..#',
                       '.##.'])
    sprite(c, 31, 41, ['..###..',
                       '.#...#.',
                       '#.....#',
                       '#.....#',
                       '#.....#',
                       '.#...#.',
                       '..###..'])


def rnd(v):
    return int(np.floor(v + .5))


EYE = ['.##.',
       '####',
       '####',
       '.##.']


def eyes(c, dy=0):
    sprite(c, 18, 14 + dy, EYE)
    sprite(c, 30, 14 + dy, EYE)


def face_happy(c):
    eyes(c)
    sprite(c, 20, 21, ['############',
                       '############',
                       '.##########.',
                       '.####..####.',      # светлый язык снизу, как в мультфильме
                       '..##....##..',
                       '...######...'])


def face_okay(c):
    eyes(c)
    sprite(c, 19, 22, ['#............#',
                       '.##........##.',
                       '...########...'])


def face_bad(c):
    eyes(c, dy=1)
    # грустные бровки: внутренние концы выше, наружные — вниз
    sprite(c, 16, 11, ['    ##',
                       '  ##  ',
                       '##    '])
    sprite(c, 30, 11, ['##    ',
                       '  ##  ',
                       '    ##'])
    sprite(c, 20, 23, ['...######...',
                       '.##......##.',
                       '#..........#'])


FACES = {'happy': face_happy, 'okay': face_okay, 'bad': face_bad}


def main():
    base = frame_and_background()
    check_frame_against_ref(base)
    out = {}
    for mood, face in FACES.items():
        c = base.copy()
        body(c)
        face(c)
        out[mood] = c
        Image.fromarray(np.where(c, 0, 255).astype(np.uint8), 'L').convert('1').save(
            os.path.join(HERE, f'passport_{mood}_46x49.png'))
    # превью: образец дельфина и BMO рядом, крупно; второй ряд — в цветах экрана Flipper
    sc, pad = 6, 8
    prev = Image.new('RGB', (3 * (W * sc + pad) + pad, 3 * (H * sc + pad) + pad), (60, 60, 60))
    for i, mood in enumerate(FACES):
        ref = np.array(Image.open(os.path.join(REF, f'passport_{mood}_46x49.png')).convert('L')) < 128
        for j, (arr, fg, bg) in enumerate([(ref, (0, 0, 0), (255, 255, 255)),
                                           (out[mood], (0, 0, 0), (255, 255, 255)),
                                           (out[mood], (0, 0, 0), (255, 130, 0))]):
            rgb = np.where(arr[..., None], np.array(fg, np.uint8), np.array(bg, np.uint8)).astype(np.uint8)
            im = Image.fromarray(rgb, 'RGB').resize((W * sc, H * sc), Image.NEAREST)
            prev.paste(im, (pad + i * (W * sc + pad), pad + j * (H * sc + pad)))
    prev.save(os.path.join(HERE, '_preview.png'))
    print('готово:', ', '.join(f'passport_{m}_46x49.png' for m in FACES))


if __name__ == '__main__':
    main()

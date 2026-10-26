# -*- coding: utf-8 -*-
"""
Генератор анимаций BMO для Flipper Zero (128x64, 1 бит).

Исходники: BMO_source_png/BMO_*.png (рядом с этим скриптом)
Результат: рядом с этим скриптом — папка на каждую анимацию
(frame_N.png + meta.txt), общий manifest.txt и _preview\\ (GIF в цветах Flipper).

Движения взяты из того, как BMO ведёт себя в «Adventure Time»:
- злость — косые бровки-чёрточки над глазами и рот дугой вниз
  (эскиз студии, серия 018 «Beemo - Angry Face Screen»), BMO топает;
- смех — глаза зажмуриваются в дуги, BMO подпрыгивает на каждом «ха»;
- моргание — глаз-точка сплющивается в чёрточку;
- антенн и «пара над головой» у BMO нет — экран и есть лицо.

Запуск: python _make_bmo_anims.py
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'BMO_source_png')
W, H = 128, 64


# ---------- примитивы ----------

def load(name):
    im = Image.open(os.path.join(SRC, f'BMO_{name}.png')).convert('L')
    assert im.size == (W, H), im.size
    return np.array(im) < 128          # True = чёрный пиксель


def crop(img, x0, y0, x1, y1):
    """Часть картинки в прямоугольнике (включительно), обрезанная по чёрным пикселям."""
    sub = img[y0:y1 + 1, x0:x1 + 1]
    ys, xs = np.nonzero(sub)
    return sub[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy(), x0 + xs.min(), y0 + ys.min()


def paste(c, part, dx=0, dy=0):
    spr, x, y = part
    x, y = x + dx, y + dy
    h, w = spr.shape
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x0 < x1 and y0 < y1:
        c[y0:y1, x0:x1] |= spr[y0 - y:y1 - y, x0 - x:x1 - x]


def compose(*parts, dx=0, dy=0):
    c = np.zeros((H, W), bool)
    for p in parts:
        if p is not None:
            paste(c, p, dx, dy)
    return c


def rnd(v):
    return int(np.floor(v + 0.5))


def center(part):
    spr, x, y = part
    return x + spr.shape[1] / 2, y + spr.shape[0] / 2


def at_center(spr, cx, cy):
    return spr, rnd(cx - spr.shape[1] / 2), rnd(cy - spr.shape[0] / 2)


def squash_v(spr, new_h):
    h = spr.shape[0]
    return spr[[min(h - 1, int((i + 0.5) * h / new_h)) for i in range(new_h)]]


def _pick(band, k):
    return {band[int((i + 0.5) * len(band) / k)] for i in range(k)} if k > 0 else set()


def drop_rows(spr, r0, r1, k):
    """Убрать k строк, равномерно из полосы r0..r1 (координаты спрайта)."""
    gone = _pick(list(range(r0, r1 + 1)), k)
    return spr[[r for r in range(spr.shape[0]) if r not in gone]]


def drop_cols(spr, c0, c1, k):
    gone = _pick(list(range(c0, c1 + 1)), k)
    return spr[:, [c for c in range(spr.shape[1]) if c not in gone]]


def dup_rows(spr, r0, r1, k):
    twice = _pick(list(range(r0, r1 + 1)), k)
    rows = []
    for r in range(spr.shape[0]):
        rows.append(r)
        if r in twice:
            rows.append(r)
    return spr[rows]


def bar(w, h=2):
    return np.ones((h, w), bool)


def canvas_part(draw):
    """Нарисовать функцией draw(c) на пустом холсте и вернуть как часть."""
    c = np.zeros((H, W), bool)
    draw(c)
    return c, 0, 0


def thick_line(c, x0, y0, x1, y1, t=2):
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        x = rnd(x0 + (x1 - x0) * i / n)
        y = rnd(y0 + (y1 - y0) * i / n)
        c[max(y, 0):min(y + t, H), max(x, 0):min(x + t, W)] = True


def arc(c, cx, cy, rx, ry, t=2, up=True):
    """Дуга-половина эллипса толщиной t: up=True — «∩», up=False — «∪»."""
    yy, xx = np.mgrid[0:H, 0:W]
    outer = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
    inner = ((xx - cx) / max(rx - t, .1)) ** 2 + ((yy - cy) / max(ry - t, .1)) ** 2 <= 1.0
    half = (yy <= cy) if up else (yy >= cy)
    c[outer & ~inner & half] = True


def ellipse(c, cx, cy, rx, ry):
    yy, xx = np.mgrid[0:H, 0:W]
    c[((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0] = True


def blink_set(part):
    """Глаз-точка: открыт / полуприкрыт / закрыт (чёрточка чуть ниже центра)."""
    spr, x, y = part
    cx, cy = center(part)
    h, w = spr.shape
    half = squash_v(spr, max(3, rnd(h * 0.4)))
    return {
        'open': part,
        'half': at_center(half, cx, cy + 1),
        'closed': at_center(bar(max(2, w - 2)), cx, cy + 1),
    }


def lid_cut(part, top_cut_left, top_cut_right):
    """Веко сверху по наклонной: срезать всё выше линии (левый край -> правый край)."""
    spr, x, y = part
    s = spr.copy()
    w = s.shape[1]
    for col in range(w):
        cut = rnd(top_cut_left + (top_cut_right - top_cut_left) * col / max(w - 1, 1))
        s[:max(cut, 0), col] = False
    return s, x, y


# ---------- анимации ----------
# Каждая функция возвращает (уникальные кадры, порядок кадров, частота кадров).

def anim_smile():
    """Довольный BMO с закрытыми глазами-дугами напевает и покачивается."""
    s = load('smile')
    face = (s, 0, 0)
    dxs = [-2, -1, 0, 1, 2]
    frames = [compose(face, dx=d) for d in dxs]
    idx = {d: i for i, d in enumerate(dxs)}
    seq = [0, 0, 1, 2, 2, 2, 1, 0, -1, -2, -2, -2, -1, 0]
    return frames, [idx[d] for d in seq], 6


def smile_curve(c, cx, x0, y_end, depth):
    """Ровная симметричная улыбка: тонкие края, середина толще на 1 пиксель."""
    hw = cx - x0
    for x in range(x0, int(cx) + 1):
        u2 = ((x - cx) / hw) ** 2
        lo = rnd(y_end + depth * (1 - u2))
        up = rnd(y_end + (depth - 1) * (1 - u2))
        for xx in (x, int(2 * cx) - x):
            c[up:lo + 1, xx] = True


def anim_smirk():
    """Спокойная улыбка: BMO поглядывает вбок, моргает и смотрит обратно.
    Глаза и рот перерисованы: в исходнике у глаз торчали «злые» хвостики,
    а улыбка была кривой."""
    L = canvas_part(lambda c: ellipse(c, 26.5, 35, 5, 5.5))
    R = canvas_part(lambda c: ellipse(c, 103.5, 35, 5, 5.5))
    M = canvas_part(lambda c: smile_curve(c, 66.5, 46, 43, 4))
    L, R = crop(L[0], 0, 0, W - 1, H - 1), crop(R[0], 0, 0, W - 1, H - 1)
    bl, br = blink_set(L), blink_set(R)
    f = [
        compose(L, R, M),                                            # 0 смотрит прямо
        compose(L, R, dx=2) | compose(M),                            # 1 поглядывает
        compose(L, R, dx=4) | compose(M),                            # 2
        compose(bl['half'], br['half'], dx=4) | compose(M),          # 3 моргает
        compose(bl['closed'], br['closed'], dx=4) | compose(M),      # 4
    ]
    order = [0, 0, 0, 0, 1, 2, 2, 2, 2, 3, 4, 3, 2, 2, 2, 1, 0, 0]
    return f, order, 6


def anim_happy():
    """Радостный BMO выкрикивает «Йа-ай!»: рот хлопает, глаза подпрыгивают, моргание."""
    s = load('happy')
    L, R, M = crop(s, 12, 18, 42, 34), crop(s, 88, 18, 118, 34), crop(s, 45, 35, 88, 63)
    mspr, mx, my = M
    band = (43 - my, 48 - my)                    # сплошная тёмная часть рта
    m_mid = (drop_rows(mspr, *band, 3), mx, my)
    m_shut = (drop_rows(mspr, *band, 5), mx, my)
    m_wide = (dup_rows(mspr, *band, 1), mx, my)
    bl, br = blink_set(L), blink_set(R)
    f = [
        compose(L, R, M),                                    # 0
        compose(L, R, dy=1) | compose(m_mid),                # 1
        compose(L, R, dy=1) | compose(m_shut),               # 2
        compose(L, R, dy=-1) | compose(m_wide),              # 3 «Йа-ай!»
        compose(bl['half'], br['half'], M),                  # 4
        compose(bl['closed'], br['closed'], M),              # 5
    ]
    order = [0, 0, 1, 2, 1, 3, 3, 0, 1, 2, 1, 3, 3, 0, 0, 0, 4, 5, 4, 0, 0, 0]
    return f, order, 6


def anim_laugh():
    """Смех: глаза зажмуриваются в дуги, BMO подпрыгивает на каждом «ха»."""
    s = load('laugh')
    L, R, M = crop(s, 12, 20, 42, 36), crop(s, 88, 20, 118, 36), crop(s, 40, 38, 92, 56)
    mspr, mx, my = M
    band = (41 - my, 47 - my)
    m_ha = (drop_rows(mspr, *band, 3), mx, my)
    m_wide = (dup_rows(mspr, *band, 1), mx, my)
    bl, br = blink_set(L), blink_set(R)
    (lx, ly), (rx, ry) = center(L), center(R)

    def arcs(c, lift=0):
        arc(c, lx, ly + 2 - lift, 6.5, 4.5, 2, up=True)
        arc(c, rx, ry + 2 - lift, 6.5, 4.5, 2, up=True)

    eyes_arc = canvas_part(arcs)
    f = [
        compose(L, R, M),                                     # 0 исходник
        compose(bl['half'], br['half'], M),                   # 1 жмурится
        compose(eyes_arc, m_wide, dy=-1),                     # 2 «ХА» — вверх
        compose(eyes_arc, m_ha, dy=0),                        # 3 «ха» — вниз
    ]
    order = [0, 0, 0, 0, 1, 2, 3, 2, 3, 2, 3, 2, 3, 2, 3, 1, 0, 0]
    return f, order, 8


def anim_angy():
    """Надулся -> вспышка злости: косые бровки, взгляд исподлобья, рот дугой, топает."""
    s = load('angy')
    L, R, M = crop(s, 12, 25, 45, 43), crop(s, 85, 25, 118, 43), crop(s, 45, 43, 88, 50)
    bl, br = blink_set(L), blink_set(R)
    # веко по наклонной: у переносицы ниже (злой взгляд)
    Lg = lid_cut(L, 2, 6)          # левый глаз: снаружи срез 2, у переносицы 6
    Rg = lid_cut(R, 6, 2)

    def brows(c):
        thick_line(c, 18, 31, 31, 35, 2)     # «\» над левым глазом
        thick_line(c, 97, 35, 109, 31, 2)    # «/» над правым
    B = canvas_part(brows)
    mcx = center(M)[0]
    frown = canvas_part(lambda c: arc(c, mcx, 48, 10.5, 5, 2, up=True))
    angry = compose(Lg, Rg, B, frown)
    f = [
        compose(L, R, M),                                    # 0 надулся
        compose(bl['half'], br['half'], M),                  # 1
        compose(bl['closed'], br['closed'], M),              # 2
        compose(Lg, Rg, M),                                  # 3 исподлобья
        angry,                                               # 4 злится
        compose((angry, 0, 0), dx=1),                        # 5 топ
        compose((angry, 0, 0), dx=-1),                       # 6 топ
    ]
    order = [0, 0, 0, 0, 1, 2, 1, 0, 0, 3, 4, 5, 6, 5, 6, 4, 4, 4, 4, 3, 0, 0]
    return f, order, 6


def anim_hmm():
    """Подозрительный прищур: зрачки-щёлочки косят влево-вправо, веко опускается."""
    s = load('hmm')
    M = crop(s, 45, 44, 82, 60)

    def eyes(p, squint):
        def d(c):
            for bx, sx in ((23, 27), (80, 84)):          # верхняя планка, щёлочка
                ty = 32 + squint
                c[ty:ty + 2, bx:bx + 22] = True
                c[ty + 2:37, sx + p:sx + p + 4] = True
                c[37:39, bx + 1:bx + 21] = True
        return canvas_part(d)

    def fr(p, squint, mdx):
        return compose(eyes(p, squint), M) if mdx == 0 else compose(eyes(p, squint)) | compose(M, dx=mdx)

    f = [
        compose((s, 0, 0)),          # 0 исходник (p=0)
        fr(-3, 0, -1),               # 1 влево
        fr(-3, 1, -1),               # 2 влево, прищур
        fr(4, 0, 0),                 # 3 по центру
        fr(10, 0, 1),                # 4 вправо
        fr(10, 1, 1),                # 5 вправо, прищур
    ]
    order = [0, 0, 0, 1, 1, 2, 2, 2, 1, 0, 3, 4, 4, 5, 5, 5, 4, 3, 0, 0]
    return f, order, 6


def anim_hng():
    """Натуга: BMO трясётся, жмурится сильнее, потом выдыхает."""
    s = load('hng')
    L, R, M = crop(s, 15, 20, 38, 44), crop(s, 92, 20, 118, 44), crop(s, 39, 43, 92, 62)
    Lc = at_center(squash_v(L[0], rnd(L[0].shape[0] * 0.75)), *center(L))
    Rc = at_center(squash_v(R[0], rnd(R[0].shape[0] * 0.75)), *center(R))
    seq = [(0, 0)] * 4 + [(1, 0), (-1, 0), (1, 0), (-1, 0),
                          (1, 1), (-1, 1), (1, 1), (-1, 1), (1, 1), (-1, 1),
                          (1, 0), (-1, 0)] + [(0, 0)] * 2
    f, key = [], {}
    for dx, clench in dict.fromkeys(seq):
        key[(dx, clench)] = len(f)
        f.append(compose(Lc if clench else L, Rc if clench else R, M, dx=dx))
    return f, [key[k] for k in seq], 8


def anim_oo():
    """«У-у-у!» — BMO поёт: рот-купол пульсирует, глаза-дуги приподнимаются на высокой ноте."""
    s = load('oo')
    L, R, M = crop(s, 12, 18, 42, 30), crop(s, 88, 18, 118, 30), crop(s, 40, 34, 92, 62)
    mspr, mx, my = M
    cx = center(M)[0]

    def mouth(scale):
        # рот сплошной чёрный — его можно честно уменьшить целиком, форма купола сохранится
        h, w = mspr.shape
        nw, nh = rnd(w * scale), rnd(h * scale)
        sp = np.array(Image.fromarray(mspr.astype(np.uint8) * 255).resize((nw, nh), Image.NEAREST)) > 127
        return sp, rnd(cx - nw / 2), my + rnd((h - nh) * 0.4)
    f = [
        compose(L, R, dy=-1) | compose(M),          # 0 полный звук
        compose(L, R) | compose(mouth(0.8)),        # 1
        compose(L, R) | compose(mouth(0.6)),        # 2 тихое «у»
    ]
    order = [0, 0, 0, 1, 2, 2, 1, 0, 0, 1, 2, 1, 0, 0, 0, 0, 1, 2, 2, 2, 1]
    return f, order, 6


def anim_yawn():
    """Сонный BMO: веки тяжёлые -> медленный зевок (один глаз жмурится) -> моргает."""
    s = load('yawn')
    L, Rscr, M = crop(s, 12, 15, 40, 33), crop(s, 88, 15, 118, 33), crop(s, 45, 33, 85, 63)
    lspr, lx, ly = L
    R = (lspr[:, ::-1], 99, ly)                     # открытый правый = зеркало левого
    mspr, mx, my = M
    mcx = center(M)[0]
    rows, cols = (37 - my, 52 - my), (57 - mx, 72 - mx)

    def mouth(dr, dc):
        sp = drop_cols(drop_rows(mspr, *rows, dr), *cols, dc)
        return sp, rnd(mcx - sp.shape[1] / 2), rnd(my + (mspr.shape[0] - sp.shape[0]) * 0.35)

    m_mid = mouth(7, 4)
    m_small = canvas_part(lambda c: ellipse(c, mcx, 43, 4.5, 5))
    m_shut = at_center(bar(8), mcx, 45)
    sleepy_L, sleepy_R = lid_cut(L, 6, 6), lid_cut(R, 6, 6)
    open_L = lid_cut(L, 3, 3)
    shut_L = at_center(bar(7), center(L)[0], 29)
    shut_R = at_center(bar(7), center(R)[0], 29)
    f = [
        compose(sleepy_L, sleepy_R, m_shut),      # 0 сонный
        compose(open_L, shut_R, m_small),         # 1 зевок начинается
        compose(L, Rscr, m_mid),                  # 2
        compose((s, 0, 0)),                       # 3 исходник — пик зевка
        compose(shut_L, shut_R, m_shut),          # 4 медленно моргнул
    ]
    order = [0, 0, 0, 0, 1, 2, 3, 3, 3, 3, 3, 2, 1, 0, 0, 0, 4, 4, 0, 0]
    return f, order, 5


ANIMS = {
    'BMO_angy': anim_angy,
    'BMO_happy': anim_happy,
    'BMO_hmm': anim_hmm,
    'BMO_hng': anim_hng,
    'BMO_laugh': anim_laugh,
    'BMO_oo': anim_oo,
    'BMO_smile': anim_smile,
    'BMO_smirk': anim_smirk,
    'BMO_yawn': anim_yawn,
}

META = """Filetype: Flipper Animation
Version: 1

Width: 128
Height: 64
Passive frames: {n}
Active frames: 0
Frames order: {order}
Active cycles: 0
Frame rate: {fps}
Duration: 3600
Active cooldown: 0

Bubble slots: 0
"""

MANIFEST_ITEM = """Name: {name}
Min butthurt: {lo}
Max butthurt: {hi}
Min level: 1
Max level: 30
Weight: {w}
"""

# Какая мордочка при каком настроении питомца (butthurt 0 — доволен, 14 — обижен)
# и как часто выпадает. Так стоит на приборе с 25.10.2026, порядок — от весёлых к сердитым.
MOODS = [
    ('BMO_happy', 0, 3, 10),
    ('BMO_laugh', 0, 4, 8),
    ('BMO_smile', 0, 6, 9),
    ('BMO_oo', 2, 7, 7),
    ('BMO_smirk', 4, 8, 7),
    ('BMO_hmm', 6, 10, 7),
    ('BMO_yawn', 7, 12, 6),
    ('BMO_hng', 9, 13, 6),
    ('BMO_angy', 11, 14, 7),
]


def to_img(a, scale=1, fg=(0, 0, 0), bg=(255, 255, 255)):
    rgb = np.where(a[..., None], np.array(fg, np.uint8), np.array(bg, np.uint8)).astype(np.uint8)
    im = Image.fromarray(rgb, 'RGB')
    return im.resize((W * scale, H * scale), Image.NEAREST) if scale > 1 else im


def main():
    prev = os.path.join(HERE, '_preview')
    os.makedirs(prev, exist_ok=True)
    manifest = ['Filetype: Flipper Animation Manifest', 'Version: 1', '']
    sheet_rows = []
    for name, fn in ANIMS.items():
        frames, order, fps = fn()
        assert 1 <= len(frames) <= 20, (name, len(frames))
        assert set(order) == set(range(len(frames))), (name, 'не все кадры в порядке')
        d = os.path.join(HERE, name)
        os.makedirs(d, exist_ok=True)
        for old in os.listdir(d):
            if old.startswith('frame_') and old.endswith('.png'):
                os.remove(os.path.join(d, old))
        for i, a in enumerate(frames):
            assert a.shape == (H, W)
            Image.fromarray(np.where(a, 0, 255).astype(np.uint8), 'L').convert('1').save(
                os.path.join(d, f'frame_{i}.png'))
        with open(os.path.join(d, 'meta.txt'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(META.format(n=len(order), order=' '.join(map(str, order)), fps=fps))
        # превью: GIF в цветах экрана Flipper (чёрное на оранжевом)
        imgs = [to_img(frames[i], 4, (0, 0, 0), (255, 130, 0)) for i in order]
        imgs[0].save(os.path.join(prev, f'{name}.gif'), save_all=True, append_images=imgs[1:],
                     duration=int(1000 / fps), loop=0, disposal=1)
        sheet_rows.append((name, frames, order, fps))
        print(f'{name}: кадров {len(frames)}, в цикле {len(order)}, {fps} к/с = {len(order) / fps:.1f} с')
    assert sorted(m[0] for m in MOODS) == sorted(ANIMS), 'MOODS и ANIMS разошлись'
    for name, lo, hi, w in MOODS:
        manifest.append(MANIFEST_ITEM.format(name=name, lo=lo, hi=hi, w=w))
    with open(os.path.join(HERE, 'manifest.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(manifest) + '\n')
    # лист всех уникальных кадров (для проверки глазами)
    sc, pad = 2, 4
    cols = max(len(r[1]) for r in sheet_rows)
    sheet = Image.new('RGB', (cols * (W * sc + pad) + pad, len(sheet_rows) * (H * sc + pad) + pad), (90, 90, 90))
    for ri, (name, frames, order, fps) in enumerate(sheet_rows):
        for ci, a in enumerate(frames):
            sheet.paste(to_img(a, sc), (pad + ci * (W * sc + pad), pad + ri * (H * sc + pad)))
    sheet.save(os.path.join(prev, '_all_frames_sheet.png'))
    # общее превью: все анимации сеткой 3x3, каждая в своём темпе
    from PIL import ImageDraw
    sc, pad, lab = 3, 6, 14
    cw, ch = W * sc, H * sc
    grid_w, grid_h = 3 * (cw + pad) + pad, 3 * (ch + pad + lab) + pad
    tick, total = 0.025, 12.0
    shots, durs = [], []
    for k in range(int(total / tick)):
        t = k * tick
        g = Image.new('RGB', (grid_w, grid_h), (40, 40, 40))
        dr = ImageDraw.Draw(g)
        for i, (name, frames, order, fps) in enumerate(sheet_rows):
            x = pad + (i % 3) * (cw + pad)
            y = pad + (i // 3) * (ch + pad + lab)
            fr = frames[order[int(t * fps) % len(order)]]
            g.paste(to_img(fr, sc, (0, 0, 0), (255, 130, 0)), (x, y))
            dr.text((x, y + ch + 2), name, fill=(230, 230, 230))
        if shots and np.array_equal(np.asarray(shots[-1]), np.asarray(g)):
            durs[-1] += int(tick * 1000)
        else:
            shots.append(g)
            durs.append(int(tick * 1000))
    shots[0].save(os.path.join(prev, '_ALL_animated.gif'), save_all=True, append_images=shots[1:],
                  duration=durs, loop=0, disposal=1)


if __name__ == '__main__':
    main()

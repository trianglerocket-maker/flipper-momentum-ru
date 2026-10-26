# -*- coding: utf-8 -*-
"""
Разбор и сборка шрифтов u8g2 (формат описан в csrc/u8g2_font.c).

Glyph: encoding, w, h, x, y (низ глифа относительно базовой линии), dx (сдвиг курсора),
       bitmap — список строк из '0'/'1' длиной w, сверху вниз.
Декодер повторяет логику u8g2_font_decode_glyph / u8g2_font_get_glyph_data байт в байт,
энкодер подбирает разрядности под набор глифов и проверяется декодером.
"""
import re

HEADER = 23


# ---------- чтение исходника .c ----------

def read_c_font(path, name):
    """Достать массив шрифта из .c (строковый литерал с экранированием)."""
    src = open(path, 'r', encoding='latin-1').read()
    m = re.search(r'const\s+uint8_t\s+' + re.escape(name) + r'\s*\[(\d+)\][^=]*=\s*', src)
    if not m:
        raise KeyError(name)
    size = int(m.group(1))
    pos = m.end()
    out = bytearray()
    while True:
        while src[pos] in ' \t\r\n':
            pos += 1
        if src[pos] == ';':
            break
        assert src[pos] == '"', src[pos:pos + 40]
        pos += 1
        while src[pos] != '"':
            ch = src[pos]
            if ch == '\\':
                nx = src[pos + 1]
                if nx in '01234567':
                    j = pos + 1
                    while j < pos + 4 and src[j] in '01234567':
                        j += 1
                    out.append(int(src[pos + 1:j], 8))
                    pos = j
                    continue
                if nx == 'x':
                    j = pos + 2
                    while src[j] in '0123456789abcdefABCDEF':
                        j += 1
                    out.append(int(src[pos + 2:j], 16) & 0xFF)
                    pos = j
                    continue
                out.append({'n': 10, 't': 9, 'r': 13, '\\': 92, '"': 34, "'": 39, '?': 63,
                            'a': 7, 'b': 8, 'f': 12, 'v': 11}[nx])
                pos += 2
                continue
            out.append(ord(ch))
            pos += 1
        pos += 1
    assert len(out) + 1 == size, (name, len(out), size)
    return bytes(out) + b'\x00'       # завершающий ноль строки — часть данных шрифта


# ---------- декодер ----------

class BitReader:
    def __init__(self, data, pos):
        self.d, self.p, self.bit = data, pos, 0

    def u(self, cnt):
        val = self.d[self.p] >> self.bit
        nb = self.bit + cnt
        if nb >= 8:
            s = 8 - self.bit
            self.p += 1
            val |= (self.d[self.p] if self.p < len(self.d) else 0) << s
            nb -= 8
        self.bit = nb
        return val & ((1 << cnt) - 1)

    def s(self, cnt):
        return self.u(cnt) - (1 << (cnt - 1))


def parse_header(f):
    k = ['glyph_cnt', 'bbx_mode', 'b0', 'b1', 'bw', 'bh', 'bx', 'by', 'bd',
         'max_w', 'max_h', 'x_off', 'y_off', 'ascent_A', 'descent_g', 'ascent_para', 'descent_para']
    h = dict(zip(k, f[:17]))
    for key in ('x_off', 'y_off', 'descent_g', 'descent_para'):
        if h[key] > 127:
            h[key] -= 256
    h['pos_A'] = (f[17] << 8) | f[18]
    h['pos_a'] = (f[19] << 8) | f[20]
    h['pos_uni'] = (f[21] << 8) | f[22]
    return h


def decode_glyph(f, h, pos, enc):
    r = BitReader(f, pos)
    w, hh = r.u(h['bw']), r.u(h['bh'])
    x, y, d = r.s(h['bx']), r.s(h['by']), r.s(h['bd'])
    px = []
    if w > 0:
        total = w * hh
        while True:
            a, b = r.u(h['b0']), r.u(h['b1'])
            while True:
                px += [0] * a + [1] * b
                if r.u(1) == 0:
                    break
            if len(px) >= total:      # == decode->y >= h после пары
                break
        px = px[:total]
    bm = [''.join(str(v) for v in px[i * w:(i + 1) * w]) for i in range(hh)] if w else []
    return dict(enc=enc, w=w, h=hh, x=x, y=y, d=d, bitmap=bm)


def decode_font(f):
    h = parse_header(f)
    glyphs = {}
    p = HEADER
    while f[p + 1] != 0:
        glyphs[f[p]] = decode_glyph(f, h, p + 2, f[p])
        p += f[p + 1]
    p += 2
    uni = HEADER + h['pos_uni']
    assert uni == p, ('unicode start', uni, p)
    # таблица поиска: записи (смещение, последний код); первая указывает на первый глиф,
    # глифы лежат подряд до кода 0
    p = uni + ((f[uni] << 8) | f[uni + 1])
    while True:
        e = (f[p] << 8) | f[p + 1]
        if e == 0:
            break
        glyphs[e] = decode_glyph(f, h, p + 3, e)
        p += f[p + 2]
    assert len(glyphs) == h['glyph_cnt'] or h['glyph_cnt'] == len(glyphs) % 256, (len(glyphs), h['glyph_cnt'])
    return h, glyphs


def lookup(f, enc):
    """Поиск глифа ровно как u8g2_font_get_glyph_data (для проверки собранного шрифта)."""
    h = parse_header(f)
    p = HEADER
    if enc <= 255:
        if enc >= ord('a'):
            p += h['pos_a']
        elif enc >= ord('A'):
            p += h['pos_A']
        while f[p + 1] != 0:
            if f[p] == enc:
                return p + 2
            p += f[p + 1]
        return None
    p += h['pos_uni']
    t = p
    while True:
        p += (f[t] << 8) | f[t + 1]
        e = (f[t + 2] << 8) | f[t + 3]
        t += 4
        if e >= enc:
            break
    while True:
        e = (f[p] << 8) | f[p + 1]
        if e == 0:
            return None
        if e == enc:
            return p + 3
        p += f[p + 2]


# ---------- энкодер ----------

class BitWriter:
    def __init__(self):
        self.bits = []

    def u(self, val, cnt):
        assert 0 <= val < (1 << cnt), (val, cnt)
        for i in range(cnt):
            self.bits.append((val >> i) & 1)

    def s(self, val, cnt):
        self.u(val + (1 << (cnt - 1)), cnt)

    def bytes(self):
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i + 8]
            out.append(sum(b << k for k, b in enumerate(chunk)))
        return bytes(out)


def bits_u(m):
    n = 1
    while (1 << n) <= m:
        n += 1
    return n


def bits_s(lo, hi):
    n = 1
    while not (-(1 << (n - 1)) <= lo and hi < (1 << (n - 1))):
        n += 1
    return n


def rle_pairs(g, b0, b1):
    px = [int(c) for row in g['bitmap'] for c in row]
    m0, m1 = (1 << b0) - 1, (1 << b1) - 1
    pairs, i, n = [], 0, len(px)
    while i < n:
        a = 0
        while i < n and px[i] == 0 and a < m0:
            a += 1
            i += 1
        b = 0
        while i < n and px[i] == 1 and b < m1:
            b += 1
            i += 1
        pairs.append((a, b))
    return pairs


def encode_glyph(g, p):
    w = BitWriter()
    w.u(g['w'], p['bw'])
    w.u(g['h'], p['bh'])
    w.s(g['x'], p['bx'])
    w.s(g['y'], p['by'])
    w.s(g['d'], p['bd'])
    if g['w'] > 0:
        pairs = rle_pairs(g, p['b0'], p['b1'])
        i = 0
        while i < len(pairs):
            j = i
            while j + 1 < len(pairs) and pairs[j + 1] == pairs[i]:
                j += 1
            w.u(pairs[i][0], p['b0'])
            w.u(pairs[i][1], p['b1'])
            for _ in range(j - i):
                w.u(1, 1)
            w.u(0, 1)
            i = j + 1
    return w.bytes()


def encode_font(glyphs, base_header):
    """Собрать шрифт. Метрики шрифта (max_w/h, смещения, ascent/descent) берутся из
    base_header — чтобы вёрстка экранов не поехала от новых букв."""
    gl = [glyphs[k] for k in sorted(glyphs)]
    nz = [g for g in gl if g['w'] > 0] or gl
    p = dict(
        bw=bits_u(max(g['w'] for g in gl)),
        bh=bits_u(max(g['h'] for g in gl)),
        bx=bits_s(min(g['x'] for g in gl), max(g['x'] for g in gl)),
        by=bits_s(min(g['y'] for g in gl), max(g['y'] for g in gl)),
        bd=bits_s(min(g['d'] for g in gl), max(g['d'] for g in gl)),
    )
    best = None
    for b0 in range(2, 7):
        for b1 in range(2, 7):
            q = dict(p, b0=b0, b1=b1)
            size = sum(len(encode_glyph(g, q)) for g in gl)
            if best is None or size < best[0]:
                best = (size, b0, b1)
    p['b0'], p['b1'] = best[1], best[2]

    ascii_part = bytearray()
    pos_A = pos_a = None
    for g in gl:
        if g['enc'] > 255:
            continue
        if pos_A is None and g['enc'] >= ord('A'):
            pos_A = len(ascii_part)
        if pos_a is None and g['enc'] >= ord('a'):
            pos_a = len(ascii_part)
        data = encode_glyph(g, p)
        assert len(data) + 2 < 256, g['enc']
        ascii_part += bytes([g['enc'], len(data) + 2]) + data
    end_ascii = len(ascii_part)
    pos_A = end_ascii if pos_A is None else pos_A
    pos_a = end_ascii if pos_a is None else pos_a
    ascii_part += b'\x00\x00'
    pos_uni = len(ascii_part)
    uni_part = bytearray(b'\x00\x04\xff\xff')        # одна группа: глифы сразу за таблицей
    for g in gl:
        if g['enc'] <= 255:
            continue
        data = encode_glyph(g, p)
        assert len(data) + 3 < 256, g['enc']
        uni_part += bytes([g['enc'] >> 8, g['enc'] & 0xFF, len(data) + 3]) + data
    uni_part += b'\x00\x00'

    bh = base_header

    def sb(v):
        return v & 0xFF
    head = bytes([
        len(gl) & 0xFF, bh['bbx_mode'], p['b0'], p['b1'],
        p['bw'], p['bh'], p['bx'], p['by'], p['bd'],
        bh['max_w'], bh['max_h'], sb(bh['x_off']), sb(bh['y_off']),
        bh['ascent_A'], sb(bh['descent_g']), bh['ascent_para'], sb(bh['descent_para']),
        pos_A >> 8, pos_A & 0xFF, pos_a >> 8, pos_a & 0xFF, pos_uni >> 8, pos_uni & 0xFF,
    ])
    font = head + bytes(ascii_part) + bytes(uni_part)
    # проверка: каждый глиф находится поиском u8g2 и распаковывается в то же самое
    h2 = parse_header(font)
    for g in gl:
        at = lookup(font, g['enc'])
        assert at is not None, ('не найден', g['enc'])
        back = decode_glyph(font, h2, at, g['enc'])
        for k in ('w', 'h', 'x', 'y', 'd', 'bitmap'):
            assert back[k] == g[k], ('расхождение', g['enc'], k, back[k], g[k])
    return font


def to_c(name, font):
    """Массив в стиле u8g2_fonts.c (размер включает завершающий ноль строки).
    Каждый байт — восьмеричный код из 3 цифр: однозначно, без ловушек экранирования."""
    body = ''.join('\\%03o' % b for b in font)
    chunks = [body[i:i + 120] for i in range(0, len(body), 120)]
    return ('const uint8_t %s[%d] U8G2_FONT_SECTION("%s") = \n  "%s";\n'
            % (name, len(font) + 1, name, '"\n  "'.join(chunks)))


def render(glyphs, h, text, scale=1):
    """Строка текста в список строк '#'/'.' (для глазной проверки)."""
    asc, desc = h['ascent_para'] + 1, -h['descent_para'] + 1
    H = asc + desc
    cols = []
    for ch in text:
        g = glyphs.get(ord(ch))
        if g is None:
            cols.append(['?'] * H)
            continue
        cw = max(g['d'], g['x'] + g['w'], 1)
        block = [['.'] * cw for _ in range(H)]
        for r, row in enumerate(g['bitmap']):
            yy = asc - (g['y'] + g['h']) + r
            for c, v in enumerate(row):
                xx = g['x'] + c
                if v == '1' and 0 <= yy < H and 0 <= xx < cw:
                    block[yy][xx] = '#'
        for c in range(cw):
            cols.append([block[r][c] for r in range(H)])
    return [''.join(col[r] for col in cols) for r in range(H)]

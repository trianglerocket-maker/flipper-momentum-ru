# -*- coding: utf-8 -*-
"""
Правки текстового движка Momentum под UTF-8 (русская буква = 2 байта).

Без них прошивка режет и прокручивает текст побайтово: длинные русские подписи
не прокручиваются, при переносе буква рвётся пополам, текстовый блок
(elements_text_box) не рисует кириллицу вовсе. Каждая правка — точная замена
куска кода; если кусок не найден (другая версия прошивки), скрипт падает.
"""
import os

HELPERS = r'''
// UTF-8: русская буква занимает 2 байта. Код символа в позиции s и его длина.
static uint16_t elements_utf8_char(const char* s, size_t* len) {
    uint8_t c = (uint8_t)s[0];
    if(c >= 0xC0 && c < 0xE0 && ((uint8_t)s[1] & 0xC0) == 0x80) {
        *len = 2;
        return ((c & 0x1F) << 6) | ((uint8_t)s[1] & 0x3F);
    }
    if(c >= 0xE0 && c < 0xF0 && ((uint8_t)s[1] & 0xC0) == 0x80 &&
       ((uint8_t)s[2] & 0xC0) == 0x80) {
        *len = 3;
        return ((c & 0x0F) << 12) | (((uint8_t)s[1] & 0x3F) << 6) | ((uint8_t)s[2] & 0x3F);
    }
    *len = 1;
    return c;
}

// Убрать последний символ целиком (а не последний байт).
static void elements_utf8_pop(FuriString* str) {
    size_t size = furi_string_size(str);
    if(!size) return;
    const char* s = furi_string_get_cstr(str);
    size--;
    while(size && ((uint8_t)s[size] & 0xC0) == 0x80)
        size--;
    furi_string_left(str, size);
}

// Сдвинуть позицию вперёд до начала символа.
static size_t elements_utf8_align(FuriString* str, size_t pos) {
    const char* s = furi_string_get_cstr(str);
    size_t size = furi_string_size(str);
    while(pos < size && ((uint8_t)s[pos] & 0xC0) == 0x80)
        pos++;
    return pos;
}
'''

ELEMENTS = [
    # помощники — перед первой функцией, где нужны
    ('\nstatic size_t\n    elements_get_max_chars_to_fit(',
     HELPERS + '\nstatic size_t\n    elements_get_max_chars_to_fit('),
    # перенос строк в окнах/сообщениях: не резать букву
    ('''    } else {
        result = text_size;
    }

    furi_string_free(str);
    return result;''',
     '''    } else {
        result = text_size;
    }
    while(result > 0 && result < text_size && ((uint8_t)text[result] & 0xC0) == 0x80)
        result--;

    furi_string_free(str);
    return result;'''),
    ('''            chars_fit -= 1; // account for the dash
''',
     '''            chars_fit -= 1; // account for the dash
            while(chars_fit > 0 && ((uint8_t)start[chars_fit] & 0xC0) == 0x80)
                chars_fit--;
'''),
    # подгонка ширины с многоточием
    ('''        do {
            furi_string_left(string, furi_string_size(string) - 1);
            len_px = canvas_string_width(canvas, furi_string_get_cstr(string));
        } while(len_px > width);''',
     '''        do {
            elements_utf8_pop(string);
            len_px = canvas_string_width(canvas, furi_string_get_cstr(string));
        } while(len_px > width);'''),
    # прокрутка длинных строк
    ('''        size_t scroll_size = furi_string_size(line);
        size_t right_width = 0;
        for(size_t i = scroll_size - 1; i > 0; i--) {
            right_width += canvas_glyph_width(canvas, furi_string_get_char(line, i));
            if(right_width > width) break;
            scroll_size--;
            if(!scroll_size) break;
        }''',
     '''        // Начало самого длинного хвоста, который помещается (целыми символами UTF-8)
        size_t scroll_size = furi_string_size(line);
        {
            const char* cstr = furi_string_get_cstr(line);
            while(scroll_size > 0) {
                size_t prev = scroll_size - 1;
                while(prev > 0 && ((uint8_t)cstr[prev] & 0xC0) == 0x80)
                    prev--;
                if(canvas_string_width(canvas, cstr + prev) > width) break;
                scroll_size = prev;
            }
        }'''),
    ('furi_string_right(line, use_scroll);', 'furi_string_right(line, elements_utf8_align(line, use_scroll));'),
    ('furi_string_right(line, scroll_size);', 'furi_string_right(line, elements_utf8_align(line, scroll_size));'),
    ('furi_string_right(line, reverse_pos);', 'furi_string_right(line, elements_utf8_align(line, reverse_pos));'),
    ('furi_string_right(line, scroll);', 'furi_string_right(line, elements_utf8_align(line, scroll));'),
    ('''        while(len_px > width) {
            furi_string_left(line, furi_string_size(line) - 1);''',
     '''        while(len_px > width) {
            elements_utf8_pop(line);'''),
    # текстовый блок: разбивка на строки по символам
    ('''        if(text[i] != '\\n') {
            line_width += canvas_glyph_width(canvas, text[i]);
        }
        // Process new line
        if(text[i] == '\\n' || text[i] == '\\0' || line_width > width) {
            if(line_width > width) {
                line_width -= canvas_glyph_width(canvas, text[i--]);
                line_len--;
            }''',
     '''        size_t char_len = 1;
        size_t char_width = 0;
        if(text[i] != '\\n') {
            char_width = canvas_glyph_width(canvas, elements_utf8_char(&text[i], &char_len));
            line_width += char_width;
            i += char_len - 1;
            line_len += char_len - 1;
        }
        // Process new line
        if(text[i] == '\\n' || text[i] == '\\0' || line_width > width) {
            if(line_width > width) {
                line_width -= char_width;
                i -= char_len;
                line_len -= char_len;
            }'''),
    # текстовый блок: отрисовка по символам
    ('''            if(inverse) {
                canvas_draw_box(
                    canvas,
                    line[i].x - 1,
                    line[i].y - line[i].height - 1,
                    canvas_glyph_width(canvas, line[i].text[j]) + 1,
                    line[i].height + line[i].descender + 2);
                canvas_invert_color(canvas);
                canvas_draw_glyph(canvas, line[i].x, line[i].y, line[i].text[j]);
                canvas_invert_color(canvas);
            } else {
                if((i == line_num - 1) && strip_to_dots) {
                    size_t next_symbol_width = canvas_glyph_width(canvas, line[i].text[j]);
                    if((line[i].x + (int32_t)next_symbol_width + (int32_t)dots_width) >
                       (x + (int32_t)width)) {
                        canvas_draw_str(canvas, line[i].x, line[i].y, "...");
                        break;
                    }
                }
                canvas_draw_glyph(canvas, line[i].x, line[i].y, line[i].text[j]);
            }
            line[i].x += canvas_glyph_width(canvas, line[i].text[j]);''',
     '''            size_t char_len = 1;
            uint16_t symbol = elements_utf8_char(&line[i].text[j], &char_len);
            if(inverse) {
                canvas_draw_box(
                    canvas,
                    line[i].x - 1,
                    line[i].y - line[i].height - 1,
                    canvas_glyph_width(canvas, symbol) + 1,
                    line[i].height + line[i].descender + 2);
                canvas_invert_color(canvas);
                canvas_draw_glyph(canvas, line[i].x, line[i].y, symbol);
                canvas_invert_color(canvas);
            } else {
                if((i == line_num - 1) && strip_to_dots) {
                    size_t next_symbol_width = canvas_glyph_width(canvas, symbol);
                    if((line[i].x + (int32_t)next_symbol_width + (int32_t)dots_width) >
                       (x + (int32_t)width)) {
                        canvas_draw_str(canvas, line[i].x, line[i].y, "...");
                        break;
                    }
                }
                canvas_draw_glyph(canvas, line[i].x, line[i].y, symbol);
            }
            line[i].x += canvas_glyph_width(canvas, symbol);
            j += char_len - 1;'''),
]

VARIABLE_ITEM_LIST = [
    ('furi_string_size(item->current_value_text) < 4U',
     'furi_string_utf8_length(item->current_value_text) < 4U'),
]


def patch_file(path, edits):
    src = open(path, encoding='utf-8', newline='').read()
    for old, new in edits:
        n = src.count(old)
        assert n == 1, (os.path.basename(path), n, old[:70])
        src = src.replace(old, new)
    open(path, 'w', encoding='utf-8', newline='').write(src)


def u8g2_alias_edits():
    """Запасной поиск буквы: нет своей кириллической — берётся латинский двойник."""
    from cyr_glyphs import ALIASES
    codes = ', '.join('0x%03X' % ord(c) for c in ALIASES)
    latin = ''.join(ALIASES.values())
    wrapper = '''
/* Русские буквы, которые рисуются точно как латинские (А, В, Е... и Ё/ё как Е/е).
   Если в шрифте нет своей кириллической буквы, берётся латинский двойник:
   двойники не хранятся в шрифтах прошивки, это экономит флеш-память. */
static const uint16_t u8g2_cyr_alias_code[] = {%s};
static const char u8g2_cyr_alias_latin[] = "%s";

const uint8_t* u8g2_font_get_glyph_data(u8g2_t* u8g2, uint16_t encoding) {
    const uint8_t* glyph = u8g2_font_get_glyph_data_exact(u8g2, encoding);
    if(glyph == NULL && encoding >= 0x400 && encoding < 0x460) {
        for(uint8_t i = 0; i < sizeof(u8g2_cyr_alias_code) / sizeof(u8g2_cyr_alias_code[0]); i++) {
            if(u8g2_cyr_alias_code[i] == encoding) {
                return u8g2_font_get_glyph_data_exact(u8g2, (uint8_t)u8g2_cyr_alias_latin[i]);
            }
        }
    }
    return glyph;
}
''' % (codes, latin)
    return [
        ('const uint8_t* u8g2_font_get_glyph_data(u8g2_t* u8g2, uint16_t encoding) {\n'
         '    const uint8_t* font = u8g2->font;',
         'static const uint8_t* u8g2_font_get_glyph_data_exact(u8g2_t* u8g2, uint16_t encoding) {\n'
         '    const uint8_t* font = u8g2->font;'),
        ('    return NULL;\n}\n\nstatic u8g2_uint_t\n    u8g2_font_draw_glyph(',
         '    return NULL;\n}\n' + wrapper + '\nstatic u8g2_uint_t\n    u8g2_font_draw_glyph('),
    ]


def main(fw):
    gui = os.path.join(fw, 'applications', 'services', 'gui')
    patch_file(os.path.join(gui, 'elements.c'), ELEMENTS)
    patch_file(os.path.join(gui, 'modules', 'variable_item_list.c'), VARIABLE_ITEM_LIST)
    patch_file(os.path.join(fw, 'lib', 'u8g2', 'u8g2_font.c'), u8g2_alias_edits())
    print('GUI: правки UTF-8 и двойники букв внесены')


if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else 'momentum-firmware')

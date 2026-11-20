#!/usr/bin/env python3
"""Generate main/probe_font.h -- a 5x7 pixel font for the two ST7735 panels.

Why a generated font instead of a hand-written table: the first version of this
menu used a 3x5 font drawn at scale 2 to make it "bigger".  Scaling a 3x5 glyph
by 2 turns every stroke into a 2x2 block and the letters run together -- it is
bigger but less readable.  A real 5x7 glyph drawn at scale 1 is 7 px tall and
crisp; drawn at scale 2 it is 14 px tall and still crisp.

The glyph art lives here as readable ASCII so a human can see and fix it, and
the C header is regenerated with:

    python tools/gen_font.py

Row 0 is the top.  Each glyph is 5 columns; bit n of a column byte is row n.
"""

import os

# Each glyph: 7 rows of exactly 5 characters.  '#' = ink.
GLYPHS = {
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "#": (".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#..##"),
    "*": (".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    ",": (".....", ".....", ".....", ".....", ".....", "..#..", ".#..."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", "..#..", "..#.."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    ":": (".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    ">": (".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."),
    "<": ("...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "_": (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".###.", "#...#", "#....", ".###.", "....#", "#...#", ".###."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
}

WIDTH, HEIGHT = 5, 7
FIRST, LAST = 0x20, 0x7E


def columns(art):
    """Transpose 7 rows of 5 characters into 5 column bitmasks (bit0 = top)."""
    cols = []
    for x in range(WIDTH):
        bits = 0
        for y in range(HEIGHT):
            if art[y][x] == "#":
                bits |= 1 << y
        cols.append(bits)
    return cols


def build():
    table = []
    for code in range(FIRST, LAST + 1):
        ch = chr(code)
        art = GLYPHS.get(ch.upper() if ch.islower() else ch)
        table.append(columns(art) if art else [0] * WIDTH)
    return table


def render_preview(table):
    for code in range(FIRST, LAST + 1):
        cols = table[code - FIRST]
        if not any(cols):
            continue
        print("  " + chr(code))
        for y in range(HEIGHT):
            line = "".join("#" if (cols[x] >> y) & 1 else "." for x in range(WIDTH))
            print("  " + line)
        print()


def emit(table, path):
    lines = [
        "/* probe_font.h -- 5x7 pixel font. GENERATED by tools/gen_font.py.",
        " *",
        " * 5 columns x 7 rows per glyph, ASCII 0x20..0x7E.  Bit n of a column byte",
        " * is row n, row 0 at the top.  Draw at scale 1 for crisp 7 px text, scale",
        " * 2 for 14 px text; do NOT emulate size by scaling a smaller glyph.",
        " *",
        " * Edit tools/gen_font.py, not this file.",
        " */",
        "#ifndef PROBE_FONT_H_INCLUDED",
        "#define PROBE_FONT_H_INCLUDED",
        "",
        "#include <stdint.h>",
        "",
        "#define PROBE_FONT_W  %d" % WIDTH,
        "#define PROBE_FONT_H  %d" % HEIGHT,
        "#define PROBE_FONT_ADV %d   /* glyph width + 1 px gap */" % (WIDTH + 1),
        "#define PROBE_FONT_FIRST 0x%02X" % FIRST,
        "#define PROBE_FONT_LAST  0x%02X" % LAST,
        "",
        "static const uint8_t PROBE_FONT[%d][%d] = {" % (len(table), WIDTH),
    ]
    for code, cols in zip(range(FIRST, LAST + 1), table):
        ch = chr(code)
        shown = ch if 0x21 <= code <= 0x7E else " "
        lines.append("    {0x%02X,0x%02X,0x%02X,0x%02X,0x%02X},  /* '%s' */"
                      % (*cols, shown))
    lines += [
        "};",
        "",
        "/* Returns a pointer to a 5-byte column bitmask, or the blank glyph. */",
        "static inline const uint8_t *probe_font_glyph(char c)",
        "{",
        "    if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');",
        "    if (c < PROBE_FONT_FIRST || c > PROBE_FONT_LAST)",
        "        return PROBE_FONT[0];",
        "    return PROBE_FONT[(int)c - PROBE_FONT_FIRST];",
        "}",
        "",
        "#endif /* PROBE_FONT_H_INCLUDED */",
        "",
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return path


if __name__ == "__main__":
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "main", "probe_font.h")
    table = build()
    emit(table, os.path.abspath(out))
    if "--preview" in sys.argv:
        render_preview(table)
    print("wrote", os.path.abspath(out), "glyphs:", len(table))

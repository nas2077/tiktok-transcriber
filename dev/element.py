"""Nas project tiles: every project is an element of one periodic table.

A tile is pixel art on a fixed grid. Its number is the order in which projects
are published (01, 02, ...), its two-letter symbol is the project's, and its
color is the project's category. The same rules make every icon, so the set
stays orderly however many projects there are.

    tile(number, symbol, category)  -> 32 x 32 grid for 48 px and larger
    badge(symbol, category)         -> 16 x 16 grid for 16 and 32 px
    png(grid, scale) / svg(grid)    -> files

Grids are lists of strings; '.' is transparent, other letters name a palette
entry in COLORS.
"""
import struct
import zlib

# Nas design system base colors and one color per project category.
NAVY, CREAM = "1b2632", "eee9df"
CATEGORIES = {
    "app": "ffb162",        # desktop and mobile applications (Nas pixel orange)
    "game": "7fc8a9",       # games
    "site": "8fb8e8",       # websites
    "design": "e8805a",     # design systems and visual identity
    "animation": "c59be0",  # animation and 3D
    "study": "e6d27a",      # study, data and writing
}

# 5 x 7 letters for symbols, 3 x 5 digits for numbers: rows separated by spaces.
LETTERS = {
    "A": ".###. #...# #...# ##### #...# #...# #...#", "B": "####. #...# #...# ####. #...# #...# ####.",
    "C": ".###. #...# #.... #.... #.... #...# .###.", "D": "####. #...# #...# #...# #...# #...# ####.",
    "E": "##### #.... #.... ####. #.... #.... #####", "F": "##### #.... #.... ####. #.... #.... #....",
    "G": ".###. #...# #.... #.### #...# #...# .####", "H": "#...# #...# #...# ##### #...# #...# #...#",
    "I": ".###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.", "J": "..### ...#. ...#. ...#. ...#. #..#. .##..",
    "K": "#...# #..#. #.#.. ##... #.#.. #..#. #...#", "L": "#.... #.... #.... #.... #.... #.... #####",
    "M": "#...# ##.## #.#.# #.#.# #...# #...# #...#", "N": "#...# #...# ##..# #.#.# #..## #...# #...#",
    "O": ".###. #...# #...# #...# #...# #...# .###.", "P": "####. #...# #...# ####. #.... #.... #....",
    "Q": ".###. #...# #...# #...# #.#.# #..#. .##.#", "R": "####. #...# #...# ####. #.#.. #..#. #...#",
    "S": ".#### #.... #.... .###. ....# ....# ####.", "T": "##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "U": "#...# #...# #...# #...# #...# #...# .###.", "V": "#...# #...# #...# #...# #...# .#.#. ..#..",
    "W": "#...# #...# #...# #.#.# #.#.# #.#.# .#.#.", "X": "#...# #...# .#.#. ..#.. .#.#. #...# #...#",
    "Y": "#...# #...# .#.#. ..#.. ..#.. ..#.. ..#..", "Z": "##### ....# ...#. ..#.. .#... #.... #####",
    "a": "..... ..... .###. ....# .#### #...# .####", "b": "#.... #.... #.##. ##..# #...# #...# ####.",
    "c": "..... ..... .###. #.... #.... #...# .###.", "d": "....# ....# .##.# #..## #...# #...# .####",
    "e": "..... ..... .###. #...# ##### #.... .###.", "f": "..##. .#..# .#... ###.. .#... .#... .#...",
    "g": "..... .#### #...# #...# .#### ....# .###.", "h": "#.... #.... #.##. ##..# #...# #...# #...#",
    "i": "..#.. ..... .##.. ..#.. ..#.. ..#.. .###.", "j": "...#. ..... ..##. ...#. ...#. #..#. .##..",
    "k": "#.... #.... #..#. #.#.. ##... #.#.. #..#.", "l": ".##.. ..#.. ..#.. ..#.. ..#.. ..#.. .###.",
    "m": "..... ..... ##.#. #.#.# #.#.# #...# #...#", "n": "..... ..... #.##. ##..# #...# #...# #...#",
    "o": "..... ..... .###. #...# #...# #...# .###.", "p": "..... ..... ####. #...# ####. #.... #....",
    "q": "..... ..... .##.# #..## .#### ....# ....#", "r": "..... ..... #.##. ##..# #.... #.... #....",
    "s": "..... ..... .###. #.... .###. ....# ####.", "t": ".#... .#... ###.. .#... .#... .#..# ..##.",
    "u": "..... ..... #...# #...# #...# #..## .##.#", "v": "..... ..... #...# #...# #...# .#.#. ..#..",
    "w": "..... ..... #...# #...# #.#.# #.#.# .#.#.", "x": "..... ..... #...# .#.#. ..#.. .#.#. #...#",
    "y": "..... ..... #...# #...# .#### ....# .###.", "z": "..... ..... ##### ...#. ..#.. .#... #####",
}
DIGITS = {
    "0": "### #.# #.# #.# ###", "1": ".#. ##. .#. .#. ###",
    "2": "### ..# ### #.. ###", "3": "### ..# .## ..# ###",
    "4": "#.# #.# ### ..# ..#", "5": "### #.. ### ..# ###",
    "6": "### #.. ### #.# ###", "7": "### ..# .#. .#. .#.",
    "8": "### #.# ### #.# ###", "9": "### #.# ### ..# ###",
}


def _canvas(size):
    return [["."] * size for _ in range(size)]


def _stamp(canvas, glyph, x, y, color, scale=1):
    for gy, row in enumerate(glyph.split()):
        for gx, c in enumerate(row):
            if c != "#":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    canvas[y + gy * scale + dy][x + gx * scale + dx] = color


def _rounded(canvas, color):
    size = len(canvas)
    for y in range(size):
        for x in range(size):
            canvas[y][x] = color
    for x, y in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
        canvas[y][x] = "."


def tile(number, symbol, category):
    """the full element: number in the corner, symbol in the middle, a color bar"""
    canvas = _canvas(32)
    _rounded(canvas, "k")                      # category color frame
    for y in range(1, 31):
        for x in range(1, 31):
            canvas[y][x] = "n"                 # navy body
    for x, y in ((1, 1), (30, 1), (1, 30), (30, 30)):
        canvas[y][x] = "k"
    for i, digit in enumerate(f"{number:02d}"):
        _stamp(canvas, DIGITS[digit], 4 + i * 4, 4, "k")
    letters = symbol[:2]
    width = len(letters) * 10 + (len(letters) - 1) * 2
    x = (32 - width) // 2
    for i, letter in enumerate(letters):
        _stamp(canvas, LETTERS[letter], x + i * 12, 10, "c", scale=2)
    for x in range(4, 28):
        canvas[26][x] = canvas[27][x] = "k"
    return ["".join(row) for row in canvas]


def badge(symbol, category):
    """the small icon: the symbol on a full category-color square"""
    canvas = _canvas(16)
    _rounded(canvas, "k")
    letters = symbol[:2]
    width = len(letters) * 5 + (len(letters) - 1)
    x = (16 - width) // 2
    for i, letter in enumerate(letters):
        _stamp(canvas, LETTERS[letter], x + i * 6, 4, "n")
    return ["".join(row) for row in canvas]


def _darker(color, amount=0.72):
    return "".join(f"{round(int(color[i:i + 2], 16) * amount):02x}" for i in (0, 2, 4))


def palette(category, light=False):
    """dark: category color on navy. light: cream body, and a deeper category
    color so yellow and orange stay readable on it."""
    if light:
        return {"k": _darker(CATEGORIES[category]), "n": CREAM, "c": NAVY}
    return {"k": CATEGORIES[category], "n": NAVY, "c": CREAM}


def png(grid, scale, category, light=False):
    colors = {k: bytes.fromhex(v) + b"\xff" for k, v in palette(category, light).items()}
    colors["."] = b"\0\0\0\0"
    rows = [b"".join(colors[c] * scale for c in row) for row in grid for _ in range(scale)]
    size = len(grid) * scale

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + r for r in rows), 9)) + chunk(b"IEND", b""))


def rects(grid, classes):
    """merged horizontal runs, one <rect> each, for compact SVG"""
    out = []
    for y, row in enumerate(grid):
        x = 0
        while x < len(row):
            c = row[x]
            end = x
            while end < len(row) and row[end] == c:
                end += 1
            if c in classes:
                out.append(f'<rect x="{x}" y="{y}" width="{end - x}" height="1" {classes[c]}/>')
            x = end
    return "".join(out)


def svg(grid, category, label, size=160):
    """a standalone SVG that follows the reader's light or dark theme"""
    n = len(grid)
    dark, light = palette(category), palette(category, light=True)
    style = (f".k{{fill:#{dark['k']}}}.n{{fill:#{dark['n']}}}.c{{fill:#{dark['c']}}}"
             f"@media(prefers-color-scheme:light){{.k{{fill:#{light['k']}}}.n{{fill:#{light['n']}}}"
             f".c{{fill:#{light['c']}}}}}")
    body = rects(grid, {"k": 'class="k"', "n": 'class="n"', "c": 'class="c"'})
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size}" height="{size}" '
            f'shape-rendering="crispEdges" role="img" aria-label="{label}"><title>{label}</title>'
            f"<style>{style}</style>{body}</svg>\n")


def ico(images):
    """a Windows icon from (size, png bytes) pairs"""
    offset = 6 + 16 * len(images)
    entries = []
    for size, data in images:
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(d for _, d in images)

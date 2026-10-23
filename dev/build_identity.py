"""Render the TikTok Transcriber element tile as SVG, PNG and a Windows icon.

The tile follows the Nas periodic table (dev/element.py): element 01, symbol
Tt, category app. Small sizes use the badge; 64 px and up use the full tile.
"""
from pathlib import Path

import element

ROOT = Path(__file__).resolve().parent.parent
NAME, NUMBER, SYMBOL, CATEGORY = "TikTok Transcriber", 1, "Tt", "app"


def main():
    tile = element.tile(NUMBER, SYMBOL, CATEGORY)
    badge = element.badge(SYMBOL, CATEGORY)
    folder = ROOT / ".github/assets"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "icon.svg").write_bytes(element.svg(tile, CATEGORY, NAME).encode())
    (folder / "icon.png").write_bytes(element.png(tile, 8, CATEGORY))
    images = [(16, element.png(badge, 1, CATEGORY)), (32, element.png(badge, 2, CATEGORY)),
              (48, element.png(badge, 3, CATEGORY)), (64, element.png(tile, 2, CATEGORY)),
              (128, element.png(tile, 4, CATEGORY)), (256, element.png(tile, 8, CATEGORY))]
    (ROOT / "src/icon.ico").write_bytes(element.ico(images))
    # macOS bundles and Linux desktop entries take a plain PNG
    (ROOT / "src/icon.png").write_bytes(element.png(tile, 16, CATEGORY))
    # the badge in the app's title bar, drawn with the page's own colors
    path = ROOT / "src/ui.html"
    text = path.read_text(encoding="utf-8")
    start = text.index("<svg", text.index('<div class="brand '))
    end = text.index("</svg>", start) + len("</svg>")
    inline = (f'<svg class="n-pixel" width="32" height="32" viewBox="0 0 16 16" role="img" aria-label="{NAME}">'
              + element.rects(badge, {"k": 'fill="var(--pixel-orange)"', "n": f'fill="#{element.NAVY}"'})
              + "</svg>")
    path.write_bytes((text[:start] + inline + text[end:]).encode("utf-8"))
    print(f"{NAME} element {NUMBER:02d} {SYMBOL}: SVG, PNG, six-size ICO, 512 px PNG and title bar badge.")


if __name__ == "__main__":
    main()

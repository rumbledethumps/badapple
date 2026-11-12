#!/usr/bin/env python3
"""Bad Apple!! title screen: credits in Shippori Mincho, in 4-bit tiles.

The screen is 640x480 at full resolution, on plane 0 in mode 2 with 4-bit
tiles, so the type keeps its antialiasing: black, and three pastels, each
in five steps from black, sixteen colors. White is for the names, the
Picocomputer line, and the keys; butter for the title and the prompt;
lilac for the headings and roles. The transport always shows over the
bottom, so the text stays above TEXT_BOTTOM.

Antialiased type makes nearly every cell a tile of its own, about 800 of
them, and mode 2 holds 256 per layer. So plane 0 is drawn in bands of
scanlines, each a mode 2 layer with a tile set of its own, tile 0 black,
all reading the one map. The tiles take 8 KB a band; the player puts them
in the video's map buffers and ring, which the title screen does not use.

Output, in OUT:
  title.bin   16-byte header ("TTL1", the number of bands, then each band's
              first row of tiles), the palette, 16 colors of 2 bytes, then
              each band's 256 tiles, 32 bytes each, two pixels a byte, the
              left one in the high bits, then the 80x60 map, 4,800 bytes.
  title.png   the screen as the VGA would draw it, with the transport over
              it, to look at.

usage: title.py [--out data/encoded] [--fonts data/fonts]
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, TILE = 640, 480, 8
COLS, ROWS = W // TILE, H // TILE
TEXT_BOTTOM = 396  # the transport's time label starts at 414
LEVELS = 5  # steps of each pastel from black

COLORS = {"white": (0xF4, 0xF1, 0xEA), "butter": (0xF2, 0xE2, 0xA4), "lilac": (0xD4, 0xC7, 0xEB),
          "peach": (0xF4, 0xC6, 0xB4), "mint": (0xBC, 0xE2, 0xCF), "sky": (0xBC, 0xD5, 0xED),
          "char": (0x3D, 0x3A, 0x42)}
PLANES = ["white", "butter", "lilac"]  # the type's colors, though all are on plane 0
WHITE, BUTTER, LILAC = range(3)

CREDITS = [
    ("MUSIC", [("ZUN", "composer, “Bad Apple!!”, 1998"), ("Masayoshi Minoshima", "arrangement, 2007"),
               ("nomico", "vocals"), ("Haruka", "lyrics")]),
    ("VIDEO", [("Μμ", "storyboard, 2008"), ("Anira and team", "shadow-art animation, 2009")]),
]
# The keys, with arrows drawn as solid triangles: Mincho's arrows are thin
# hairlines at this size.
KEYS = ["Space play", "  ·  ", "<", ">", " 10 seconds", "  ·  ", "^", "v", " volume", "  ·  ",
        "M mute", "  ·  ", "R repeat"]
ARROW = 11  # each triangle's width and height


class Screen:
    """The type's coverage in each of its three colors, antialiased.
    Shippori Mincho has no Greek, so Greek is set in Noto Serif."""

    def __init__(self, fonts):
        self.layers = [Image.new("L", (W, H), 0) for _ in PLANES]
        self.draws = [ImageDraw.Draw(im) for im in self.layers]
        semi, extra = (os.path.join(fonts, f"ShipporiMincho-{w}.ttf") for w in ("SemiBold", "ExtraBold"))
        self.font = {
            "title": ImageFont.truetype(extra, 56), "sub": ImageFont.truetype(semi, 20),
            "head": ImageFont.truetype(extra, 15), "name": ImageFont.truetype(semi, 18),
            "small": ImageFont.truetype(semi, 16),
        }
        self.greek = ImageFont.truetype(os.path.join(fonts, "NotoSerif.ttf"), 17)
        self.greek.set_variation_by_name("SemiBold")

    def face(self, font, text):
        return self.greek if any("\u0370" <= ch <= "\u03ff" for ch in text) else self.font[font]

    def width(self, font, text):
        return self.draws[0].textlength(text, font=self.face(font, text))

    def text(self, plane, font, text, x, y):
        self.draws[plane].text((x, y), text, font=self.face(font, text), fill=255, anchor="ls")

    def center(self, plane, font, text, y):
        self.text(plane, font, text, round((W - self.width(font, text)) / 2), y)

    def keys(self, plane, font, parts, y):
        """A line of text and arrows, centered; an arrow sits on the
        middle of the lowercase letters."""
        arrows = {"<", ">", "^", "v"}
        widths = [ARROW + 5 if p in arrows else self.width(font, p) for p in parts]
        x = (W - sum(widths)) / 2
        mid = y - 5
        for p, w in zip(parts, widths):
            if p in arrows:
                a, h = x, ARROW / 2
                tri = {"<": [(a, mid), (a + ARROW, mid - h), (a + ARROW, mid + h)],
                       ">": [(a + ARROW, mid), (a, mid - h), (a, mid + h)],
                       "^": [(a + h, mid - h), (a, mid + h), (a + ARROW, mid + h)],
                       "v": [(a + h, mid + h), (a, mid - h), (a + ARROW, mid - h)]}[p]
                self.draws[plane].polygon(tri, fill=255)
            else:
                self.text(plane, font, p, round(x), y)
            x += w

    def coverage(self):
        return np.stack([np.array(im, np.float64) / 255 for im in self.layers])


def layout(s):
    s.center(BUTTER, "title", "Bad Apple!!", 84)
    s.center(WHITE, "small", "for the Picocomputer 6502", 118)

    # Three columns, centered as a block: heading, name, role.
    gap = 28
    head_w = max(s.width("head", h) for h, _ in CREDITS)
    name_w = max(s.width("name", n) for _, rows in CREDITS for n, _ in rows)
    role_w = max(s.width("small", r) for _, rows in CREDITS for _, r in rows)
    x0 = round((W - (head_w + gap + name_w + gap + role_w)) / 2)
    x_name, x_role = x0 + head_w + gap, x0 + head_w + gap + name_w + gap
    y = 178
    for head, rows in CREDITS:
        s.text(LILAC, "head", head, x0, y)
        for name, role in rows:
            s.text(WHITE, "name", name, x_name, y)
            s.text(LILAC, "small", role, x_role, y)
            y += 24
        y += 14

    s.center(BUTTER, "sub", "Click or press Space to play", 352)
    s.keys(WHITE, "small", KEYS, 380)


def to_linear(c):
    c = np.asarray(c, np.float64) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055)
    return np.clip(np.rint(c * 255), 0, 255).astype(int)


def palette():
    """Color 0 black, then each pastel at 1/5 to 5/5 of its light."""
    rgb = [(0, 0, 0)]
    for name in PLANES:
        for level in range(1, LEVELS + 1):
            rgb.append(tuple(int(v) for v in to_srgb(to_linear(COLORS[name]) * level / LEVELS)))
    return rgb


def rgb555(r, g, b):
    return (b >> 3) << 11 | (g >> 3) << 6 | 1 << 5 | r >> 3


def indexed(cov):
    """Each pixel's palette index: the color with the most coverage, in the
    step nearest its coverage."""
    color, amount = cov.argmax(0), cov.max(0)
    level = np.rint(amount * LEVELS).astype(int)
    return np.where(level > 0, 1 + color * LEVELS + level - 1, 0)


def tiles_and_map(idx):
    """Bands of rows, each with up to 256 tiles, tile 0 black, and the map."""
    cells = idx.reshape(ROWS, TILE, COLS, TILE).transpose(0, 2, 1, 3)
    packed = (cells[..., 0::2] << 4 | cells[..., 1::2]).astype(np.uint8).reshape(ROWS, COLS, TILE * TILE // 2)
    black = bytes(TILE * TILE // 2)
    bands, sets, out = [], [], bytearray(ROWS * COLS)
    index, tiles = None, None
    for r in range(ROWS):
        row = [packed[r, c].tobytes() for c in range(COLS)]
        if index is None or len(set(tiles) | set(row)) > 256:
            index, tiles = {black: 0}, [black]
            bands.append(r)
            sets.append(tiles)
        for c, key in enumerate(row):
            if key not in index:
                index[key] = len(tiles)
                tiles.append(key)
            out[r * COLS + c] = index[key]
    return bands, sets, bytes(out)


# The gel-disc transport, paused at 0:00, for the preview, at full
# resolution: drawn four times larger, then scaled down, so its edges are
# smooth, as 4-bit sprites can draw them.
def draw_transport(img, fonts):
    k = 4
    over = Image.new("RGBA", (W * k, 64 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    cy, top = 444, H - 64

    def P(x, y):
        return (x * k, (y - top) * k)

    def disc(cx, r, c):
        d.ellipse([P(cx - r, cy - r), P(cx + r, cy + r)], fill=COLORS[c] + (255,))

    def poly(pts, c):
        d.polygon([P(x, y) for x, y in pts], fill=COLORS[c] + (255,))

    for cx, gel in [(32, "sky"), (72, "butter"), (112, "sky"), (512, "mint"), (556, "lilac")]:
        disc(cx, 16, "char")
        disc(cx, 14, gel)
    poly([(23, cy), (31, cy - 7), (31, cy + 7)], "char")          # back 10 s
    poly([(31, cy), (39, cy - 7), (39, cy + 7)], "char")
    poly([(67, cy - 8), (67, cy + 8), (80, cy)], "char")          # play
    poly([(121, cy), (113, cy - 7), (113, cy + 7)], "char")       # forward 10 s
    poly([(113, cy), (105, cy - 7), (105, cy + 7)], "char")
    w = 2                                                         # repeat: a loop with an arrow on each run
    d.rounded_rectangle([P(503, cy - 6), P(521, cy + 6)], radius=6 * k, outline=COLORS["char"] + (255,), width=w * k)
    poly([(514, cy - 10), (520, cy - 6), (514, cy - 2)], "char")
    poly([(510, cy + 2), (504, cy + 6), (510, cy + 10)], "char")
    d.rectangle([P(546, cy - 4), P(551, cy + 4)], fill=COLORS["char"] + (255,))   # speaker
    poly([(551, cy - 4), (558, cy - 9), (558, cy + 9), (551, cy + 4)], "char")
    for r in (5, 9):
        d.arc([P(556 - r, cy - r), P(556 + r, cy + r)], -45, 45, fill=COLORS["char"] + (255,), width=2 * k)
    d.rounded_rectangle([P(148, cy - 4), P(472, cy + 4)], radius=4 * k, fill=COLORS["char"] + (255,))
    d.rounded_rectangle([P(150, cy - 2), P(470, cy + 2)], radius=2 * k, fill=COLORS["lilac"] + (255,))
    disc(150, 8, "char")
    disc(150, 6, "peach")
    d.rounded_rectangle([P(580, cy - 4), P(626, cy + 4)], radius=4 * k, fill=COLORS["char"] + (255,))
    d.rounded_rectangle([P(582, cy - 2), P(624, cy + 2)], radius=2 * k, fill=COLORS["mint"] + (255,))
    font = ImageFont.truetype(os.path.join(fonts, "ShipporiMincho-ExtraBold.ttf"), 13 * k)
    tw = d.textlength("0:00", font=font) / k
    d.rounded_rectangle([P(150 - tw / 2 - 6, 414), P(150 + tw / 2 + 6, 430)], radius=8 * k, fill=COLORS["char"] + (255,))
    d.rounded_rectangle([P(150 - tw / 2 - 5, 415), P(150 + tw / 2 + 5, 429)], radius=7 * k, fill=COLORS["butter"] + (255,))
    d.text(P(150, 427), "0:00", font=font, fill=COLORS["char"] + (255,), anchor="ms")
    small = over.resize((W, 64), Image.LANCZOS)
    img.paste(small, (0, top), small)


def build(out, fonts):
    """Writes title.bin and title.png to out; returns a line about them."""
    s = Screen(fonts)
    layout(s)
    cov = s.coverage()
    assert not cov[:, TEXT_BOTTOM:].any(), "text runs into the transport"
    idx = indexed(cov)
    bands, sets, tmap = tiles_and_map(idx)
    assert len(bands) <= 4, f"{len(bands)} bands; the player has room for 4"
    rgb = palette()
    with open(os.path.join(out, "title.bin"), "wb") as f:
        f.write(b"TTL1" + bytes([len(bands)] + bands) + bytes(16 - 5 - len(bands)))
        f.write(b"".join(rgb555(*c).to_bytes(2, "little") for c in rgb))
        for tiles in sets:
            f.write(b"".join(tiles) + bytes(32 * (256 - len(tiles))))
        f.write(tmap)

    # Draw the screen back from the tiles and the map, as the VGA will.
    shown = np.zeros((H, W), int)
    for band, first in enumerate(bands):
        last = bands[band + 1] if band + 1 < len(bands) else ROWS
        for r in range(first, last):
            for c in range(COLS):
                t = np.frombuffer(sets[band][tmap[r * COLS + c]], np.uint8).reshape(TILE, TILE // 2)
                shown[r * TILE:(r + 1) * TILE, c * TILE:c * TILE + TILE:2] = t >> 4
                shown[r * TILE:(r + 1) * TILE, c * TILE + 1:c * TILE + TILE:2] = t & 15
    assert np.array_equal(shown, idx), "the tiles do not draw the screen"
    img = Image.fromarray(np.array([[c >> 3 << 3 | c >> 5 for c in rgb[i]] for i in range(16)], np.uint8)[shown])
    draw_transport(img, fonts)
    img.save(os.path.join(out, "title.png"))
    return (f"title.bin: {len(bands)} bands from rows {bands}, tiles {[len(t) - 1 for t in sets]} of 255; "
            f"{len(bands) * 8192 + 4800 + 32:,} bytes of XRAM")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/encoded", help="output directory")
    ap.add_argument("--fonts", default="data/fonts", help="folder of ShipporiMincho-SemiBold.ttf and -ExtraBold.ttf")
    args = ap.parse_args()
    print(build(args.out, args.fonts))
    print(f"Wrote title.bin and title.png to {args.out}")


if __name__ == "__main__":
    sys.exit(main())

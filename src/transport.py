#!/usr/bin/env python3
"""Bad Apple!! transport art: the gel discs, as 4-bit mode 5 sprite images.

Each image is drawn eight times larger, then scaled down, so its edges are
smooth. A pixel then takes one of three tones of its palette: the gel, the
charcoal, or one between them for the edges. The outer edge is cut at
half coverage, since a color is either opaque or clear.

Each palette holds its three tones in five ranks: entry 1 + tone * 5 +
rank, and entry 0 clear. A pixel's rank comes from a 4x4 ordered-dither
pattern. The player fades the transport out by turning the ranks clear,
lowest first, so it dissolves in five steps. Solid fills, which the player
stretches by changing a sprite's width, keep one rank throughout, so their
bytes are all alike.

Output, in OUT:
  transport.bin  the palettes, 32 bytes each, in the order of PALETTES,
                 then the images, in the order of IMAGES, rows top down,
                 two pixels a byte, the left one in the high bits.
  transport.png  the images on a gray sheet, to look at.

usage: transport.py [--out data/encoded] [--fonts data/fonts]
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

COLORS = {"peach": (0xF4, 0xC6, 0xB4), "butter": (0xF2, 0xE2, 0xA4), "mint": (0xBC, 0xE2, 0xCF),
          "sky": (0xBC, 0xD5, 0xED), "lilac": (0xD4, 0xC7, 0xEB), "stone": (0xD9, 0xD6, 0xDE),
          "char": (0x3D, 0x3A, 0x42)}
RANKS = 5
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])

# Each palette: its gel, then the charcoal. The middle tone is between them.
PALETTES = ["sky", "butter", "mint", "stone", "lilac", "peach"]
PAL = {name: i for i, name in enumerate(PALETTES)}

K = 8  # drawn K times larger


def tones(gel):
    g, c = np.array(COLORS[gel], float), np.array(COLORS["char"], float)
    return [g, (g + c) / 2, c]  # tone 0 gel, 1 middle, 2 charcoal


def palette(gel):
    out = [0]  # clear
    for tone in tones(gel):
        r, g, b = (int(round(v)) for v in tone)
        out += [(b >> 3) << 11 | (g >> 3) << 6 | 1 << 5 | r >> 3] * RANKS
    return out


class Art:
    """An image drawn large: a canvas of the gel and charcoal over clear."""

    def __init__(self, w, h, gel):
        self.w, self.h, self.gel = w, h, gel
        self.im = Image.new("RGBA", (w * K, h * K), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def c(self, name):
        return COLORS[name] + (255,)

    def disc(self, cx, cy, r, col):
        self.d.ellipse([(cx - r) * K, (cy - r) * K, (cx + r) * K - 1, (cy + r) * K - 1], fill=self.c(col))

    def poly(self, pts, col):
        self.d.polygon([(x * K, y * K) for x, y in pts], fill=self.c(col))

    def rrect(self, x0, y0, x1, y1, r, col):
        self.d.rounded_rectangle([x0 * K, y0 * K, x1 * K - 1, y1 * K - 1], radius=r * K, fill=self.c(col))

    def pixels(self, solid=None):
        """4-bit indices: clear, or 1 + tone * RANKS + rank."""
        small = np.array(self.im.resize((self.w, self.h), Image.BOX), float)
        alpha = small[..., 3] / 255
        rgb = small[..., :3] / np.maximum(alpha[..., None], 1e-6)
        t = np.array(tones(self.gel))
        tone = np.argmin(((rgb[:, :, None, :] - t[None, None]) ** 2).sum(-1), axis=2)
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        rank = BAYER[ys % 4, xs % 4] * RANKS // 16 if solid is None else np.full((self.h, self.w), solid)
        return np.where(alpha >= 0.5, 1 + tone * RANKS + rank, 0)


def disc_image(gel, icon):
    a = Art(32, 32, gel)
    a.disc(16, 16, 16, "char")
    a.disc(16, 16, 14, gel)
    icon(a, 16, 16)
    return a


def back(a, x, y):
    a.poly([(x - 9, y), (x - 1, y - 7), (x - 1, y + 7)], "char")
    a.poly([(x - 1, y), (x + 7, y - 7), (x + 7, y + 7)], "char")


def forward(a, x, y):
    a.poly([(x + 9, y), (x + 1, y - 7), (x + 1, y + 7)], "char")
    a.poly([(x + 1, y), (x - 7, y - 7), (x - 7, y + 7)], "char")


def play(a, x, y):
    a.poly([(x - 5, y - 8), (x - 5, y + 8), (x + 8, y)], "char")


def pause(a, x, y):
    a.rrect(x - 7, y - 7, x - 2, y + 8, 1, "char")
    a.rrect(x + 2, y - 7, x + 7, y + 8, 1, "char")


def repeat(a, x, y):
    a.d.rounded_rectangle([(x - 9) * K, (y - 6) * K, (x + 9) * K - 1, (y + 6) * K - 1], radius=6 * K,
                          outline=a.c("char"), width=2 * K)
    a.poly([(x + 2, y - 10), (x + 8, y - 6), (x + 2, y - 2)], "char")
    a.poly([(x - 2, y + 2), (x - 8, y + 6), (x - 2, y + 10)], "char")
    a.rrect(x - 1, y - 8, x + 3, y - 4, 0, a.gel)  # gaps where the arrows leave the loop
    a.rrect(x - 3, y + 4, x + 1, y + 8, 0, a.gel)
    a.poly([(x + 2, y - 10), (x + 8, y - 6), (x + 2, y - 2)], "char")
    a.poly([(x - 2, y + 2), (x - 8, y + 6), (x - 2, y + 10)], "char")


def speaker(a, x, y, waves=True):
    a.rrect(x - 10, y - 4, x - 5, y + 4, 0, "char")
    a.poly([(x - 5, y - 4), (x + 2, y - 9), (x + 2, y + 9), (x - 5, y + 4)], "char")
    if waves:
        for r in (5, 9):
            a.d.arc([(x + 1 - r) * K, (y - r) * K, (x + 1 + r) * K, (y + r) * K], -45, 45, fill=a.c("char"), width=2 * K)
    else:
        a.d.line([(x + 4) * K, (y - 5) * K, (x + 11) * K, (y + 5) * K], fill=a.c("char"), width=2 * K)
        a.d.line([(x + 4) * K, (y + 5) * K, (x + 11) * K, (y - 5) * K], fill=a.c("char"), width=2 * K)


def track_piece(kind, gel):
    """64x8: charcoal edge, gel inside; a rounded end on the left or right."""
    a = Art(64, 8, gel)
    x0 = 0 if kind == "left" else -8
    x1 = 64 if kind == "right" else 72
    a.rrect(x0, 0, x1, 8, 4, "char")
    a.rrect(x0 + 2, 2, x1 - 2, 6, 2, gel)
    return a


def solid(w, h, gel):
    a = Art(w, h, gel)
    a.rrect(0, 0, w, h, 0, gel)
    return a


def playhead():
    a = Art(16, 16, "peach")
    a.disc(8, 8, 8, "char")
    a.disc(8, 8, 6, "peach")
    return a


def label():
    a = Art(48, 16, "butter")
    a.rrect(0, 0, 48, 16, 8, "char")
    a.rrect(1, 1, 47, 15, 7, "butter")
    return a


def digit(ch, font):
    """On butter, so its edges blend into the label's color, not clear."""
    a = Art(8, 12, "butter")
    a.rrect(0, 0, 8, 12, 0, "butter")
    a.d.text((4 * K, 10.5 * K), ch, font=font, fill=a.c("char"), anchor="ms")
    return a


def pointer():
    a = Art(12, 20, "butter")
    pts = [(1, 1), (1, 16), (4.5, 12.5), (7, 18), (9.5, 17), (7, 11.5), (11.5, 11.5)]
    a.poly(pts, "char")
    inner = [(2.6, 4.6), (2.6, 13), (5, 10.6), (7.6, 16.2), (8, 16), (5.6, 10.2), (8.4, 10.2)]
    a.poly(inner, "butter")
    return a


def images(fonts):
    font = ImageFont.truetype(os.path.join(fonts, "ShipporiMincho-ExtraBold.ttf"), 13 * K)
    out = [
        ("back", disc_image("sky", back), "sky", None),
        ("play", disc_image("butter", play), "butter", None),
        ("pause", disc_image("butter", pause), "butter", None),
        ("forward", disc_image("sky", forward), "sky", None),
        ("repeat on", disc_image("mint", repeat), "mint", None),
        ("repeat off", disc_image("stone", repeat), "stone", None),
        ("speaker", disc_image("lilac", speaker), "lilac", None),
        ("muted", disc_image("lilac", lambda a, x, y: speaker(a, x, y, False)), "lilac", None),
        ("track left", track_piece("left", "lilac"), "lilac", None),
        ("track", track_piece("middle", "lilac"), "lilac", None),
        ("track right", track_piece("right", "lilac"), "lilac", None),
        ("fill", solid(64, 4, "peach"), "peach", 2),
        ("playhead", playhead(), "peach", None),
        ("label", label(), "butter", None),
    ]
    out += [(f"digit {ch}", digit(ch, font), "butter", None) for ch in "0123456789:"]
    vt = Art(48, 8, "lilac")
    vt.rrect(0, 0, 48, 8, 4, "char")
    vt.rrect(2, 2, 46, 6, 2, "lilac")
    out += [
        ("volume track", vt, "lilac", None),
        ("volume fill", solid(48, 4, "mint"), "mint", 2),
        ("pointer", pointer(), "butter", None),
    ]
    return out


def pack(px):
    return (px[:, 0::2] << 4 | px[:, 1::2]).astype(np.uint8).tobytes()


def build(out, fonts):
    """Writes transport.bin and transport.png to out; returns a line about them."""
    imgs = images(fonts)
    pals = [palette(g) for g in PALETTES]
    data = bytearray()
    for p in pals:
        data += b"".join(v.to_bytes(2, "little") for v in p)
    sheet = Image.new("RGB", (8 + sum(a.w + 8 for _, a, _, _ in imgs[:14]), 120), (110, 108, 116))
    x, y = 8, 8
    for name, art, pal, solid_rank in imgs:
        assert art.w % 4 == 0 and art.h % 4 == 0 and 4 <= art.w <= 64 and 4 <= art.h <= 64, name
        assert art.gel == pal, name
        px = art.pixels(solid_rank)
        data += pack(px)
        colors = palette(pal)
        rgb = np.array([[(c & 31) << 3, (c >> 6 & 31) << 3, (c >> 11 & 31) << 3] for c in colors], np.uint8)
        im = Image.fromarray(rgb[px])
        mask = Image.fromarray(((px > 0) * 255).astype(np.uint8))
        if x + art.w > sheet.width - 8:
            x, y = 8, y + 44
        sheet.paste(im, (x, y), mask)
        x += art.w + 8
    with open(os.path.join(out, "transport.bin"), "wb") as f:
        f.write(data)
    sheet.save(os.path.join(out, "transport.png"))
    return f"transport.bin: {len(pals)} palettes, {len(imgs)} images, {len(data):,} bytes"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/encoded", help="output directory")
    ap.add_argument("--fonts", default="data/fonts", help="folder of ShipporiMincho-ExtraBold.ttf")
    args = ap.parse_args()
    print(build(args.out, args.fonts))


if __name__ == "__main__":
    sys.exit(main())

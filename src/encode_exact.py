#!/usr/bin/env python3
"""Bad Apple!! encoder, experimental: exact tiles, uploaded as they are needed.

Each frame is cut into 80x60 tiles of its own pixels, so thin lines, like a
broom handle narrower than a cell, keep every piece. The source is scaled to
640x480 and cut at EDGE; real gray, found as in encode.py, is drawn as a
checkerboard.

The three planes hold 765 tiles at a time, 255 each after the empty tile 0,
and a tile can show from any plane: plane 0 is opaque black under it, and
black is clear on planes 1 and 2. The stream uploads each frame's new tiles
into slots that the frame on screen does not use, and keeps tiles that stay
where they are. A frame may use at most PER_FRAME tiles, so it and the frame
on screen always fit; a busier frame shows its rarest tiles as the nearest
one it keeps, counting border pixels BORDER_WEIGHT times.

Every write in the stream is to an XRAM address: the tiles at 0, the two map
buffers from 6144, frame n in buffer n % 2. The player does what the stream
says.

frames.bin   16-byte header ("BAD6", frame count, first source frame, fps,
             length of frame 0's block), then per frame its block and its
             sound. A block: the next block's length (2 bytes), flags (1
             byte; 1 clears the frame's map buffer first), then writes of
             an XRAM address (2 bytes), a count (1 to 255), and that many
             bytes, then FF FF. The first two frames of each second are
             keyframes: their buffers are cleared, and they upload every
             tile they use, so the player can start there.

usage: encode_exact.py video [--seconds N] [--start S] [--out DIR] [--archive A]
"""

import argparse
import os
import struct
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encode as E  # noqa: E402
import title  # noqa: E402
import transport  # noqa: E402

W, H, TILE = 640, 480, 8
COLS, ROWS = W // TILE, H // TILE
CELLS = COLS * ROWS
LAYERS = 3
SLOTS_PER_LAYER = 255
SLOTS = LAYERS * SLOTS_PER_LAYER
PER_FRAME = SLOTS // 2
XRAM_TILES = 0
XRAM_MAPS = LAYERS * 256 * TILE
FRAME_BYTES = LAYERS * CELLS
END = b"\xff\xff"
KEYFRAME = 1

Y, X = np.mgrid[0:H, 0:W]
CHECKER = (X + Y) % 2 == 1
TY, TX = np.mgrid[0:TILE, 0:TILE]
BORDER = np.where((TX == 0) | (TX == TILE - 1) | (TY == 0) | (TY == TILE - 1), 4, 1).ravel()


def composite(img, lo, hi, opening, edge):
    """The frame's 640x480 pixels: the edge, and real gray as a checkerboard."""
    real = E.opening((img > lo) & (img < hi), opening)
    big = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)) / 255
    real_big = np.asarray(Image.fromarray(real.astype(np.uint8) * 255).resize((W, H), Image.BILINEAR)) >= 128
    return ((big >= edge) & ~real_big) | (real_big & CHECKER)


def cells_of(pixels):
    """Each cell's tile as 8 row bytes, leftmost pixel in the high bit."""
    return np.packbits(pixels.reshape(ROWS, TILE, COLS, TILE).transpose(0, 2, 1, 3).reshape(CELLS, 64),
                       axis=1)


def runs(writes, gap):
    """(address, bytes) writes to the stream's runs. Writes that touch, or
    are within gap bytes, join into one run, carrying the bytes between from
    xram, the player's XRAM as it will be."""
    merged = []
    for addr, data in sorted(writes):
        if merged and addr - (merged[-1][0] + len(merged[-1][1])) <= gap:
            a, d = merged[-1]
            fill = bytes(XRAM_MODEL[a + len(d):addr])
            merged[-1] = (a, d + fill + data)
        else:
            merged.append((addr, bytes(data)))
    out = bytearray()
    for addr, data in merged:
        XRAM_MODEL[addr:addr + len(data)] = np.frombuffer(data, np.uint8)
        for at in range(0, len(data), 255):
            piece = data[at:at + 255]
            out += struct.pack("<HB", addr + at, len(piece)) + piece
    return bytes(out), len(merged), 0


XRAM_MODEL = np.zeros(65536, np.uint8)


GAP = 4


def map_runs(addr0, cur, prev):
    """Runs that turn map bytes prev into cur, with gaps of up to 4 carried."""
    changed = np.flatnonzero(cur != prev)
    out = []
    i = 0
    while i < len(changed):
        start = end = int(changed[i])
        i += 1
        while i < len(changed) and changed[i] - end <= GAP + 1 and changed[i] - start < 255:
            end = int(changed[i])
            i += 1
        out.append((addr0 + start, cur[start:end + 1].tobytes()))
    return out


class Slots:
    """Which tile each of the 765 slots holds, as the player's XRAM will."""

    def __init__(self, in_order):
        self.in_order = in_order          # fill free slots lowest first, so uploads join
        self.content = [None] * SLOTS     # tile bytes, or None when unknown
        self.where = {}                   # tile bytes to slot
        self.used = [0] * SLOTS           # the frame that last used it
        self.showing = set()              # slots the frame on screen uses

    def forget(self):
        """After a seek the slots hold anything: trust none of them."""
        self.content = [None] * SLOTS
        self.where = {}

    def place(self, tiles, n):
        """Slots for this frame's tiles; returns {tile: slot} and uploads."""
        slot_of, uploads, taken = {}, [], set()
        for t in tiles:
            s = self.where.get(t)
            if s is not None:
                slot_of[t] = s
                taken.add(s)
        free = [s for s in range(SLOTS) if s not in self.showing and s not in taken]
        if not self.in_order:
            free.sort(key=lambda s: self.used[s])
        fi = 0
        for t in tiles:
            if t in slot_of:
                continue
            s = free[fi]
            fi += 1
            old = self.content[s]
            if old is not None and self.where.get(old) == s:
                del self.where[old]
            self.content[s] = t
            self.where[t] = s
            slot_of[t] = s
            uploads.append(s)
        for s in slot_of.values():
            self.used[s] = n
        return slot_of, uploads


def budget(cells, limit):
    """At most limit distinct tiles: the rarest become their nearest kept."""
    keys = [c.tobytes() for c in cells]
    count = {}
    for k in keys:
        count[k] = count.get(k, 0) + 1
    count.pop(bytes(TILE), None)
    if len(count) <= limit:
        return keys, 0
    ranked = sorted(count, key=lambda k: -count[k])
    kept = ranked[:limit]
    kept_px = np.unpackbits(np.frombuffer(b"".join(kept), np.uint8).reshape(-1, TILE), axis=1).astype(np.int16)
    swap = {}
    for k in ranked[limit:]:
        px = np.unpackbits(np.frombuffer(k, np.uint8)).astype(np.int16)
        swap[k] = kept[int(np.argmin((np.abs(kept_px - px) * BORDER).sum(axis=1)))]
    return [swap.get(k, k) for k in keys], sum(count[k] for k in ranked[limit:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", default="data/encoded")
    ap.add_argument("--archive")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--gray-lo", type=int, default=31)
    ap.add_argument("--gray-hi", type=int, default=254)
    ap.add_argument("--opening", type=int, default=12)
    ap.add_argument("--edge", type=int, default=127)
    ap.add_argument("--fonts", default="data/fonts")
    ap.add_argument("--gap", type=int, default=4, help="unchanged bytes a run carries rather than start another")
    ap.add_argument("--lru", action="store_true", help="fill the slots least recently used first")
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.archive is None:
        whole = args.start == 0 and args.seconds is None
        args.archive = "src/badapple.tar.xz" if whole else os.path.join(args.out, "badapple.tar.xz")
    global GAP
    GAP = args.gap
    first = round(args.start * E.FPS)
    count = round(args.seconds * E.FPS) if args.seconds else None

    t0 = time.time()
    slots = Slots(not args.lru)
    cost = []
    buffers = [np.zeros(FRAME_BYTES, np.uint8) for _ in range(2)]
    blocks, shown, stand_in_cells, uploaded = [], [], 0, 0
    n = 0
    for img in E.read_frames(args.video, first, count):
        target = cells_of(composite(img, args.gray_lo / 255, args.gray_hi / 255, args.opening, args.edge / 255))
        keys, replaced = budget(target, PER_FRAME)
        stand_in_cells += replaced
        key = n % E.FPS < 2
        if n % E.FPS == 0:
            slots.forget()
        tiles = sorted(set(keys) - {bytes(TILE)})
        slot_of, uploads = slots.place(tiles, n)
        uploaded += len(uploads)
        writes = [(XRAM_TILES + (s // SLOTS_PER_LAYER) * 256 * TILE + (s % SLOTS_PER_LAYER + 1) * TILE,
                   slots.content[s]) for s in uploads]
        maps = np.zeros(FRAME_BYTES, np.uint8)
        for cell, k in enumerate(keys):
            if k != bytes(TILE):
                s = slot_of[k]
                maps[(s // SLOTS_PER_LAYER) * CELLS + cell] = s % SLOTS_PER_LAYER + 1
        buf = n % 2
        prev = np.zeros(FRAME_BYTES, np.uint8) if key else buffers[buf]
        if key:
            XRAM_MODEL[XRAM_MAPS + buf * FRAME_BYTES:XRAM_MAPS + (buf + 1) * FRAME_BYTES] = 0
        writes += map_runs(XRAM_MAPS + buf * FRAME_BYTES, maps, prev)
        buffers[buf] = maps
        block, nruns, _ = runs(writes, args.gap)
        nbytes = len(block) - 3 * nruns
        cost.append(nruns * 70 + nbytes * 8.6 + (FRAME_BYTES * 4.5 if key else 0))
        blocks.append((KEYFRAME if key else 0, block))
        shown.append(keys)
        slots.showing = set(slot_of.values())
        n += 1
    count = n
    encode_seconds = time.time() - t0

    audio = E.read_audio(args.video, first, count)
    lengths = [3 + len(r) + len(END) for _, r in blocks] + [0]
    offsets = []
    with open(os.path.join(args.out, "frames.bin"), "wb") as f:
        f.write(b"BAD6" + struct.pack("<HHBH", count, first, E.FPS, lengths[0]) + bytes(5))
        for i, (flags, r) in enumerate(blocks):
            offsets.append(f.tell())
            f.write(struct.pack("<HB", lengths[i + 1], flags) + r + END + E.frame_audio(audio, i))
    with open(os.path.join(args.out, "index.bin"), "wb") as f:
        for i in range(0, count, E.FPS):
            f.write(struct.pack("<IH", offsets[i], lengths[i]))

    # Play it back as the player does, into a model of XRAM, starting both at
    # 0:00 and at every second, and check each frame's cells at its flip.
    data = open(os.path.join(args.out, "frames.bin"), "rb").read()

    def play(start_second, frames):
        xram = np.zeros(65536, np.uint8)
        at = offsets[start_second * E.FPS]
        length = lengths[start_second * E.FPS]
        for i in range(start_second * E.FPS, start_second * E.FPS + frames):
            next_len, flags = struct.unpack_from("<HB", data, at)
            buf = i % 2
            if flags & KEYFRAME:
                xram[XRAM_MAPS + buf * FRAME_BYTES:XRAM_MAPS + (buf + 1) * FRAME_BYTES] = 0
            p = at + 3
            while data[p:p + 2] != END:
                addr, cnt = struct.unpack_from("<HB", data, p)
                xram[addr:addr + cnt] = np.frombuffer(data, np.uint8, cnt, p + 3)
                p += 3 + cnt
            maps = xram[XRAM_MAPS + buf * FRAME_BYTES:XRAM_MAPS + (buf + 1) * FRAME_BYTES].reshape(LAYERS, CELLS)
            tiles = xram[:LAYERS * 256 * TILE].reshape(LAYERS, 256, TILE)
            got = tiles[0][maps[0]] | tiles[1][maps[1]] | tiles[2][maps[2]]
            want = np.frombuffer(b"".join(shown[i]), np.uint8).reshape(CELLS, TILE)
            assert np.array_equal(got, want), f"frame {i} differs, started at {start_second} s"
            at += length + E.SOUND_BYTES
            length = next_len

    if not args.no_check:
        play(0, count)
        for second in range(1, (count + E.FPS - 1) // E.FPS):
            play(second, min(2 * E.FPS, count - second * E.FPS))
    c = np.array(cost)
    print(f"6502 cycles a frame for decoding, estimated: mean {c.mean():,.0f}, 99.9th {np.percentile(c, 99.9):,.0f}, "
          f"max {c.max():,.0f}, of 266,667")

    print(f"Encoded {count} frames in {encode_seconds:.0f} s; {uploaded} tiles uploaded, "
          f"{uploaded / count:.0f} a frame; {stand_in_cells} of {count * CELLS} cells use a stand-in")
    print(f"Wrote frames.bin ({len(data):,} bytes) and index.bin; blocks average "
          f"{sum(lengths) / count:.0f} bytes, {max(lengths):,} at most")
    print(title.build(args.out, args.fonts))
    print(transport.build(args.out, args.fonts))
    E.write_archive(args.archive, args.out, ["frames.bin", "index.bin", "title.bin", "transport.bin"])
    print(f"Wrote {args.archive} ({os.path.getsize(args.archive):,} bytes)")


if __name__ == "__main__":
    sys.exit(main())

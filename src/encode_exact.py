#!/usr/bin/env python3
"""Bad Apple!! encoder: exact tiles, uploaded as they are needed.

Each frame is cut into 80x60 tiles of its own pixels, so thin lines, like a
broom handle narrower than a cell, keep every piece. The source is scaled to
640x480 and cut at EDGE; real gray is drawn in Bayer dots, a level a pixel.
Real gray is what survives an opening that grows with the frame's motion,
from 2 pixels in a still scene, which keeps its shadows, to 16 in one in
motion, which drops its motion blur; the motion is averaged over nearby
frames so the opening eases between scenes.

The three planes hold 765 tiles at a time, 255 each after the empty tile 0,
and a tile can show from any plane: plane 0 is opaque black under it, and
black is clear on planes 1 and 2. They work as a cache, planned with the
whole video in view:

- While frame n loads, frame n - 1 is on screen, so their tiles must fit in
  the 765 slots together. Where two frames need more, the later one keeps
  its tiles in common with the earlier and its most used new ones; the rest
  show the nearest it keeps, counting border pixels BORDER_WEIGHT times.
  No frame keeps more than MAX_FRAME, so the next always has room.
- A new tile goes in the slot whose tile is needed again furthest in the
  future, or never (Belady's rule), never one the frame on screen or the
  frame loading uses.
- A frame that costs the 6502 less than TARGET cycles to decode uploads
  tiles that frames up to AHEAD frames later need, while a slot's tile is
  needed later than they are, so a busy frame has less to upload.

Every write in the stream is to an XRAM address: the tiles at 0, the two map
buffers from 6144, frame n in buffer n % 2. The player does what the stream
says.

frames.bin   16-byte header ("BAD8", frame count, first source frame, fps,
             length of frame 0's block), then per frame its block and its
             sound, SOUND_IN bytes of 4-bit DPCM from src/adpcm.c. A block: the next block's length (2 bytes), flags (1
             byte, 0), then writes of an XRAM address (2 bytes), a count (1
             to 255), and that many bytes, then FF FF.
seek.bin     for each second, a seek record: what the stream expects to be
             in XRAM when that second's first frame loads, every tile slot
             and both map buffers. Flags (1 byte; 1 clears both map buffers
             first), then parts of up to 8 KB: a length (2 bytes), the same
             writes, FF FF; then a length of 0.
index.bin    for each second, 12 bytes: the offset of its first frame in
             frames.bin (4), that frame's block length (2), the offset of
             its seek record in seek.bin (4), and the record's length (2).

usage: encode_exact.py video [--seconds N] [--start S] [--out DIR] [--archive A]
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile
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
MAX_FRAME = 700
TARGET = 60000  # cycles
AHEAD = 90
CLEAR_BOTH = 1
SEEK_PART = 8192  # a seek record is read and applied in parts of up to this
PAIRS = E.SOUND_BYTES // E.AUDIO_FRAME  # 1,027 sample pairs a frame
SOUND_IN = 4 + (PAIRS + 31) // 32 + PAIRS  # 1,064 bytes of DPCM a frame
XRAM_TILES = 0
XRAM_MAPS = LAYERS * 256 * TILE
FRAME_BYTES = LAYERS * CELLS
END = b"\xff\xff"

Y, X = np.mgrid[0:H, 0:W]
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]])[Y % 4, X % 4] + 0.5) / 16
TY, TX = np.mgrid[0:TILE, 0:TILE]
BORDER = np.where((TX == 0) | (TX == TILE - 1) | (TY == 0) | (TY == TILE - 1), 4, 1).ravel()


def composite(img, lo, hi, opening, edge, grad, levels, gamma):
    """The frame's 640x480 pixels: the edge, and real gray dithered.

    Real gray is source pixels between lo and hi, and with grad, whose slope
    after a 3x3 box blur is under grad (in 0..255 a pixel). The opening drops
    specks and bands thinner than it. Each pixel of real gray takes one of
    levels + 1 Bayer 4x4 patterns, from the scaled source raised to gamma, as
    the dots light it."""
    gray = (img > lo) & (img < hi)
    if grad:
        pad = np.pad(img, 1, mode="edge")
        soft = sum(pad[y:y + img.shape[0], x:x + img.shape[1]] for y in range(3) for x in range(3)) / 9
        gy, gx = np.gradient(soft)
        gray &= np.hypot(gx, gy) * 255 < grad
    real = E.opening(gray, opening)
    big = np.asarray(Image.fromarray((img * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)) / 255
    real_big = np.asarray(Image.fromarray(real.astype(np.uint8) * 255).resize((W, H), Image.BILINEAR)) >= 128
    dots = np.round(big ** gamma * levels) / levels > BAYER
    return ((big >= edge) & ~real_big) | (real_big & dots)


def shift(a, dy, dx, fill):
    """a moved by (dy, dx), the edge it uncovers set to fill."""
    out = np.full_like(a, fill)
    h, w = a.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def near(mask, limit):
    """Each pixel's distance to the nearest set one, 1 straight and 1.414
    diagonal, exact up to limit."""
    d = np.where(mask, 0.0, np.inf).astype(np.float32)
    for _ in range(int(np.ceil(limit))):
        n = d
        for dy, dx, c in ((0, 1, 1), (0, -1, 1), (1, 0, 1), (-1, 0, 1),
                          (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            n = np.minimum(n, shift(d, dy, dx, np.inf) + np.float32(c))
        d = n
    return d


def dilate(mask, r):
    """Set where any pixel within r, square, is set."""
    o = mask.copy()
    for k in range(1, r + 1):
        o |= shift(mask, 0, k, False) | shift(mask, 0, -k, False)
    m = o.copy()
    for k in range(1, r + 1):
        m |= shift(o, k, 0, False) | shift(o, -k, 0, False)
    return m


def motion_share(cur, neighbors, lo, hi, reach, ramp):
    """How much of the frame's gray moves, 0 to 1. Gray is source bytes
    between lo and hi. Motion blur is gray that comes and goes: a frame
    before or after has no gray within reach pixels. Shadow is gray that
    stays and is wider than a ramp, its distance to the nearest black plus
    to the nearest white over ramp. The share is blur over blur plus shadow,
    as the tuner's shadow test counts it."""
    gray = lambda f: (f > lo) & (f < hi)
    g = gray(cur)
    stay = np.ones_like(g)
    for f in neighbors:
        stay &= dilate(gray(f), reach)
    soft = near(cur <= lo, ramp) + near(cur >= hi, ramp) <= ramp
    blur = (g & ~stay).sum()
    shadow = (g & stay & ~soft).sum()
    return blur / (blur + shadow) if blur + shadow else 0.0


def opening_for(share, args):
    """The opening by motion: args.opening at a share of args.motion_low % or
    less, args.opening_max at args.motion_high % or more, in proportion
    between, so a still scene keeps its shadows and a moving one drops its
    blur."""
    t = (share * 100 - args.motion_low) / max(1e-6, args.motion_high - args.motion_low)
    return round(args.opening + (args.opening_max - args.opening) * min(1, max(0, t)))


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


def cost(nruns, nbytes):
    """The 6502's cycles to apply a block, roughly: a run's setup, then
    about 8.6 cycles a byte through the portals."""
    return nruns * 70 + nbytes * 8.6


def nearest(kept_px, px):
    return int(np.argmin((np.abs(kept_px - px) * BORDER).sum(axis=1)))


def unpack(keys):
    return np.unpackbits(np.array(keys, ">u8").view(np.uint8).reshape(-1, 8), axis=1).astype(np.int16)


def budgets(frames):
    """Each frame's cells, as tile keys, after the limits: with the frame
    before it, no more than SLOTS distinct tiles, and itself no more than
    MAX_FRAME. Returns the cells and the count of cells changed."""
    out, prev, changed = [], set(), 0
    for cells in frames:
        keys, counts = np.unique(cells, return_counts=True)
        count = {int(k): int(c) for k, c in zip(keys, counts) if k}
        shared = [k for k in count if k in prev]
        new = sorted((k for k in count if k not in prev), key=lambda k: -count[k])
        room = min(SLOTS - len(prev), MAX_FRAME - len(shared))
        if len(new) <= room:
            out.append(cells)
            prev = set(count)
            continue
        kept = shared + new[:max(room, 0)]
        kept_px = unpack(kept)
        swap = {k: kept[nearest(kept_px, unpack([k])[0])] for k in new[max(room, 0):]}
        changed += sum(count[k] for k in swap)
        cells = np.array([swap.get(int(k), int(k)) for k in cells], np.uint64)
        out.append(cells)
        prev = set(kept)
    return out, changed


class Plan:
    """The slots, as the player's XRAM will hold them, and when each tile is
    needed next."""

    def __init__(self, frames):
        self.uses = {}
        for n, cells in enumerate(frames):
            for k in np.unique(cells).tolist():
                if k:
                    self.uses.setdefault(k, []).append(n)
        self.content = [0] * SLOTS        # tile key, 0 when empty
        self.where = {}                   # tile key to slot
        self.next_use = np.full(SLOTS, -1, np.int64)  # -1 empty, else frame

    def next_after(self, key, n):
        """The first frame after n that uses key, or a large number."""
        u = self.uses[key]
        i = int(np.searchsorted(u, n, side="right"))
        return u[i] if i < len(u) else 1 << 40

    def victim(self, protect):
        """The slot to take: empty first, else the tile needed furthest away."""
        score = np.where(self.next_use < 0, 1 << 50, self.next_use).astype(np.float64)
        score[list(protect)] = -1
        s = int(np.argmax(score))
        return s if score[s] >= 0 else None

    def put(self, s, key, n):
        old = self.content[s]
        if old and self.where.get(old) == s:
            del self.where[old]
        self.content[s] = key
        self.where[key] = s
        self.next_use[s] = self.next_after(key, n - 1)

    def refresh(self, n):
        """After frame n: each slot's tile's next use after n."""
        for s in np.flatnonzero(self.next_use == n).tolist():
            self.next_use[s] = self.next_after(self.content[s], n)


def tile_addr(s):
    return XRAM_TILES + (s // SLOTS_PER_LAYER) * 256 * TILE + (s % SLOTS_PER_LAYER + 1) * TILE


def tile_bytes(key):
    return int(key).to_bytes(8, "big")


def plan_stream(frames, gap, target, ahead, heavy):
    """Plans the stream: for each frame its block of writes, and for each
    second its seek record. heavy maps a frame to how many of its tiles to
    upload ahead, in cheaper frames before it."""
    global XRAM_MODEL
    XRAM_MODEL = np.zeros(65536, np.uint8)
    count = len(frames)
    plan = Plan(frames)
    heavy = dict(heavy)
    blocks, seeks, costs, uploaded, early = [], [], [], 0, 0
    buffers = [np.zeros(FRAME_BYTES, np.uint8) for _ in range(2)]
    showing = set()                       # slots of the frame on screen
    for n, cells in enumerate(frames):
        if n % E.FPS == 0:
            # A seek starts here: every tile slot and both map buffers as the
            # stream expects them now.
            tiles = XRAM_MODEL[XRAM_TILES:XRAM_MAPS].tobytes()
            writes = [(XRAM_TILES, tiles)]
            for b in range(2):
                nz = np.flatnonzero(buffers[b])
                writes += map_runs(XRAM_MAPS + b * FRAME_BYTES, buffers[b], np.zeros(FRAME_BYTES, np.uint8))
            # In parts of up to SEEK_PART bytes, each read into the ring and
            # applied in turn.
            seek, part = bytearray([CLEAR_BOTH]), bytearray()
            for addr, data in sorted(writes):
                for at in range(0, len(data), 255):
                    piece = data[at:at + 255]
                    run = struct.pack("<HB", addr + at, len(piece)) + piece
                    if len(part) + len(run) + len(END) > SEEK_PART:
                        seek += struct.pack("<H", len(part) + len(END)) + part + END
                        part = bytearray()
                    part += run
            seek += struct.pack("<H", len(part) + len(END)) + part + END + struct.pack("<H", 0)
            seeks.append(bytes(seek))

        keys = set(np.unique(cells).tolist()) - {0}
        protect = set(showing) | {plan.where[k] for k in keys if k in plan.where}
        uploads = []
        for k in sorted(keys - set(plan.where)):
            s_ = plan.victim(protect)
            plan.put(s_, k, n)
            protect.add(s_)
            uploads.append(s_)
        slot_of = {k: plan.where[k] for k in keys}

        maps = np.zeros(FRAME_BYTES, np.uint8)
        nzc = np.flatnonzero(cells)
        for c in nzc.tolist():
            s_ = slot_of[int(cells[c])]
            maps[(s_ // SLOTS_PER_LAYER) * CELLS + c] = s_ % SLOTS_PER_LAYER + 1
        buf = n % 2
        map_writes = map_runs(XRAM_MAPS + buf * FRAME_BYTES, maps, buffers[buf])
        nb = sum(len(d) for _, d in map_writes) + 8 * len(uploads)
        here = cost(len(map_writes) + len(uploads), nb)

        # Upload ahead while this frame is cheap: tiles of the next frames,
        # each into the slot needed furthest away, if that is later.
        if here < target:
            for m in range(n + 1, min(count, n + 1 + ahead)):
                if heavy.get(m, 0) <= 0:
                    continue
                for k in sorted(set(np.unique(frames[m]).tolist()) - {0} - set(plan.where)):
                    if heavy[m] <= 0:
                        break
                    s_ = plan.victim(protect)
                    if s_ is None or (plan.next_use[s_] >= 0 and plan.next_use[s_] <= m):
                        break
                    plan.put(s_, k, n)
                    plan.next_use[s_] = m
                    protect.add(s_)
                    uploads.append(s_)
                    early += 1
                    heavy[m] -= 1
                    here += cost(1, 8)
                    if here >= target:
                        break
                if here >= target:
                    break
        uploaded += len(uploads)

        writes = [(tile_addr(s_), tile_bytes(plan.content[s_])) for s_ in uploads] + map_writes
        block, nruns, _ = runs(writes, gap)
        costs.append(cost(nruns, len(block) - 3 * nruns))
        buffers[buf] = maps
        blocks.append(block)
        plan.refresh(n)
        showing = set(slot_of.values())
    return blocks, seeks, costs, uploaded, early


def encode_sound(audio, shaping, paths):
    """The soundtrack as 4-bit DPCM, SOUND_IN bytes a frame, by src/adpcm.c."""
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "adpcm")
        subprocess.run(["cc", "-O2", "-o", exe, os.path.join(here, "adpcm.c"), "-lm"], check=True)
        out = subprocess.run([exe, str(shaping), str(paths)], input=audio, capture_output=True, check=True).stdout
    assert len(out) == len(audio) // E.SOUND_BYTES * SOUND_IN
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", default="data/encoded")
    ap.add_argument("--archive")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--gray-lo", type=int, default=0)
    ap.add_argument("--gray-hi", type=int, default=255)
    ap.add_argument("--opening", type=int, default=2, help="the opening of a still scene")
    ap.add_argument("--opening-max", type=int, default=16, help="the opening of a scene in motion")
    ap.add_argument("--motion-low", type=float, default=32, help="motion share, %%, at or below which the opening is --opening")
    ap.add_argument("--motion-high", type=float, default=64, help="motion share, %%, at or above which it is --opening-max")
    ap.add_argument("--reach", type=int, default=4, help="pixels gray may move between frames and still count as staying")
    ap.add_argument("--ramp", type=float, default=6, help="pixels wide or less, gray between black and white is a soft edge")
    ap.add_argument("--smooth", type=int, default=8, help="frames each side the motion share is averaged over")
    ap.add_argument("--edge", type=int, default=127)
    ap.add_argument("--grad", type=float, default=0, help="real gray is less steep than this, 0..255 a source pixel; 0 for any")
    ap.add_argument("--levels", type=int, default=16, help="gray levels besides black")
    ap.add_argument("--gamma", type=float, default=1.6, help="the source's brightness to dot coverage")
    ap.add_argument("--fonts", default="data/fonts")
    ap.add_argument("--gap", type=int, default=4, help="unchanged bytes a run carries rather than start another")
    ap.add_argument("--target", type=int, default=TARGET, help="6502 cycles a frame to fill with uploads ahead")
    ap.add_argument("--ahead", type=int, default=AHEAD, help="frames ahead to upload for")
    ap.add_argument("--shaping", type=float, default=0, help="the sound's error fed back; below 0 moves hiss down from the treble")
    ap.add_argument("--paths", type=int, default=16, help="paths the sound encoder's trellis keeps")
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    global GAP
    GAP = args.gap
    if args.archive is None:
        whole = args.start == 0 and args.seconds is None
        args.archive = "src/badapple.tar.xz" if whole else os.path.join(args.out, "badapple.tar.xz")
    first = round(args.start * E.FPS)
    count = round(args.seconds * E.FPS) if args.seconds else None

    # The frames' cells, as 64-bit tile keys, then the limits.
    t0 = time.time()
    raw, openings = [], []

    # Each frame's motion share, from it and its neighbours; then the
    # shares averaged over --smooth frames each side, so the opening eases
    # from one scene's to the next rather than flickering.
    src = lambda f: np.round(f * 255).astype(np.uint8)
    shares = []
    prev = cur = None
    for img in E.read_frames(args.video, first, count):
        img = src(img)
        if cur is not None:
            shares.append(motion_share(cur, [f for f in (prev, img) if f is not None], args.gray_lo, args.gray_hi,
                                       args.reach, args.ramp))
        prev, cur = cur, img
    if cur is not None:
        shares.append(motion_share(cur, [prev] if prev is not None else [], args.gray_lo, args.gray_hi,
                                   args.reach, args.ramp))
    n = args.smooth
    padded = np.pad(np.array(shares), n, mode="edge")
    smoothed = np.convolve(padded, np.ones(2 * n + 1) / (2 * n + 1), mode="valid")
    openings = [opening_for(s, args) for s in smoothed]

    for i, img in enumerate(E.read_frames(args.video, first, count)):
        px = composite(img, args.gray_lo / 255, args.gray_hi / 255, openings[i], args.edge / 255,
                       args.grad, args.levels, args.gamma)
        raw.append(cells_of(px).view(">u8").ravel().astype(np.uint64))
    count = len(raw)
    frames, changed = budgets(raw)
    del raw

    # Plan once with no uploads ahead, to find the frames that cost more
    # than the target; then again, uploading some of their tiles ahead.
    _, _, first_costs, _, _ = plan_stream(frames, args.gap, 0, 0, {})
    heavy = {m: int((c - args.target) / cost(1, 8)) + 1 for m, c in enumerate(first_costs) if c > args.target}
    blocks, seeks, costs, uploaded, early = plan_stream(frames, args.gap, args.target, args.ahead, heavy)
    encode_seconds = time.time() - t0

    sound = encode_sound(E.read_audio(args.video, first, count), args.shaping, args.paths)
    lengths = [3 + len(b) + len(END) for b in blocks] + [0]
    offsets = []
    with open(os.path.join(args.out, "frames.bin"), "wb") as f:
        f.write(b"BAD8" + struct.pack("<HHBH", count, first, E.FPS, lengths[0]) + bytes(5))
        for i, b in enumerate(blocks):
            offsets.append(f.tell())
            f.write(struct.pack("<HB", lengths[i + 1], 0) + b + END + sound[i * SOUND_IN:(i + 1) * SOUND_IN])
    seek_at = []
    with open(os.path.join(args.out, "seek.bin"), "wb") as f:
        for r in seeks:
            seek_at.append(f.tell())
            f.write(r)
    with open(os.path.join(args.out, "index.bin"), "wb") as f:
        for sec, r in enumerate(seeks):
            f.write(struct.pack("<IHIH", offsets[sec * E.FPS], lengths[sec * E.FPS], seek_at[sec], len(r)))

    # Play it back as the player does, into a model of XRAM, from the start
    # and from every second's seek record, and check each frame at its flip.
    data = open(os.path.join(args.out, "frames.bin"), "rb").read()
    seekdata = open(os.path.join(args.out, "seek.bin"), "rb").read()

    def apply(xram, d, at, skip=3):
        p = at + skip
        while d[p:p + 2] != END:
            addr, cnt = struct.unpack_from("<HB", d, p)
            xram[addr:addr + cnt] = np.frombuffer(d, np.uint8, cnt, p + 3)
            p += 3 + cnt

    def play(second, frames_to_check):
        xram = np.random.default_rng(second).integers(0, 256, 65536).astype(np.uint8)
        xram[XRAM_TILES:XRAM_TILES + TILE] = 0
        xram[XRAM_TILES + 256 * TILE:XRAM_TILES + 257 * TILE] = 0
        xram[XRAM_TILES + 512 * TILE:XRAM_TILES + 513 * TILE] = 0
        xram[XRAM_MAPS:XRAM_MAPS + 2 * FRAME_BYTES] = 0
        p = seek_at[second] + 1
        while True:
            plen = struct.unpack_from("<H", seekdata, p)[0]
            if not plen:
                break
            apply(xram, seekdata, p + 2, 0)
            p += 2 + plen
        at, length = offsets[second * E.FPS], lengths[second * E.FPS]
        for i in range(second * E.FPS, second * E.FPS + frames_to_check):
            next_len = struct.unpack_from("<H", data, at)[0]
            apply(xram, data, at)
            buf = i % 2
            maps = xram[XRAM_MAPS + buf * FRAME_BYTES:XRAM_MAPS + (buf + 1) * FRAME_BYTES].reshape(LAYERS, CELLS)
            tiles = xram[:LAYERS * 256 * TILE].reshape(LAYERS, 256, TILE)
            got = tiles[0][maps[0]] | tiles[1][maps[1]] | tiles[2][maps[2]]
            want = np.array([tile_bytes(k) for k in frames[i].tolist()], dtype="S8")
            want = np.frombuffer(want.tobytes(), np.uint8).reshape(CELLS, TILE)
            assert np.array_equal(got, want), f"frame {i} differs, started at {second} s"
            at += length + SOUND_IN
            length = next_len

    if not args.no_check:
        play(0, count)
        for second in range(1, len(seeks)):
            play(second, min(2 * E.FPS, count - second * E.FPS))
    c = np.array(costs)
    o = np.array(openings)
    print(f"Opening by motion: {np.mean(o == args.opening):.0%} of frames at {args.opening}, "
          f"{np.mean(o == args.opening_max):.0%} at {args.opening_max}, mean {o.mean():.1f}")
    print(f"Encoded {count} frames in {encode_seconds:.0f} s; {uploaded} tiles uploaded, {uploaded / count:.0f} a frame, "
          f"{early} of them ahead; {changed} of {count * CELLS} cells show a nearest tile")
    print(f"6502 cycles a frame for decoding, estimated: mean {c.mean():,.0f}, 99.9th {np.percentile(c, 99.9):,.0f}, "
          f"max {c.max():,.0f}, of 266,667")
    print(f"Wrote frames.bin ({len(data):,} bytes), seek.bin ({len(seekdata):,}), index.bin; blocks average "
          f"{sum(lengths) / count:.0f} bytes, {max(lengths):,} at most")
    print(title.build(args.out, args.fonts))
    print(transport.build(args.out, args.fonts))
    E.write_archive(args.archive, args.out, ["frames.bin", "seek.bin", "index.bin", "title.bin", "transport.bin"])
    print(f"Wrote {args.archive} ({os.path.getsize(args.archive):,} bytes)")


if __name__ == "__main__":
    sys.exit(main())

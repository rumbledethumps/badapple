#!/usr/bin/env python3
"""Bad Apple!! encoder: 80x60 marching-squares tiles, three levels, 511 tiles.

Each 512x384 frame is box-filtered to an 81x61 grid of corner samples. Each
of the 80x60 cells becomes one 8x8 1bpp tile on a 640x480 canvas. A dark
line and a light line, both marching-squares iso-lines snapped to SNAP
positions per tile edge, split each tile into black (under the dark
threshold), a checkerboard fill (between), and white (over the light one).

The whole video shares 511 tiles: the 511 it uses most. A cell whose tile
is not among them shows the nearest one, counting pixels on the tile's
border BORDER_WEIGHT times, so outlines stay continuous across tiles.

The 511 tiles live on two mode 2 layers of 256 tiles each. Tile 0 of both
layers is all black, which is transparent on the top layer. A cell shows a
bottom tile under the top layer's tile 0, or a top tile over the bottom
layer's tile 0.

Output, in ARCHIVE, which the build unpacks: tiles.bin and frames.bin,
  below. For the whole video it is src/badapple.tar.xz, the archive the
  build uses; for part of it, OUT/badapple.tar.xz. The archive has fixed
  times and owners, so the same video and settings give the same bytes.

Output, in OUT:
  tiles.bin    4096 bytes: 256 bottom tiles, then 256 top tiles, 8 bytes
               each, one byte per row, leftmost pixel in the high bit.
  frames.bin   16-byte header ("BAD2", frame count, first source frame,
               fps), then a 13,708-byte record per frame, so the player
               reads a frame and its sound together: the 80x60 bottom map
               and the 80x60 top map, one tile ID per byte, 9600 bytes, then
               the frame's sound, 1027 samples, 4108 bytes. The sound is raw
               PCM, 30,810 Hz, 16-bit signed little-endian, stereo, 1 dB
               lower so the resampler does not clip. Niconico's AAC encoder
               kept nothing above about 15.4 kHz, and a rate carries up to
               half of itself, so 30.8 kHz carries it all; 30,810 Hz is the
               next rate with a whole number of samples a frame.
  preview.mp4  the encoded frames as the two layers draw them, with the
               soundtrack of the same span.
  tileset.npz  the 511 tiles, cached for the next run with the same
               thresholds and snapping.
"""

import argparse
import io
import lzma
import os
import struct
import subprocess
import sys
import tarfile
import time

import numpy as np

SRC_W, SRC_H = 512, 384
COLS, ROWS, TILE = 80, 60, 8
FPS = 30
SETS = 511
MAP_BYTES = COLS * ROWS
FRAME_BYTES = 2 * MAP_BYTES
AUDIO_RATE = 30810
AUDIO_FRAME = 4  # bytes per stereo 16-bit sample pair
assert AUDIO_RATE % FPS == 0, "a whole number of samples a frame"
SOUND_BYTES = AUDIO_RATE // FPS * AUDIO_FRAME  # 4108
RECORD_BYTES = FRAME_BYTES + SOUND_BYTES


# Corner samples: a box one cell wide around each of the 81x61 corners.

def box_weights(n_out, n_src):
    cell = n_src / (n_out - 1)
    w = np.zeros((n_out, n_src))
    for i in range(n_out):
        lo, hi = i * cell - cell / 2, i * cell + cell / 2
        for x in range(n_src):
            w[i, x] = max(0.0, min(hi, x + 1) - max(lo, x))
        w[i] /= w[i].sum()
    return w


WY = box_weights(ROWS + 1, SRC_H)
WX = box_weights(COLS + 1, SRC_W)


def read_frames(video, first=0, count=None):
    """Yield the grayscale frames of video from frame first, as 0..1."""
    vf = f"trim=start_frame={first}" + (f":end_frame={first + count}" if count else "")
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", video, "-vf", vf, "-fps_mode", "passthrough",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    n = SRC_W * SRC_H
    while True:
        b = proc.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(SRC_H, SRC_W) / 255.0
    proc.wait()


def corners(img):
    return (WY @ img @ WX.T).astype(np.float32)


# Tile keys. One iso-line in one cell: 4-bit corner case (TL TR BR BL), four
# 3-bit crossing bins (top, right, bottom, left), and a saddle bit.

LINE_BITS = 17


def line_keys(g, thr, k):
    w = g >= thr
    tl, tr, br, bl = w[..., :-1, :-1], w[..., :-1, 1:], w[..., 1:, 1:], w[..., 1:, :-1]
    a, b, c, d = g[..., :-1, :-1], g[..., :-1, 1:], g[..., 1:, 1:], g[..., 1:, :-1]
    case = tl * 8 + tr * 4 + br * 2 + bl
    saddle = (case == 10) | (case == 5)
    kk = np.where(saddle, 1, k)

    def crossing(p, q, wp, wq):
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(wp != wq, (thr - p) / (q - p), 0.0)
        return np.where(wp != wq, np.clip(np.floor(t * kk), 0, kk - 1), 0).astype(np.int64)

    key = (case.astype(np.int64)
           | crossing(a, b, tl, tr) << 4 | crossing(b, c, tr, br) << 7
           | crossing(c, d, br, bl) << 10 | crossing(d, a, bl, tl) << 13)
    linked = saddle & ((a + b + c + d) / 4 >= thr)
    return key | linked.astype(np.int64) << 16


def cell_keys(g, dark, light, k):
    return line_keys(g, dark, k) | line_keys(g, light, k) << LINE_BITS


def inside_polygon(poly):
    """8x8 mask of the pixel centers inside a polygon (even-odd)."""
    ys, xs = np.mgrid[0:TILE, 0:TILE] + 0.5
    mask = np.zeros((TILE, TILE), bool)
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
        if y0 != y1:
            mask ^= ((y0 <= ys) != (y1 <= ys)) & (xs < x0 + (ys - y0) * (x1 - x0) / (y1 - y0))
    return mask


CORNER_XY = [(0.0, 0.0), (TILE, 0.0), (TILE, TILE), (0.0, TILE)]
EDGE_AT = [lambda t: (t, 0.0), lambda t: (TILE, t),
           lambda t: (TILE - t, TILE), lambda t: (0.0, TILE - t)]


def line_mask(key, k):
    """The pixels of a cell on the light side of one iso-line."""
    case = key & 15
    w = [(case >> 3) & 1, (case >> 2) & 1, (case >> 1) & 1, case & 1]
    if case in (0, 15):
        return np.full((TILE, TILE), bool(w[0]))
    saddle = case in (5, 10)
    kk = 1 if saddle else k
    pts = []
    for i in range(4):
        if w[i]:
            pts.append(CORNER_XY[i])
        if w[i] != w[(i + 1) % 4]:
            pts.append(EDGE_AT[i]((((key >> (4 + 3 * i)) & 7) + 0.5) / kk * TILE))
    if saddle and not (key >> 16) & 1:
        # Two light corners, each cut off by its own two crossings.
        mask = np.zeros((TILE, TILE), bool)
        for i, c in enumerate(pts):
            if c in CORNER_XY:
                mask |= inside_polygon([pts[i - 1], c, pts[(i + 1) % len(pts)]])
        return mask
    return inside_polygon(pts)


# Tiles as uint64: bit i is pixel (i % 8, i // 8), 1 is white.

Y, X = np.mgrid[0:TILE, 0:TILE]
CHECKER = (X + Y) % 2 == 1
BIT = np.uint64(1) << np.arange(64, dtype=np.uint64)


def tile_of_key(ckey, k):
    level = line_mask(ckey & ((1 << LINE_BITS) - 1), k).astype(int) + line_mask(ckey >> LINE_BITS, k)
    px = np.where(level == 0, False, np.where(level == 2, True, CHECKER))
    return np.uint64((px.ravel().astype(np.uint64) * BIT).sum())


def tile_pixels(tiles):
    """uint64 tiles to an (n, 64) array of 0/1 pixels."""
    t = np.asarray(tiles, np.uint64)[:, None]
    return ((t >> np.arange(64, dtype=np.uint64)) & np.uint64(1)).astype(np.int64)


def tile_rows(tile):
    """One tile as 8 row bytes, leftmost pixel in the high bit."""
    t = int(tile)
    rows = bytearray()
    for y in range(TILE):
        bits = (t >> (8 * y)) & 0xFF
        rows.append(int(f"{bits:08b}"[::-1], 2))
    return bytes(rows)


class Tiler:
    """Turns frames into tiles, caching each key's tile."""

    def __init__(self, dark, light, snap):
        self.dark, self.light, self.snap = dark, light, snap
        self.tiles = {}

    def keys(self, g):
        return cell_keys(g, self.dark, self.light, self.snap)

    def tile(self, ckey):
        t = self.tiles.get(ckey)
        if t is None:
            t = self.tiles[ckey] = tile_of_key(ckey, self.snap)
        return t


def build_tileset(video, tiler):
    """The SETS tiles the whole video uses most, all-black first."""
    counts = {}
    frames = 0
    for img in read_frames(video):
        keys, n = np.unique(tiler.keys(corners(img)), return_counts=True)
        for key, c in zip(keys.tolist(), n.tolist()):
            counts[key] = counts.get(key, 0) + c
        frames += 1
    use = {}
    for key, c in counts.items():
        t = int(tiler.tile(key))
        use[t] = use.get(t, 0) + c
    ranked = sorted(use, key=lambda t: (-use[t], t))
    kept = [0] + [t for t in ranked if t != 0][:SETS - 1]
    cells = sum(use.values())
    exact = sum(use[t] for t in kept if t in use)
    return np.array(kept, np.uint64), len(use), exact / cells, frames


class Matcher:
    """Maps any tile to its index in the tile set."""

    def __init__(self, kept, border_weight):
        self.kept = kept
        self.index = {int(t): i for i, t in enumerate(kept)}
        self.kept_px = tile_pixels(kept)
        border = (X == 0) | (X == TILE - 1) | (Y == 0) | (Y == TILE - 1)
        self.weight = np.where(border, border_weight, 1).ravel()
        self.stand_ins = {}

    def __call__(self, tile):
        i = self.index.get(int(tile))
        if i is not None:
            return i
        i = self.stand_ins.get(int(tile))
        if i is None:
            # Weighted pixel differences; ties go to the more used tile.
            d = (np.abs(self.kept_px - tile_pixels([tile])) * self.weight).sum(axis=1)
            i = self.stand_ins[int(tile)] = int(np.argmin(d))
        return i


def write_archive(path, folder, names):
    """A .tar.xz of the named files in folder, with fixed times and owners."""
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in names:
            with open(os.path.join(folder, name), "rb") as f:
                data = f.read()
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    with open(path, "wb") as f:
        f.write(lzma.compress(tar_bytes.getvalue(), preset=9 | lzma.PRESET_EXTREME))


def read_audio(video, first, count):
    """The soundtrack of count frames from frame first, as raw PCM."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video, "-ss", f"{first / FPS:.6f}", "-t", f"{count / FPS:.6f}",
         "-vn", "-af", "volume=-1dB", "-ar", str(AUDIO_RATE), "-ac", "2", "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    size = count * SOUND_BYTES
    return raw[:size] + bytes(max(0, size - len(raw)))


def frame_audio(audio, n):
    """Frame n's slice of the soundtrack."""
    return audio[n * SOUND_BYTES:(n + 1) * SOUND_BYTES]


def layer_of(index):
    """Set index to (bottom ID, top ID). Index 0 is the shared black tile."""
    if index == 0:
        return 0, 0
    if index <= 255:
        return index, 0
    return 0, index - 255


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", help="source video, 512x384 at 30 fps")
    ap.add_argument("--out", default="data/encoded", help="output directory")
    ap.add_argument("--archive", help="archive for the build (default: src/badapple.tar.xz for the "
                    "whole video, OUT/badapple.tar.xz for part of it)")
    ap.add_argument("--start", type=float, default=0.0, help="first second to encode")
    ap.add_argument("--seconds", type=float, help="seconds to encode (default: to the end)")
    ap.add_argument("--dark", type=int, default=128, help="dark threshold, of 255")
    ap.add_argument("--light", type=int, default=192, help="light threshold, of 255")
    ap.add_argument("--snap", type=int, default=3, choices=range(1, 9), help="crossing positions per tile edge")
    ap.add_argument("--border-weight", type=int, default=4, help="weight of a border pixel when matching")
    ap.add_argument("--no-preview", action="store_true", help="skip preview.mp4")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.archive is None:
        whole = args.start == 0 and args.seconds is None
        args.archive = "src/badapple.tar.xz" if whole else os.path.join(args.out, "badapple.tar.xz")

    tiler = Tiler(args.dark / 255, args.light / 255, args.snap)
    cache = os.path.join(args.out, "tileset.npz")
    params = np.array([args.dark, args.light, args.snap])
    t0 = time.time()
    if os.path.exists(cache) and np.array_equal(np.load(cache)["params"], params):
        kept = np.load(cache)["kept"]
        print(f"Tile set: {len(kept)} tiles from {cache}")
        set_seconds = None
    else:
        kept, distinct, exact, frames = build_tileset(args.video, tiler)
        np.savez(cache, params=params, kept=kept)
        set_seconds = time.time() - t0
        print(f"Tile set: {distinct} distinct tiles in {frames} frames; the {len(kept)} kept "
              f"cover {100 * exact:.2f}% of cells ({set_seconds:.0f} s)")
    match = Matcher(kept, args.border_weight)

    with open(os.path.join(args.out, "tiles.bin"), "wb") as f:
        for layer in range(2):
            for tid in range(256):
                index = tid if layer == 0 else (0 if tid == 0 else tid + 255)
                f.write(tile_rows(kept[index]))

    first = round(args.start * FPS)
    count = round(args.seconds * FPS) if args.seconds else None
    t1 = time.time()
    shown, maps = [], []
    stand_in_cells = 0
    for img in read_frames(args.video, first, count):
        keys = tiler.keys(corners(img)).ravel()
        bottom, top = bytearray(MAP_BYTES), bytearray(MAP_BYTES)
        frame = np.empty(MAP_BYTES, np.uint64)
        for cell, key in enumerate(keys.tolist()):
            tile = tiler.tile(key)
            i = match(tile)
            stand_in_cells += int(kept[i] != tile)
            frame[cell] = kept[i]
            bottom[cell], top[cell] = layer_of(i)
        shown.append(frame)
        maps.append(bytes(bottom) + bytes(top))
    count = len(maps)
    encode_seconds = time.time() - t1

    audio = read_audio(args.video, first, count)
    with open(os.path.join(args.out, "frames.bin"), "wb") as f:
        f.write(b"BAD2" + struct.pack("<HHB", count, first, FPS) + bytes(7))
        for n, m in enumerate(maps):
            f.write(m + frame_audio(audio, n))

    # Draw the layers back from the files: every frame must come out as encoded.
    tiles = np.frombuffer(open(os.path.join(args.out, "tiles.bin"), "rb").read(), np.uint8).reshape(2, 256, 8)
    layer_px = np.unpackbits(tiles, axis=2).reshape(2, 256, TILE, TILE).astype(bool)  # [layer][id][y][x]
    data = open(os.path.join(args.out, "frames.bin"), "rb").read()[16:]
    assert len(data) == count * RECORD_BYTES
    assert b"".join(data[n * RECORD_BYTES + FRAME_BYTES:(n + 1) * RECORD_BYTES]
                    for n in range(count)) == audio, "the sound differs"
    canvas = []
    for n in range(count):
        m = np.frombuffer(data, np.uint8, FRAME_BYTES, n * RECORD_BYTES).reshape(2, ROWS, COLS)
        cells = layer_px[0][m[0]] | layer_px[1][m[1]]                      # [row][col][y][x]
        img = cells.transpose(0, 2, 1, 3).reshape(ROWS * TILE, COLS * TILE)
        want = tile_pixels(shown[n]).reshape(ROWS, COLS, TILE, TILE).transpose(0, 2, 1, 3)
        assert np.array_equal(img, want.reshape(ROWS * TILE, COLS * TILE).astype(bool)), f"frame {n} differs"
        canvas.append(img)

    print(f"Encoded {count} frames from frame {first} ({first / FPS:.2f} s) in {encode_seconds:.1f} s; "
          f"{stand_in_cells} of {count * MAP_BYTES} cells use a stand-in tile; "
          f"{len(match.stand_ins)} distinct stand-ins")
    print(f"Wrote tiles.bin and frames.bin ({16 + count * RECORD_BYTES:,} bytes) to {args.out}")
    write_archive(args.archive, args.out, ["tiles.bin", "frames.bin"])
    print(f"Wrote {args.archive} ({os.path.getsize(args.archive):,} bytes)")
    if set_seconds is not None:
        total = 6573
        print(f"Estimate for all {total} frames: {set_seconds:.0f} s for the tile set, then "
              f"{encode_seconds / count * total:.0f} s to encode")

    if not args.no_preview:
        path = os.path.join(args.out, "preview.mp4")
        ff = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{COLS * TILE}x{ROWS * TILE}", "-r", str(FPS), "-i", "-",
             "-ss", f"{first / FPS:.3f}", "-t", f"{count / FPS:.3f}", "-i", args.video,
             "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-shortest", path], stdin=subprocess.PIPE)
        for img in canvas:
            ff.stdin.write((img * 255).astype(np.uint8).tobytes())
        ff.stdin.close()
        ff.wait()
        print(f"Wrote {path}")


if __name__ == "__main__":
    sys.exit(main())

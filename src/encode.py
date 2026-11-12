#!/usr/bin/env python3
"""Bad Apple!! encoder: hard edges over real gray, on three planes of tiles.

Each 512x384 frame is box-filtered to an 81x61 grid of corner samples. Each
of the 80x60 cells becomes 8x8 1bpp tiles on a 640x480 canvas, in three
mode 2 layers:

- Real gray. Source pixels between GRAY_LO and GRAY_HI are gray. An opening
  of OPENING source pixels (shrink, then grow back) drops the thin gray
  bands along edges, which are antialiasing, and keeps wide gray: motion
  blur, glows, shadows.
- Layer 0, plane 0: the real gray as a checkerboard, under a marching-squares
  outline snapped to GRAY_SNAP positions per tile edge. 256 tiles; tile 0
  is all black.
- Layers 1 and 2, planes 1 and 2: one hard white marching-squares outline at
  EDGE, snapped to EDGE_SNAP positions, clear inside the real gray. 511
  tiles from two layers of 256; tile 0 of both is clear.

Each layer set holds the tiles the whole video uses most. Spare slots on
layers 1 and 2 take the gray tiles that did not fit on layer 0: a
checkerboard tile looks the same there, over layer 0's black tile 0, in a
cell with no edge. A cell whose tile is not among them shows the nearest
one, counting pixels on the tile's
border BORDER_WEIGHT times, so outlines stay continuous across tiles.

Output, in ARCHIVE, which the build unpacks: tiles.bin and frames.bin,
  below. For the whole video it is src/badapple.tar.xz, the archive the
  build uses; for part of it, OUT/badapple.tar.xz. The archive has fixed
  times and owners, so the same video and settings give the same bytes.

Output, in OUT:
  tiles.bin    6144 bytes: 256 tiles for each of the three layers, 8 bytes
               each, one byte per row, leftmost pixel in the high bit.
  frames.bin   16-byte header ("BAD3", frame count, first source frame,
               fps), then an 18,508-byte record per frame, so the player
               reads a frame and its sound together: the three 80x60 maps,
               layers 0, 1, 2, one tile ID per byte, 14,400 bytes, then
               the frame's sound, 1027 samples, 4108 bytes. The sound is raw
               PCM, 30,810 Hz, 16-bit signed little-endian, stereo,
               resampled with soxr and dithered to 16 bits. The decoded
               AAC peaks at +2.05 dBFS, so it is 2.5 dB lower: nothing
               clips here, and the RIA's resampler has 0.45 dB more. Niconico's AAC encoder
               kept nothing above about 15.4 kHz, and a rate carries up to
               half of itself, so 30.8 kHz carries it all; 30,810 Hz is the
               next rate with a whole number of samples a frame.
  preview.mp4  the encoded frames as the two layers draw them, with the
               soundtrack of the same span.
  tileset.npz  the 511 tiles, cached for the next run with the same
               settings.
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
LAYERS = 3
FRAME_BYTES = LAYERS * MAP_BYTES
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


def mask_bits(mask):
    return np.uint64((mask.ravel().astype(np.uint64) * BIT).sum())


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


def opening(mask, r):
    """Square opening of a boolean mask: erode by r, then dilate by r."""
    if r == 0:
        return mask

    def run(m, axis, erode):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r + 1, r)
        c = np.cumsum(np.pad(m, pad, constant_values=erode).astype(np.int32), axis=axis)
        n = m.shape[axis]
        hi = np.take(c, np.arange(2 * r + 1, n + 2 * r + 1), axis=axis)
        lo = np.take(c, np.arange(0, n), axis=axis)
        return (hi - lo == 2 * r + 1) if erode else (hi - lo > 0)

    m = run(run(mask, 1, True), 0, True)
    return run(run(m, 1, False), 0, False)


class Tiler:
    """Turns a frame into edge keys and gray keys, caching each key's tile."""

    def __init__(self, gray_lo, gray_hi, opening, edge, edge_snap, gray_snap):
        self.gray_lo, self.gray_hi, self.opening = gray_lo, gray_hi, opening
        self.edge, self.edge_snap, self.gray_snap = edge, edge_snap, gray_snap
        self.edge_tiles, self.gray_tiles = {}, {}

    def keys(self, img):
        real = opening((img > self.gray_lo) & (img < self.gray_hi), self.opening)
        edge = line_keys(corners(np.where(real, 0.0, img)), self.edge, self.edge_snap)
        gray = line_keys(corners(real.astype(np.float64)), 0.5, self.gray_snap)
        return edge.ravel(), gray.ravel()

    def edge_tile(self, key):
        t = self.edge_tiles.get(key)
        if t is None:
            t = self.edge_tiles[key] = mask_bits(line_mask(key, self.edge_snap))
        return t

    def gray_tile(self, key):
        t = self.gray_tiles.get(key)
        if t is None:
            t = self.gray_tiles[key] = mask_bits(line_mask(key, self.gray_snap) & CHECKER)
        return t


def rank(counts, tile_of):
    """Every tile but the empty one, most used first, and its uses."""
    use = {}
    for key, c in counts.items():
        t = int(tile_of(key))
        use[t] = use.get(t, 0) + c
    return [t for t in sorted(use, key=lambda t: (-use[t], t)) if t != 0], use


def build_tilesets(video, tiler):
    """The edge and gray tiles of the whole video, each most used first."""
    edge_counts, gray_counts = {}, {}
    for img in read_frames(video):
        for keys, counts in zip(tiler.keys(img), (edge_counts, gray_counts)):
            k, n = np.unique(keys, return_counts=True)
            for key, c in zip(k.tolist(), n.tolist()):
                counts[key] = counts.get(key, 0) + c
    return rank(edge_counts, tiler.edge_tile), rank(gray_counts, tiler.gray_tile)


def coverage(kept, use):
    return sum(use.get(int(t), 0) for t in set(int(t) for t in kept)) / sum(use.values())


class Matcher:
    """Maps any tile to its index in the tile set."""

    def __init__(self, kept, border_weight):
        self.kept = kept
        self.index = {}
        for i, t in enumerate(kept):
            self.index.setdefault(int(t), i)
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
         "-vn", "-af", f"volume=-2.5dB,aresample={AUDIO_RATE}:resampler=soxr:precision=28:dither_method=triangular",
         "-ar", str(AUDIO_RATE), "-ac", "2", "-f", "s16le", "-"],
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
    ap.add_argument("--gray-lo", type=int, default=31, help="lowest real gray, of 255")
    ap.add_argument("--gray-hi", type=int, default=254, help="highest real gray, of 255")
    ap.add_argument("--opening", type=int, default=12, help="source pixels of gray band dropped as antialiasing")
    ap.add_argument("--edge", type=int, default=127, help="the hard edge's gray, of 255")
    ap.add_argument("--edge-snap", type=int, default=7, choices=range(1, 9), help="edge crossings per tile edge")
    ap.add_argument("--gray-snap", type=int, default=7, choices=range(1, 9), help="gray crossings per tile edge")
    ap.add_argument("--border-weight", type=int, default=4, help="weight of a border pixel when matching")
    ap.add_argument("--no-preview", action="store_true", help="skip preview.mp4")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.archive is None:
        whole = args.start == 0 and args.seconds is None
        args.archive = "src/badapple.tar.xz" if whole else os.path.join(args.out, "badapple.tar.xz")

    tiler = Tiler(args.gray_lo / 255, args.gray_hi / 255, args.opening, args.edge / 255,
                  args.edge_snap, args.gray_snap)
    cache = os.path.join(args.out, "tileset.npz")
    params = np.array([4, args.gray_lo, args.gray_hi, args.opening, args.edge, args.edge_snap, args.gray_snap])
    t0 = time.time()
    if os.path.exists(cache) and np.array_equal(np.load(cache)["params"], params):
        z = np.load(cache, allow_pickle=True)
        edge_ranked, gray_ranked = z["edge"].tolist(), z["gray"].tolist()
        edge_use, gray_use = z["edge_use"].item(), z["gray_use"].item()
        print(f"Tile sets from {cache}")
        set_seconds = None
    else:
        (edge_ranked, edge_use), (gray_ranked, gray_use) = build_tilesets(args.video, tiler)
        np.savez(cache, params=params, edge=np.array(edge_ranked, np.uint64), gray=np.array(gray_ranked, np.uint64),
                 edge_use=np.array(edge_use, object), gray_use=np.array(gray_use, object))
        set_seconds = time.time() - t0

    # Planes 1 and 2 hold the 510 edge tiles used most, after the empty tile
    # 0. Plane 0 holds the 255 gray tiles used most, after the black tile 0.
    # Spare slots on planes 1 and 2 take the next gray tiles: a checkerboard
    # tile looks the same there, over plane 0's tile 0, in a cell with no edge.
    kept_edge = [0] + edge_ranked[:SETS - 1]
    kept_gray = [0] + gray_ranked[:255]
    overflow = gray_ranked[255:255 + SETS - len(kept_edge)]
    first_overflow = len(kept_edge)
    slots = np.array(kept_edge + overflow + [0] * (SETS - len(kept_edge) - len(overflow)), np.uint64)
    kept_gray = np.array(kept_gray + [0] * (256 - len(kept_gray)), np.uint64)
    gray_all = np.concatenate([kept_gray, np.array(overflow, np.uint64)])
    print(f"Edge tiles: {len(edge_ranked) + 1} distinct; {len(kept_edge)} kept cover "
          f"{100 * coverage(kept_edge, edge_use):.2f}% of cells")
    print(f"Gray tiles: {len(gray_ranked) + 1} distinct; 256 on plane 0 and {len(overflow)} in spare edge slots "
          f"cover {100 * coverage(gray_all, gray_use):.2f}% of cells")
    match_edge = Matcher(np.array(kept_edge, np.uint64), args.border_weight)
    match_gray = Matcher(kept_gray, args.border_weight)
    match_gray_all = Matcher(gray_all, args.border_weight)

    with open(os.path.join(args.out, "tiles.bin"), "wb") as f:
        for tile in kept_gray:
            f.write(tile_rows(tile))
        for layer in range(2):
            for tid in range(256):
                index = tid if layer == 0 else (0 if tid == 0 else tid + 255)
                f.write(tile_rows(slots[index]))

    first = round(args.start * FPS)
    count = round(args.seconds * FPS) if args.seconds else None
    t1 = time.time()
    shown, maps = [], []
    stand_in_cells = 0
    for img in read_frames(args.video, first, count):
        edge_keys, gray_keys = tiler.keys(img)
        gray_map, edge1, edge2 = bytearray(MAP_BYTES), bytearray(MAP_BYTES), bytearray(MAP_BYTES)
        frame = np.empty(MAP_BYTES, np.uint64)
        for cell, (ek, gk) in enumerate(zip(edge_keys.tolist(), gray_keys.tolist())):
            et, gt = tiler.edge_tile(ek), tiler.gray_tile(gk)
            i = match_edge(et)
            if i == 0:
                g = match_gray_all(gt)
                if g >= 256:
                    i, g = first_overflow + g - 256, 0
            else:
                g = match_gray(gt)
            stand_in_cells += int(int(slots[i]) | int(kept_gray[g]) != int(et) | int(gt))
            frame[cell] = slots[i] | kept_gray[g]
            gray_map[cell] = g
            edge1[cell], edge2[cell] = layer_of(i)
        shown.append(frame)
        maps.append(bytes(gray_map) + bytes(edge1) + bytes(edge2))
    count = len(maps)
    encode_seconds = time.time() - t1

    audio = read_audio(args.video, first, count)
    with open(os.path.join(args.out, "frames.bin"), "wb") as f:
        f.write(b"BAD3" + struct.pack("<HHB", count, first, FPS) + bytes(7))
        for n, m in enumerate(maps):
            f.write(m + frame_audio(audio, n))

    # Draw the layers back from the files: every frame must come out as encoded.
    tiles = np.frombuffer(open(os.path.join(args.out, "tiles.bin"), "rb").read(), np.uint8).reshape(LAYERS, 256, 8)
    layer_px = np.unpackbits(tiles, axis=2).reshape(LAYERS, 256, TILE, TILE).astype(bool)  # [layer][id][y][x]
    data = open(os.path.join(args.out, "frames.bin"), "rb").read()[16:]
    assert len(data) == count * RECORD_BYTES
    assert b"".join(data[n * RECORD_BYTES + FRAME_BYTES:(n + 1) * RECORD_BYTES]
                    for n in range(count)) == audio, "the sound differs"
    canvas = []
    for n in range(count):
        m = np.frombuffer(data, np.uint8, FRAME_BYTES, n * RECORD_BYTES).reshape(LAYERS, ROWS, COLS)
        cells = layer_px[0][m[0]] | layer_px[1][m[1]] | layer_px[2][m[2]]                     # [row][col][y][x]
        img = cells.transpose(0, 2, 1, 3).reshape(ROWS * TILE, COLS * TILE)
        want = tile_pixels(shown[n]).reshape(ROWS, COLS, TILE, TILE).transpose(0, 2, 1, 3)
        assert np.array_equal(img, want.reshape(ROWS * TILE, COLS * TILE).astype(bool)), f"frame {n} differs"
        canvas.append(img)

    print(f"Encoded {count} frames from frame {first} ({first / FPS:.2f} s) in {encode_seconds:.1f} s; "
          f"{stand_in_cells} of {count * MAP_BYTES} cells use a stand-in tile; "
          f"{len(match_edge.stand_ins) + len(match_gray.stand_ins) + len(match_gray_all.stand_ins)} distinct stand-ins")
    print(f"Wrote tiles.bin and frames.bin ({16 + count * RECORD_BYTES:,} bytes) to {args.out}")
    write_archive(args.archive, args.out, ["tiles.bin", "frames.bin"])
    print(f"Wrote {args.archive} ({os.path.getsize(args.archive):,} bytes)")
    if set_seconds is not None:
        total = 6573
        print(f"Estimate for all {total} frames: {set_seconds:.0f} s for the tile sets, then "
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

# Bad Apple!! on the Picocomputer 6502 — Marching Cubes Video Compression

Status: **draft for review**. This plan is meant to be complete enough to
execute in one pass once the open questions at the end are answered.

## 1. Goal

Play the Bad Apple!! shadow-art video on the RP6502 at full frame rate,
from a single ROM, using a codec built on marching cubes:

- Treat the black-and-white video as a 3D volume `V(x, y, t)`.
- Extract the boundary between black and white as an isosurface with
  marching cubes, a closed triangle mesh in space-time.
- Simplify and quantize the mesh. Large, slowly changing areas become a few
  big triangles that span many frames.
- On the 6502, slice the mesh at each frame time to get polygon contours,
  and fill them into a 1-bit bitmap.

Because the codec stores shapes rather than pixels, the same stream can
render at any resolution. The first target is 320x240. 512x384 is a stretch
goal.

### Success criteria (v1)

1. `badapple.rp6502` plays the whole video at 30 fps on the emulator at
   8 MHz with no late frames, or with a late-frame count that we measure
   and accept.
2. The 6502 decoder's output matches the Python reference decoder **bit for
   bit** on every frame. A ctest checks this.
3. Fidelity and size are measured against the thresholded source and
   reported: bytes total, bytes per frame, and per-frame pixel error / IoU.
4. A web player builds through `rp6502_web()` and the existing GitHub Pages
   workflow.

## 2. Machine facts that shape the design

From `~/picocomputer.github.io/docs/source` (vga, ria, api, sdk, emu, web,
port).

| Fact | Value | Source |
|---|---|---|
| CPU clock | 8 MHz at start, settable 100 kHz–8 MHz | ria.rst PHI2 |
| VSYNC | 60 Hz; `RIA_VSYNC` ($FFE3) increments each frame; optional IRQ | ria.rst, api.rst IRQ |
| Cycles per 30 fps video frame | 8,000,000 / 30 = **266,666** | derived |
| Vertical blanking, 320x240 / 640x480 canvas | 1.37 ms, ~10,900 cycles | vga.rst Video Timing |
| Bitmap mode | Mode 3, 1/2/4/8/16 bpp, MSB = leftmost pixel (bit 3 reverses) | vga.rst Mode 3 |
| Mode 3 config | `mode3_config_t`, 14 bytes, even address; `xram_data_ptr` at offset 10 | vga.rst |
| 1bpp built-in palette | `xram_palette_ptr = $FFFF` is black and white | vga.rst palettes |
| XRAM | 64 KB, reached through portals RW0/RW1 with ADDR and signed STEP | ria.rst XRAM Portals |
| XRAM write cost | `sta RIA_RW0` with STEP0=1: 4 cycles a byte, no wait states documented | ria.rst |
| XRAM change visibility | Shows on the next scanline drawn, so changes mid-frame can tear | vga.rst VSYNC |
| File to XRAM | `read_xram()` up to $7FFF a call, ~800 KB/s on PICO, can run in the background (poll `RIA_BUSY`) | api.rst XRAM Transfers |
| File to RAM | `read()` up to $7FFF, through XSTACK in 512-byte calls | api.rst |
| Data in a ROM | Named asset via `rp6502_asset(target name file)`, opened as `ROM:name` | sdk.rst Adding Assets |
| Generated assets | `add_custom_command()` output passed to `rp6502_asset()` | sdk.rst |
| RAM | $0000–$FEFF free, zero page included; VIA at $FFD0 | sdk.rst Memory Map |
| Sound | PSG (8 ch) or OPL2 (9 ch), one at a time; no sample playback is documented | ria.rst |
| Emulator scripting | `run N` (exact frames), `dump xram:a n`, `peek`, `wait`, `shot`, `crc`, `expect exit` | emu.rst Scripting |
| Emulator headless | `--headless --phi2 0` runs at full host speed; exit code passes through | emu.rst |
| Tests | `rp6502_test(NAME n COMMAND tests/x.py $<TARGET_PROPERTY:t,RP6502_ROM>)`; Python `rp6502.Emu` | sdk.rst Testing |
| Uninitialized memory | Emulator fills RAM/XRAM randomly; `--memfill 0` / `--memseed` for repeat runs | emu.rst |

### Frame buffers

| Canvas / bitmap | Bytes per buffer | Two buffers | Fits in XRAM? |
|---|---|---|---|
| 320x240 1bpp (40 B/row) | 9,600 | 19,200 | yes, **v1 target** |
| 512x384 1bpp inside a 640x480 canvas (64 B/row) | 24,576 | 49,152 | yes, stretch |
| 640x480 1bpp | 38,400 | 76,800 | single buffer only |

Double buffering: the decoder draws into the back buffer, then right after
VSYNC it writes the back buffer's address into `xram_data_ptr` (one 16-bit
poke, well inside the 10,900-cycle blanking window). At 30 fps each video
frame is shown for two VSYNCs.

## 3. Codec design

### 3.1 From video to mesh

1. Decode the source to 8-bit grayscale at the working resolution
   (320x240 at first) with ffmpeg. Keep gray, not just black and white, so
   marching cubes places vertices with sub-pixel precision.
2. Pad the volume by one voxel of black on every side, in x, y, and t, so
   the isosurface is closed: every contour is a closed loop, including
   white areas that touch the frame border, and the first and last frames.
3. Run marching cubes at iso level 0.5 over `(x, y, t)` with a consistent
   triangulation that gives a watertight, manifold mesh. Lewiner's MC33 or a
   marching-tetrahedra split avoids holes from ambiguous cases. Process in
   time chunks (for example 64 frames with shared boundary planes) to bound
   memory.
4. Simplify with quadric-error edge collapse. Scale the t axis by a
   tunable `s` (pixels of error that one frame of timing error costs), so
   the error metric trades shape error against timing error.
5. Quantize the vertices: t to **integer frames**, and x, y to the
   decoder's fixed point (3.3).

Before simplification, slicing the raw mesh at frame `t = k` gives exactly
the marching-squares contours of frame k. This is the first correctness
check of the encoder (M2). All of the compression comes from simplifying.

### 3.2 Slicing rule (the robustness trick)

Frame k is drawn from the slice at `t = k + ε`. A vertex with `t ≤ k`
counts as below the plane. The plane then never passes through a vertex,
and a slice of a closed manifold mesh is always a set of closed loops.

- A mesh edge (a, b) with `t_a < t_b` is **active** for the frames
  `t_a ≤ f < t_b`. Its slice point is
  `p(f) = a + (b − a)(f − t_a)/(t_b − t_a)`, so at `f = t_a` the point is
  exactly at vertex a.
- A triangle with sorted times `t0 ≤ t1 ≤ t2` is active for `t0 ≤ f < t2`
  and contributes one segment: between edges (0,1) and (0,2) while
  `f < t1`, then between edges (1,2) and (0,2). If `t0 = t1` it has only the
  second phase.
- Edges and triangles with no extent in t are never active. They need no
  special case.

### 3.3 What the decoder sees: kinetic points and segments

The decoder knows nothing about triangles. Its state is:

- **Points**: slots holding `x, y, vx, vy`. Each is one active mesh edge,
  moving at a constant velocity. Every frame, `x += vx; y += vy`.
- **Segments**: slots holding a pair of point slots. Each is one active
  triangle phase.

All topology changes happen at frame boundaries (the vertex times). The
stream for frame f lists, in order:

1. point slots that die (edges with `t_b = f`)
2. segment slots that die
3. new points: position and velocity (edges with `t_a = f`)
4. new segments: two point slots each

Both encoder and decoder allocate slots from the same deterministic free
list (LIFO), so new items carry no slot id.

The velocity is `(b − a)/(t_b − t_a)` computed by the encoder and rounded
to fixed point. The 6502 never divides for motion. Rounding drift shows up
as a small shape error, never as an opening in a contour, because segments
share point slots: closure depends on the topology, not on the geometry.

**Fixed point (initial choice, tunable):** positions and velocities are
signed 16-bit with 6 fractional bits (10.6), so the range is ±512 px at
1/64 px. The drift over a 30-frame edge is at most about 0.25 px. The
encoder simulates the decoder's integer math exactly, so it knows the
decoded positions and can choose each velocity to minimize the error at
the end of the edge.

### 3.4 Rasterization (must match bit for bit)

Even-odd fill over the segment soup. Loop orientation does not matter.

- Pixel (px, py) has its center at (px + 0.5, py + 0.5).
- A segment covers scanline py when `y_top ≤ py + 0.5 < y_bottom`
  (half-open), so a vertex shared by two segments counts once.
- Its crossing on that scanline is x at `py + 0.5`, stepped per scanline by
  a slope from a reciprocal table: `slope = (dx * RECIP[dy]) >> k`. The
  rounding is defined in the reference decoder.
- After sorting the crossings of a scanline, the spans between crossings
  0–1, 2–3, … are white. A span covers the pixels whose centers lie in
  `[x_even, x_odd)`.

**The Python reference decoder is the specification.** Any change to the
arithmetic is made in both decoders, and the checksum test (M4) enforces
that they agree.

### 3.5 Bitstream (v1 draft)

```
header:  magic "BAMC", version, frame_count, width, height,
         fixed-point format, caps (max points, max segments,
         max crossings per scanline)
frame f: kill_pts  : count, then slot ids
         kill_segs : count, then slot ids
         new_pts   : count, then (x, y, vx, vy) each
         new_segs  : count, then (slot a, slot b) each
end:     frame_count records, then a CRC-32 of the stream
```

v1 uses byte-aligned variable-length integers. A new point's position is
coded as a delta from the previous new point of the same frame, because
the edges that start at one vertex all start at its position. v2 can add
entropy coding (for example rANS or adaptive binary arithmetic coding) if
the measurements show it pays off. The data rate is low, so decode speed
is not the issue.

The encoder enforces the decoder's caps, so a frame never needs more
points, segments, or crossings than the 6502 tables hold. Where a frame
would exceed a cap or the cycle budget, it simplifies that part of the
mesh further.

## 4. The 6502 player

### 4.1 Layout

**XRAM**

| Addr | Size | Use |
|---|---|---|
| $0000 | 9,600 | frame buffer 0 (320x240 1bpp) |
| $2580 | 9,600 | frame buffer 1 |
| $4B00 | 14 | `mode3_config_t` |
| $4B10 | up to ~46 KB | free: stream ring buffer when M5 moves to `read_xram`, span history for delta rendering |

All `XRAM_` symbols live in `src/xram.h` as `xram_layout_t`, and
`rp6502_align(badapple "XRAM_.*")` checks them.

**RAM** (rough): point tables as structure-of-arrays (`x_lo, x_hi, y_lo,
y_hi, vx_lo, …` indexed by X/Y) for up to 512 points, segment tables for
up to 512 segments, the active edge table, a reciprocal table, a 1–2 KB
stream buffer, and code.

### 4.2 Per-frame loop

```
for each video frame f:
    apply events of f (kill / add points and segments)
    advance every point by its velocity
    if behind schedule: count a late frame, skip drawing (state stays exact)
    else:
        build the edge list (segments → top, bottom, x at top, slope)
        scanline loop over the active edge table: step x, sort, emit spans
        write each row of the back buffer through RW0
        wait for VSYNC f*2 (the frame's due time), poke xram_data_ptr
```

Skipping a draw never desynchronizes the decoder, because events and
motion are applied for every frame.

Stream input in v1: `open("ROM:video")` and `read()` into a RAM ring
buffer, refilled when it falls below half. At ~800 KB/s a 1 KB refill
costs about 10,000 cycles, a few percent of one frame. M5 can switch to
`read_xram()` in the background, with the decoder reading the stream
through portal 1 (`lda RIA_RW1`, 4 cycles a byte), which needs no copy.

### 4.3 Cycle budget at 320x240, 30 fps

These are estimates to validate in M1/M4. N is the number of active
segments, C the number of scanline crossings in the frame.

| Step | Estimate |
|---|---|
| Advance points (~60 cycles each, N≈256) | ~15K |
| Segment setup (multiply by reciprocal, ~250 each) | ~64K |
| Crossings (step + insert ~45 each, C≈2,000) | ~90K |
| Write rows (40 bytes/row, unrolled `sta`, 240 rows) | ~60K |
| Events, stream read | ~10–20K |
| **Total** | **~240K of 266K** |

This is tight, so:

- Hot loops (advance, crossing step, span write) are 6502 assembly from
  the start. The rest is C.
- The encoder carries a cost model of the decoder and holds each frame
  under the budget, simplifying harder in frames that would go over.
- The first optimization if needed (M5) is **delta rendering**: compare
  each row's spans with the spans of the same buffer two frames ago, and
  write only the bytes that changed.
- A VIA timer measures cycles per step on the 6502, so the cost model can
  be calibrated from measurements.

### 4.4 Compiler

llvm-mos, for the better C code, with hot loops in llvm-mc assembly. The
cc65 presets stay in the template but are not maintained for this program
unless you want them.

## 5. Encoder and tools (Python, offline)

```
encoder/
  requirements.txt      numpy, Pillow, plus the mesh libraries chosen in Q4
  extract.py            ffmpeg → grayscale frames (.npy chunks) + ffprobe facts
  mc.py                 marching cubes over (x, y, t) chunks
  simplify.py           anisotropic QEM, t-quantization, cap enforcement
  events.py             mesh → per-frame events (slicing rule 3.2)
  bitstream.py          pack / unpack (3.5)
  refdec.py             reference decoder: stream → frames, integer-exact
  metrics.py            IoU / pixel error vs source, size, cost-model report
  encode.py             CLI: source video → assets/badapple.bamc + report
  tests/                unittest: MC raw-slice identity, pack/unpack round trip,
                        slicing robustness, refdec determinism
```

- `data/` holds the source video and intermediates. It is gitignored.
- `assets/badapple.bamc` is the encoded stream, committed (see Q5), so the
  ROM and the web player build without the source video or a long encode.
- `encode.py` writes a report (markdown + a few PNG comparison frames) with
  the size, error, and decoder-cost numbers for each run.

## 6. Repository layout after v1

```
CMakeLists.txt        badapple target (llvm-mos), asset ROM:video, rp6502_web, tests
src/main.c            setup, frame loop, pacing
src/stream.c/.h       ring buffer + event parsing
src/raster.s          advance, edge setup, scanline fill (llvm-mc)
src/xram.h            VGA mode 3 code blocks + xram_layout_t
tests/frames.py       bit-exact checksum test vs refdec (test-mode ROM, --phi2 0)
tests/realtime.py     real-time run at 8 MHz, asserts the late-frame count
tests/smoke.txt       emulator script: boots, draws, shot, exits 0
encoder/              as section 5
assets/badapple.bamc
plan.md, README.md
```

Two ROM targets share the sources:

- `badapple`: the player, paced by VSYNC.
- `badapple_test`: the same decoder, unpaced, which prints a 16-bit
  checksum of every frame to stdout. `refdec.py` computes the same
  checksum. Under `--headless --phi2 0` this covers every frame in one
  ctest.

## 7. Milestones

Each milestone ends with a commit and push to `main`. Its acceptance check
must pass first.

**M0 — Source and baselines**
- Set up the encoder venv and requirements. Run `extract.py` on the source
  file (Q1) and record ffprobe facts (resolution, fps, frame count,
  duration) in the report.
- Baselines for comparison: raw 1bpp size, plain RLE size, and per-frame
  XOR+RLE size at 320x240.
- Check the size limit: build a throwaway ROM with a dummy asset of the
  expected size (1–4 MB). Confirm the emulator and the web player open and
  read it. The docs give no limit for named assets.
- *Accept:* frame count and fps are recorded, baselines are in the report,
  and the large-asset check passes or the limit is known.

**M1 — Player skeleton**
- Mode 3 1bpp 320x240, two buffers, page flip on VSYNC.
- A hand-made stream (a moving square and a ring) runs through the real
  event format and rasterizer in C.
- VIA-timer cycle instrumentation.
- *Accept:* `tests/smoke.txt` boots, runs 120 frames, writes a `shot`, and
  exits 0. Cycle numbers per step are printed.

**M2 — Marching cubes, unsimplified**
- `mc.py` on a 300-frame clip, `events.py`, `refdec.py`.
- *Accept:* the reference-decoded frames of the raw mesh match the
  thresholded source to within the rounding of the rasterizer (pixel
  error < 0.1%), and every slice is closed loops (checked by the test).

**M3 — Simplification and rate–distortion**
- QEM with t scale `s`, quantization, caps, cost model, bitstream v1.
- Sweep `s` and the error tolerance over the whole video, then pick an
  operating point with you (Q6).
- *Accept:* the report shows the size against error curve. The chosen
  stream stays within the caps and the cycle budget on every frame.

**M4 — 6502 decoder, bit-exact**
- Port the event handling and rasterizer to the 6502, with the hot loops
  in assembly.
- *Accept:* `tests/frames.py` passes: every frame's checksum equals
  `refdec.py`.

**M5 — Real time**
- Optimize until `tests/realtime.py` (13,144 VSYNCs at 8 MHz) reports zero
  late frames, or the count we accept. Options in order: tighter asm,
  encoder budget control, delta rendering, `read_xram` streaming.
- *Accept:* real-time test passes. The cost model is calibrated against
  measured cycles.

**M6 — Ship**
- `rp6502_web(badapple)`. The README gets a description, the numbers, and
  how to re-encode. The Pages workflow publishes.
- *Accept:* the web build plays in a browser, and ctest is green.

**Stretch** (after v1, in any order): 512x384 in a 640x480 canvas from the
same stream; entropy-coded bitstream v2; 2bpp edge anti-aliasing; a
soundtrack on OPL2 or PSG (Q2).

## 8. Risks

| Risk | Mitigation |
|---|---|
| Rendering misses 30 fps at 320x240 | Encoder cost model + budget control, delta rendering, frame skipping that keeps the state exact. Fall back to 15 fps if needed. |
| Simplified mesh self-intersects; even-odd fill makes holes | Measured by the per-frame error from refdec. Reject collapses that cause intersections in their neighborhood. |
| Marching cubes on ~6,500 frames is slow or memory-heavy in Python | Chunk in time; vectorized numpy; C library for QEM (Q4). |
| QEM libraries have no constraint for t-quantization | Quantize after collapse, then validate. Write our own collapse loop if the error is too high. |
| Named-asset or web-player size limit | Checked in M0 before any codec work depends on it. |
| `read_xram` in the background while the portals are in use | v1 uses `read()`; test this before M5 relies on it. |
| Decoder and refdec drift apart | Single integer spec in refdec; the every-frame checksum test runs in ctest. |
| WSL runs the Windows emulator through interop | The tools already handle it (both presets build). Keep tests path-agnostic. |

## 9. Open questions for you

1. **Source video.** Where is the file? I'll put it under `data/`
   (gitignored) and not download anything on my own.
2. **Audio.** Video only for v1? The docs show no sample playback, so a
   soundtrack means a PSG or OPL2 arrangement. Is that a later milestone
   or out of scope?
3. **Target.** 320x240 at 30 fps, 1bpp, as the v1 bar?
4. **Python dependencies.** Is it OK to install packages into a project
   venv? My suggestion: our own marching cubes in numpy (it is the subject
   of the project and small), plus `pyfqmr` or similar for QEM at first,
   replaced by our own if the constraints need it. The alternative is all
   our own code: slower to build, no outside dependencies.
5. **Committing the encoded stream** (`assets/badapple.bamc`, probably
   0.5–2 MB) so CI and the web player build without the source. OK?
6. **Size and quality.** Do you have a target, such as under 1 MB, or a
   comparison point? Otherwise I'll present the rate–distortion curve in
   M3 and we choose together.
7. **cc65.** Drop the cc65 and BASIC presets and the template's hello
   files, or keep them?
8. Your first message ended at "After that," — what came next?

# Bad Apple!! on the Picocomputer 6502

A port of the Bad Apple!! shadow-art video and its music to the RP6502.

## Step 1: Provenance

Research results, from web sources only. **UNVERIFIED** marks a fact from
secondary sources that we confirm once we have the files.

### Lineage and credits

There is no original retro-computer program. The ports all start from a
2009 web video, which animates a 2007 song arrangement, which arranges a
1998 game track.

| Year | Work | Credit |
|---|---|---|
| 1998-08-14 | "Bad Apple!!", the Stage 3 theme of *Touhou Gensokyo ~ Lotus Land Story* (Touhou 4), NEC PC-98 | ZUN (composer; the Touhou games were by ZUN Soft at the time) |
| 2006 | Track included in *Akyu's Untouched Score vol.1* | ZUN |
| 2007-05-20 | "Bad Apple!! feat. nomico" on the album *Lovelight* (ARCD0018), released at the 4th Hakurei Shrine Reitaisai | Alstroemeria Records: Masayoshi Minoshima (arrangement), nomico (vocals), Haruka (lyrics) |
| 2008-06-08 | Storyboard of a shadow-art PV posted to Niconico as `nm3601701`, asking someone to animate it | Μμ |
| 2009-10-27 03:13 JST (10-26 UTC) | The finished shadow-art PV, Niconico [`sm8628149`](https://www.nicovideo.jp/watch/sm8628149). Its description says it is based on `nm3601701`. | Anira (あにら), Niconico user 10731211 |

Sources: [Wikipedia: Bad Apple!!](https://en.wikipedia.org/wiki/Bad_Apple!!),
[Bilibili article on the PV's history](https://www.bilibili.com/read/cv3839234/),
[Niconico dictionary](https://dic.nicovideo.jp/a/bad%20apple%21%21%20feat.%20nomico).

Fan use: ZUN's guidelines allow derivative works without prior permission
if they follow the guidelines: attribution, no unauthorized commercial
distribution, and no crowdfunding (Wikipedia, citing the guidelines). We
need to read ZUN's guidelines ourselves, and check Alstroemeria Records'
position on fan use of the arrangement and the PV.

### The video

**The source:** Anira's original upload,
[`sm8628149`](https://www.nicovideo.jp/watch/sm8628149) on Niconico. It
is still online.

The text that scrolls over the video on Niconico is viewer comments. The
player draws them over the video, and its comment button hides them. They
are not part of the video file.

yt-dlp downloads it without an account. Into `data/`, which Git ignores:

```text
yt-dlp -f "video-h264-360p-1+audio-aac-128kbps" -k --write-info-json \
    -o "data/sm8628149.%(ext)s" https://www.nicovideo.jp/watch/sm8628149
```

Niconico offers 512x384 and 480x360 video. The 512x384 stream is its best.

Measured with `ffprobe` on the download:

| Property | Value |
|---|---|
| Resolution | 512x384 (4:3) |
| Frame rate | 30/1 fps, constant |
| Frame count | 6573 |
| Duration | 219.1 s (video), 219.13 s (audio) |
| Video codec | H.264 Main, yuv420p |
| Audio | AAC, 44.1 kHz stereo, 128 kbps |
| Color | Black-and-white shadow art. A frame at 60 s is 80% black, 16% white, and 4% gray, from soft edges and blur. |

The files are Niconico's current encode. The file Anira uploaded in 2009
is not offered, so these are the closest copy available.

### The audio: solved

The RP6502 is getting PCM audio, so the port plays the PV's own
soundtrack, the Alstroemeria Records recording, from the AAC track in
`data/`. The emulator and documentation for PCM audio come later.

The soundtrack is real stereo, not mono in two channels. Over the whole
track, left and right correlate at 0.91, and the difference (L-R) sits
13 dB below the sum (L+R), up to 3 dB below it in the widest second. The
two channels are balanced within 0.14 dB. A mono mix keeps every part,
and loses only the stereo width.

What the download holds: AAC-LC at 44.1 kHz, about 113 kbps. Its encoder
cut everything above about 15.4 kHz: the average spectrum falls from
-49 dB at 15 kHz to -75 dB at 15.5 kHz, then stays at the noise floor to
22 kHz. So a 32 kHz sample rate (16 kHz bandwidth) carries nearly all of
it. The file cannot show whether the master was 44.1 or 48 kHz, because
the cutoff erased any trace. The arrangement came out on a CD, *Lovelight*,
and CD audio is 44.1 kHz, 16-bit.

The master is loud: overall RMS -8.4 dBFS, half-second RMS between -8.3
(median) and -6.6 dBFS (loudest), peaks at 0 dBFS with 0.14% of samples
clipped. 16 bits is plenty. A resampler should lower the gain about 1 dB
so its filter does not clip.

Stereo, 16-bit, for 219.13 s:

| Sample rate | Bandwidth | Bytes per second | Whole song |
|---|---|---|---|
| 44.1 kHz | 22.05 kHz | 176,400 | 38.7 MB |
| 32 kHz | 16 kHz | 128,000 | 28.0 MB |
| 24 kHz | 12 kHz | 96,000 | 21.0 MB |
| 22.05 kHz | 11.03 kHz | 88,200 | 19.3 MB |

**Decision:** 32 kHz, stereo, 16-bit raw PCM, 128,000 bytes per second.

An FM version is no longer needed. The search for one found no OPL2 or
AdLib cover. The DOS ports play digitized sound, and the two FM covers
(MSX by MDPC with music by aro, and Mega Drive by Mt.Chocolate) need FM
and a PSG at once, which the RP6502 cannot do.

### Notable ports, for context

| Port | Year | Notes |
|---|---|---|
| IBM PC/XT, 8088 Domination (Trixter) | 2014 | 640x200 at 30 fps, CGA plus a Sound Blaster ([blog](https://trixter.oldskool.org/2014/06/17/8088-domination)) |
| Commodore 64 | 2014 | 12 fps |
| NES | — | 64x60 at 15 fps, blocky tile video with I, P, and D frames ([nesdev](https://www.nesdev.org/wiki/Bad_Apple)) |
| Vectrex, Atari 2600, Genesis, TI-84 Plus | by 2015 | (Wikipedia) |
| Apple IIe | 2021 | unmodified hardware |
| ESP8266 (cnlohr) | — | all 6570 frames at 64x48; MIDI audio ([espbadapple](https://github.com/cnlohr/espbadapple)) |

### Still to do in step 1

- [x] Get the original video and record its exact resolution, frame rate,
      frame count, and duration with `ffprobe`.
- [ ] Read ZUN's derivative-work guidelines. Look for Alstroemeria
      Records' terms on fan use.
- [x] Decide on the audio source: the original soundtrack, as PCM.

## Step 2: 1-bit video

### Research: the soft edges

- No write-up was found about recovering the motion blur, and no cleaner
  source than Niconico's. The ports simply threshold, often at 127 of 255
  (for example the [RACECAR Neo guide](https://mitracecarneo.github.io/racecar-neo-library/guides/bad-apple.html)),
  or dither.
- The gray is in the artwork. Measured over all 6573 frames of the
  512x384 download, counting pixels from 48 to 207 as gray:

  | | Gray pixels |
  |---|---|
  | Median frame | 1.07% |
  | Mean | 2.03% |
  | 90th percentile | 4.69% |
  | 99th percentile | 15.78% |
  | Worst frame | 33.56% (frame 3308, 110.3 s) |

  618 frames are over 5% gray, 164 over 10%, and 33 over 20%. The worst
  frames (3305-3313 at 110 s, and 2831 at 94.4 s) are glows, gradients,
  and motion blur that the animation draws, not compression damage. The
  gray share correlates only weakly with motion (0.37). So no unblurred
  version is likely to exist.

### Proposed approach

- Scale each frame to an 81x61 grid of samples.
- Treat the samples as the corners of 80x60 cells, and pick each cell's
  tile from its four corners, marching-squares style.
- Show the tiles with mode 2: 1bpp 8x8 tiles fill a 640x480 canvas as
  80x60 tiles. Up to 256 tiles at 8 bytes each is 2 KB. Each 80x60 map is
  4,800 bytes, so two pages for double buffering are 9,600 bytes.
- The video stream is not stored as height maps. The decoder
  double-buffers the two 80x60 tile maps.

### Decision: black and white

Previews of frames 357 (the arm swing) and 2831 (two girls in a glow)
compared black and white tiles with four-gray tiles. Four grays put some
of the blur back, but they draw a gray outline around every hard edge and
need 406-463 tiles in a single frame, over the 256 that mode 2 holds. The
port is **1bpp black and white**, tuned by adjusting the threshold.

### Dithered levels, tested

The four-level previews were redrawn as 1-bit: black, white, and the two
middle levels filled with a fixed 8x8 pattern (ordered Bayer, clustered
halftone, blue noise, or horizontal lines). The pattern turns the gray
outline into a soft fringe and brings back the smear and the glow. Blue
noise looks smoothest.

Distinct 8x8 tiles over all 6573 frames, one fixed tile set. k is the
number of crossing positions per tile edge for each iso-line; the 0.5
line is the one in the middle of the list:

| Config | Bayer | Halftone | Blue noise | Lines |
|---|---|---|---|---|
| B/W, k 4 | 190 | 190 | 190 | 190 |
| 4 levels, k 4/4/4 | 2968 | 2709 | 3112 | 2973 |
| 4 levels, k 2/4/2 | 1495 | 1098 | 1365 | 1395 |
| 4 levels, k 1/4/1 | 1007 | 859 | 913 | 779 |
| 4 levels, k 2/2/2 | 719 | 555 | 687 | 676 |
| 4 levels, k 1/2/1 | 489 | 451 | 471 | 397 |
| 5 levels, k 2/2/2/2 | 1428 | 1071 | 1450 | 1193 |
| 5 levels, k 1/2/2/1 | 1258 | 1026 | 1252 | 887 |
| 5 levels, k 1/1/1/1 | 716 | 558 | 716 | 546 |

Only black and white fits mode 2's 256 tiles with one tile set.

### At most two levels per tile

In the plain four-level render, a hard black-to-white edge crosses all
three lines inside one tile, which leaves a thin band of halftone around
every character. The rule: a tile holds at most two levels. A cell whose
corners span one level splits on the line between them. A cell whose
corners span two or more levels splits on the middle line only, with its
lowest level on one side and its highest on the other, so a hard edge
draws as clean black and white. The smear and the glow keep their bands.

Before the rule, the three test frames have 47-132 tiles holding all four
levels and 90-168 holding three. Tiles over the whole video, halftone
screen at 45 degrees:

| Snapping | Tiles in the video |
|---|---|
| All lines 4 | 666 |
| Dark and light lines 2, middle 4 | 540 |
| Dark and light lines 1, middle 4 | 502 |
| Dark and light lines 1; middle 4 for black and white, 2 for halftone tiles | 268 |
| Dark and light lines 1; middle 4 for black and white, 1 for halftone tiles | **215** |

The last row fits mode 2's 256 tiles with one tile set. Black-and-white
edges keep full precision, and the edges of the halftone bands snap to
the tile-edge midpoints, which the dots hide. A few stray dots remain
along some character edges, where a corner sample lands in a band.

### Three levels

Black, white, and one 50% fill, at most two levels per tile. The fill is
a checkerboard, every other pixel, not a halftone dot screen. A
corner is black under the dark threshold (0.25), white over the light
one (0.75), and halftone between. A cell with black and halftone corners
splits on the dark line, halftone and white on the light line, and black
and white on the middle line (0.5), so a hard edge stays clean. The
single band is meant to suggest the motion blur and the glow, not to
reproduce their detail.

| Snapping, dark/middle/light | Tiles in the video |
|---|---|
| 1/4/1, 45-degree halftone | 167 |
| 2/4/2, 45-degree halftone | 221 |
| 4/4/4, 45-degree halftone | 409 |
| **2/4/2, checkerboard** | **235** |

With the checkerboard at 2/4/2, the three test frames use 116, 156, and
117 tiles.

### Chosen look, and its tile budget

Picked in the tuner on frame 2831: three levels stacked (black, a 50%
checkerboard fill, white), dark threshold 128 and light threshold 192 of
255, both lines snapped to 4 positions per tile edge. The edges of the
fill matter more than its interior. All three levels must be supported.

| Snapping, dark/light | Tiles in the video | Per frame, median | Per frame, max | Frames over 256 |
|---|---|---|---|---|
| **4/4 (chosen)** | **1446** | 151 | 386 (frame 1889, 63.0 s) | 405 |
| 4/2 | 753 | 128 | 320 | 30 |
| 2/4 | 733 | 121 | 286 | 10 |
| 2/2 | 361 | 96 | 220 | 0 |

The chosen look does not fit one fixed set of 256 tiles. Most frames fit
256 on their own.

### 511 tiles from two layers

Two mode 2 layers, each with its own 256 tiles. Each layer has one
all-black tile: black is transparent on the top layer, so a cell shows
either a top tile over the bottom layer's black, or the bottom layer's
tile through the top layer's black. That makes 511 visible tiles. The
tile sets stay fixed for the whole video; each frame streams both 80x60
maps, 9,600 bytes, or 288,000 bytes a second at 30 fps.

The set keeps the 511 tiles the video uses most. A cell whose ideal tile
is not in the set shows the set's nearest tile, the one with the fewest
different pixels. Dark threshold 128, light 192:

| Snap | Distinct tiles | Cells exact | Wrong pixels per frame against a 1/4-pixel reference, mean | Worst frame |
|---|---|---|---|---|
| 2/2 | 361 | 100% | 1118 | 3349 |
| 3/3 | 862 | 99.93% | not measured | not measured |
| 4/4 | 1446 | 99.72% | 593 | 1837 |
| 5/5 | 2604 | 99.27% | 529 | 1637 |
| 6/6 | 3467 | 98.98% | 486 | 1762 |
| 8/8 | 5509 | 98.55% | 466 | 1699 |

Snap 3/3 needs 862 tiles to be exact. The most used 173 tiles cover 99%
of cells, 467 cover 99.9%, the set's 511 cover 99.93%, 719 cover 99.99%,
and 823 cover 99.999%. A frame uses 125 distinct tiles at the median and
316 at most (frame 1887). With the 511-tile set, a frame is off from its
own exact tiles by 5.2 pixels on average and 68 at worst (frame 1894).

Finer snapping still wins with the limit. At 8/8 a crossing can land on
any pixel; 1.45% of cells show a stand-in tile, and the result is off by
466 of 307,200 pixels a frame on average. Only 2/2 fits 511 tiles
exactly. A selection that weighs each tile's stand-in error, rather than
counting uses alone, could do better.

### How other ports drew the same frames

Frames 357, 2831, and 3308 (the hand reaching into light), matched in
YouTube captures:

| Port | Capture | How it shows the soft edges |
|---|---|---|
| IBM PC 5160, 8088 Domination (Trixter, 2014) | [MWdG413nNkI](https://www.youtube.com/watch?v=MWdG413nNkI) | Dithered, with horizontal line patterns for the glow and the blur |
| Atari STE, fenarinarsa (2017) | [aIeAIgGnx0M](https://www.youtube.com/watch?v=aIeAIgGnx0M) | Dithered gray; closest to the source |
| Mega Drive, Stef (2012) | [2vPe452cegU](https://www.youtube.com/watch?v=2vPe452cegU) | Seven flat gray levels, banded like the four-gray preview |
| Atari 8-bit, Bad Apple HD (JAC! and others, 2018) | [nMsMypjnI3Q](https://www.youtube.com/watch?v=nMsMypjnI3Q) | 1-bit threshold; the glow swallows the right girl in 2831 |
| Amiga, Electric Black Sheep vectorized (2022) | [4aWe9AqW5bc](https://www.youtube.com/watch?v=4aWe9AqW5bc) | 1-bit vectors; the same merge with the glow in 2831 |
| C64, Onslaught (2014) | [fu7rRYkWsyk](https://www.youtube.com/watch?v=fu7rRYkWsyk) | 1-bit blocks, dithered glow; has 2200 frames, and 2831 was not found |

The Atari 8-bit, Amiga, and C64 versions run at lower frame rates, so
their frames are the nearest ones, not exact matches.

## Step 3: first animation

`src/encode.py` encodes a span of the video; `src/main.c` plays it.

- **Encoder:** thresholds 128/192, snap 3/3, checkerboard fill. The tile
  set is the 511 tiles the whole video uses most, cached in
  `tileset.npz`. A stand-in is the kept tile with the fewest different
  pixels, counting border pixels 4 times. The encoder draws the layers
  back from its own files and checks every frame.
- **Files:** `tiles.bin` (4096 bytes, loaded into XRAM before start) and
  `video.bin` (a 16-byte header, then 9,600 bytes a frame), packaged as
  the named asset `ROM:video`.
- **Player:** two buffers. Each frame is read with `read_xram` into the
  back buffer. The player keeps the last VSYNC count in a static, waits
  for it to change twice, then points both layers at the back buffer.
  A slow frame finds VSYNC already moved on, so the waits return at once
  and the video catches up.
- **Test:** `tests/play.txt` (ctest `play`) runs two seconds and checks
  that the player starts without an error.

First run: 5 seconds, frames 300-449 (10.0-15.0 s). The tile set took
30 s over the whole video, the 150 frames 1.1 s. 383 of 720,000 cells use
a stand-in. Emulator screenshots after 60, 117, and 208 VSYNCs match
encoded frames 29, 58, and 103 pixel for pixel. The whole video would
take about 30 s for the set plus 48 s to encode, and makes 63.1 MB of
maps.

### The whole video

All 6573 frames encoded in 57 s with the tile set cached (43 s for the
frames). 21,939 of 31,550,400 cells (0.07%) use a stand-in; all 351
tiles left out of the set appear as stand-ins somewhere. `video.bin` is
63,100,816 bytes, the ROM 63.1 MB, and the web player zip 3.5 MB. One
full loop in the emulator, 48.97 s unpaced, kept time. A screenshot after
6620 VSYNCs matches frame 3309 (110.30 s) pixel for pixel.
Measured over the whole video with the border weighting, a frame is off
from its exact tiles by 5.64 pixels on average, 4.05 of them on tile
borders.

The video is done. The encoder is `src/encode.py`, and the project is
C only.

The encoded video is in Git as `src/badapple.tar.xz`, 2,188,392 bytes
(xz at its strongest preset; bz2 made 2.25 MB and zlib 3.07 MB). The
encoder writes it with fixed times and owners, so the same input gives
the same bytes. The build unpacks it with `cmake -E tar`, so CI builds and
publishes the full ROM. The README's screenshot is after 716 VSYNCs,
frame 357.

### Alternatives compared, and kept as they are

- **Corner sampling.** Point samples (nearest, bilinear, bicubic as from
  scaling to 641x481, Lanczos) look about the same as the one-cell
  average, better in some frames and worse in others. At snap 3 they
  need 868-1059 distinct tiles, against 862 for the average, which stays.
- **A 320x240 bitmap.** One mode 3 bitmap at 1bpp is the same 9,600 bytes
  per frame. Dithered with halftone screens, Bayer, blue noise, or
  Floyd-Steinberg, it looks far worse than the 640x480 marching-squares
  tiles, which stay.

## Step 4: audio

### Tools

PCM audio arrives in the next official release. Until then, local work
uses the emulator and the web player built by the rp6502 CI on the
`audio` branch, run 42121145980 (`rp6502-emu --version` prints `CI
42121145980`). They are in `data/emu/`, which Git ignores: the Windows
emulator, for WSL, and the web player, repacked in the layout of a release
web zip. `CMakeUserPresets.json`, also ignored, adds the preset `audio`.
It builds in `build/audio/` with `RP6502_EMU` and `RP6502_WEB` set to
those files. The `llvm-mos/Release` preset and CI keep the 0.42 release.

### The PCM device

From `ria.rst`, PCM Sampled Sound:

- `open("PCM:32000,16,2", O_WRONLY)`: 32 kHz, 16-bit signed little-endian,
  stereo, left then right. That is our format, 128,000 bytes per second.
- The device can be open once, and plays from a 4,096-byte buffer.
- Writes never block: a write takes as many bytes as fit and returns the
  count. `write_xram()` writes from XRAM, so samples go from a file to
  XRAM with `read_xram()` and on to the device with `write_xram()`,
  never through 6502 RAM.
- `lseek(pcm, 0, SEEK_CUR)` is the bytes waiting to play, `SEEK_END` the
  buffer size, `SEEK_SET` empties it. `close()` waits for the buffer to
  play.

### Budget

| | Bytes |
|---|---|
| Audio per VSYNC (60 Hz) | 2,133 |
| Audio per video frame (30 fps) | 4,267 |
| Video per frame | 9,600 |
| Both, per second | 416,000 (RP6502-PICO: up to 800 KB/s) |
| PCM device buffer | 4,096 = 32 ms of sound |
| ROM with audio | 63.1 MB + 28.0 MB = 91.1 MB |

The device buffer covers every call the loop waits on. On an
RP6502-PICO, at 800 KB/s:

| Call | Time | Sound played meanwhile |
|---|---|---|
| Read one video map, 4,800 bytes | 6.0 ms | 768 of 4,096 bytes |
| Read one audio buffer, 2,400 bytes | 3.0 ms | 384 bytes |

### Encoder

`src/encode.py` adds `audio.bin`: the soundtrack of the encoded span,
resampled by ffmpeg to 32 kHz, stereo, 16-bit, 1 dB lower so the
resampler does not clip. It is cut to exactly the video's length,
6573 / 30 s = 7,011,200 sample pairs, 28,044,800 bytes. (The source audio
runs 33 ms longer than the video.) It goes into `src/badapple.tar.xz` with
the video, plain xz like the rest: the archive grows to about 29 MB, and
CI builds the ROM with sound.

### Player

Two named assets open at once: `ROM:video` and `ROM:audio`, each with its
own file position, and the device `PCM:32000,16,2`.

- **No device, no playback.** Opening `PCM:` comes first. If it fails, the
  player prints `No PCM device found.` on the console and exits, before
  it changes the canvas, so the message shows on every machine. The 0.42
  release, which CI and GitHub Pages use, shows this until the next
  release.
- **XRAM.** Two audio buffers of 2,400 bytes (19 ms each) beside the two
  video buffers: 4,800 bytes more, 27.5 KB in all.
- **No call blocks the loop.** The player makes its API calls itself:
  push the arguments, write `RIA.op`, then go on. Each pass of the main
  loop checks VSYNC and flips when a frame is due, as now, whether or not
  a call is running. Only when `RIA.busy` is clear does it read the
  call's result and start the next call.
- **One call at a time.** The loop alternates a PCM write and a read. A
  PCM write sends what is left of the full audio buffer. A read fills an
  empty audio buffer first, or else reads the next map of the next video
  frame, 4,800 bytes, so an audio read can come between the two maps.
- **Video** keeps the static VSYNC count: two changes per frame, then a
  flip, if the back buffer is complete. A slow frame still catches up.
- **Start.** Load frame 0 and both audio buffers, then at a VSYNC show
  frame 0 and write the first audio. Sound and picture start together.
- **Loop.** At the end of the video, the rest of the sound plays out
  (`syncfs()` waits for it), both files go back to the start, and
  playback starts again as at the start, so sound and picture are back in
  sync on every pass. Over one 3:39 pass, the clocks cannot drift enough
  to hear.

### Tests

- The `play` test stays short: two seconds, no `ROM:` errors. On 0.42 it
  sees `No PCM device found.`, which is the expected result there.
- With the `audio` preset, a second short test records two seconds with
  the emulator script's `wav` command and checks that it matches the
  start of `audio.bin`, to catch gaps, offsets, or wrong format.

### Results

Built and run with the `audio` preset:

- `audio.bin` is 28,044,800 bytes, and `src/badapple.tar.xz` 29.2 MB. The
  ROM is 91.2 MB.
- Three seconds recorded with the emulator's `wav` command, from 1 s in,
  match `audio.bin` from 984 ms: correlation 0.99 in both channels, level
  ratio 1.008, and no silence where the source has sound. So the sound
  starts one VSYNC after the emulator does, with frame 0.
- After 240 VSYNCs, the screen is frame 119, pixel for pixel: on time with
  sound playing.
- The 0.42 release emulator prints `No PCM device found.`
- The `play` test passes on both presets.

### On the hardware

Run on an RP6502-PICO with the test build, `-DBADAPPLE_TEST=ON`, which
reads the frames from the machine's USB drive instead of the ROM.

- **Small reads were too slow.** A call costs a few milliseconds beyond its
  bytes, so 4,800-byte map reads and 2,400-byte audio reads came to
  406 KB/s, short of the 416 KB/s needed, and the video ran at half speed.
- **One file.** The encoder now writes `frames.bin`: a record per frame,
  the two maps and then the frame's sound, so picture and sound come in
  together, in large reads, from one file position.
- **Half-record reads.** Nothing feeds the PCM device during a read, and
  its buffer lasts 33 ms. A whole record took 26 ms on average and up to
  37 ms, and the sound dropped out. So the player reads each record in two
  halves, about 15 ms each, and fills the device before every read.
- **Triple buffering.** XRAM holds three records: the frame on screen and
  up to two loaded ahead.
- **Flips at VSYNC only.** A frame that was late showed as soon as its
  read finished, partway down the screen, and tore. Now a frame shows only
  at a VSYNC, and a late one waits for the next.
- **30,810 Hz.** Twice the 15.4 kHz that survives in the source is
  30.8 kHz, and 30,810 Hz is the next rate with a whole number of samples
  a frame, 1,027. Every record is then 13,708 bytes, and the player reads
  411,240 bytes per second.

Measured over 10 s, with the 32 kHz encoding before the last change:

| | |
|---|---|
| VSYNC, as the loop saw it | every 16,374-16,934 µs, against 16,667 |
| Reads | 603, at 460 kB/s, 91% of the time |
| Overall | 418 kB/s, 416 kB/s needed |
| Frames loaded ahead at each frame change | two 240 times, one 60 times, none 0 |
| Fewest bytes in the PCM device | 360, 2.8 ms of sound |

## Step 5: compressed maps

The firmware now reads over 1 MB/s, and two buffers are enough (step 4's
three-plane test, then a 10-second double-buffered ROM on an RP6502-PICO).
The ROM is 122 MB, and 95 MB of it is maps that barely change. This step
sends only the map bytes that change, decoded by the 6502. The RIA does
nothing new. The sound stays raw.

### Measured

On the current encoding, comparing each frame's three maps with the frame
two before it, the one its buffer last held:

| | Bytes |
|---|---|
| Changed map bytes per frame | 555 mean, 4,963 max, of 14,400 |
| Delta block per frame, format below | 1,118 mean, 3,219 at the 99th percentile, 5,585 max |
| All delta blocks | 7.4 MB, against 94.7 MB of maps |
| ROM | about 35 MB: 7.4 MB of maps, 27.0 MB of sound |
| Read rate | about 157 kB/s, against 555 kB/s |

### Format

`frames.bin`, `BAD4`: the header gives frame 0's delta length. Then per
frame, the delta block, then the 4,108 bytes of sound.

- **Delta block:** the length of the next frame's delta block (2 bytes),
  then runs, then a 0. A run is a map offset, 0 to 14,399 across the three
  maps (2 bytes), a count of 1 to 255, and that many tile IDs. A gap of
  four bytes or fewer between changes goes in the run as literals.
- **Deltas against two frames back,** the frame the buffer last held.
  Frames 0 and 1 are against all zeros, and each pass starts with both map
  buffers cleared.

### XRAM, using only what it needs

| | Bytes |
|---|---|
| Tiles, 3 planes | 6,144 |
| Config and palettes | 60 |
| Map buffers, 2 x 14,400 | 28,800 |
| Stream ring, deltas and sound | 16,384 |
| Total | 51,388 |
| Free for the transport bar, pointer, and index | about 14 KB |

### Player

- **Large reads.** A frame now averages about 5.2 KB, deltas and sound,
  too small for one read each: every call has a fixed cost, and reads
  stop gaining much between 8 and 16 KB. So the file streams into a
  16 KB ring in XRAM, 8 KB a read, whenever 8 KB of the ring is free.
  That is a read about every 1.5 frames, about 8 ms each on an
  RP6502-PICO.
- **Parsing the ring.** The 6502 reads each frame's delta block from the
  ring through `RW1`, and its sound goes to the PCM device straight from
  the ring with `write_xram()`, in two writes where it wraps. Ring space
  is free again once a frame's delta is applied and its sound sent.
- **The 6502 applies the delta** into the back map buffer: for each run,
  set `ADDR0` to the map offset, then copy count bytes from the ring
  (`RW1`) to the map (`RW0`), about 13 cycles a byte. A frame averages
  about 2 ms of this and about 9 ms at worst.
- **The copy never holds up VSYNC.** The main loop applies one run, or at
  most about 256 bytes, per pass, and checks VSYNC every pass, so a flip
  still lands in the 1.37 ms window.
- **A frame flips at its VSYNC once its delta is applied,** as now. A late
  frame shows at the next VSYNC.
- **Everything else stays:** the PCM top-up before every read and at every
  VSYNC, the static VSYNC count, and the sync at the start of each pass.

### Tests

- The encoder applies every delta block to two simulated buffers and
  checks that each frame comes out as encoded.
- The emulator's short `play` test, then a screenshot at frame 357.
- A 10-second ROM on the hardware, then the whole video in the emulator.

### Later

The transport bar and pointer are planned as sprites on plane 2, with a
tablet. Each plane has a sprite layer drawn over its fill layer, so they
go over the edge tiles with no change to them. The free XRAM above is
meant for them and for an index asset of frame positions.

### Results

- The stream format is `BAD4`, as planned. The delta blocks are 7.4 MB,
  averaging 1,126 bytes a frame, 5,647 at most, and `frames.bin` is
  34.4 MB. The encoder plays the stream back and checks every frame.
- The run loop is in assembly, `src/copy.s`: unrolled by eight, counters
  in zero page, and the stream position read back from ADDR1 once per
  call, with no per-run 16-bit sums. A first version in C decoded every
  frame exactly but fell 220 frames behind in 4,000 VSYNCs.
- In the emulator, screenshots after 716, 4,000, 12,000 and 12,600 VSYNCs
  each match the encoder's frame pixel for pixel, 3 frames after VSYNC / 2,
  the start-up time. Sound recorded at the start and at the spinning
  yin-yang keeps one alignment, second by second, with no dropouts.
- Late frames over the whole video, counted with a temporary probe: none
  at 8 MHz, none at 4 MHz, 19 at 3 MHz, 5,053 at 2 MHz. The decoder has
  at least twice the CPU it needs.
- A 10-second ROM played cleanly on an RP6502-PICO, and then the whole
  video did.

## Step 6: transport

A transport bar over the video: play and pause, back and forward 10
seconds, scrubbing, repeat, and volume, driven by the tablet interface
(mouse, pen, or touch) and by a gamepad. It fades out after a few seconds
without input, and comes back on any movement or button.

### Seeking: keyframes and an index

Every frame is a delta against the frame two before it, so playback can
only start where both map buffers are known. Today that is only frame 0.

- **Keyframes.** At the start of every second, frames 30n and 30n+1 are
  coded against cleared maps, and their delta blocks carry a flag. Before
  applying a flagged block, the player clears that map buffer, 14,400
  bytes, in assembly, about 8 ms. In plain playback that happens twice a
  second. Measured on the current encoding, keyframe blocks average 2,724
  bytes, 5,375 at most, and add 0.71 MB to the 34.4 MB stream.
- **The index,** a second ROM asset, `ROM:index`: for each second, the
  file offset of its keyframe (4 bytes) and the length of its delta block
  (2 bytes). 220 seconds make 1.3 KB, loaded into 6502 RAM at start, so a
  seek costs no read of its own.
- **A seek:** empty the PCM device (`lseek` with `SEEK_SET`), `lseek` the
  stream to the keyframe, refill the ring, decode the keyframe pair, and
  go on. About 40 ms, so scrubbing can show 20 or more seconds a second.
- **Scrubbing** shows the keyframe of each second the playhead crosses,
  with no sound, and plays from the second it is let go at.

### Volume

The docs give the PCM device no volume control, so the 6502 scales the
sound in the ring before it is sent. A second assembly routine reads each 16-bit
sample through portal 1, looks up `hi * v` (16 bits) and `lo * v / 256` in
tables in 6502 RAM, 768 bytes rebuilt when the volume changes, and writes
the sum back through portal 0 in place. About 35 cycles a sample, 72,000
a frame, 27% of the 6502. It runs in steps of about 256 bytes, like the
decoder, and PCM writes never pass the scaled part. At full volume it is
skipped. Sixteen steps; the decoder's worst frames use under half the
6502, so the two fit, and the emulator at lower clock speeds will show the
margin.

### The bar

- **Sprites** on plane 2's sprite layer, over the video: mode 5 custom
  sprites, 4-bit color, at full resolution, with smooth edges.
- **Parts:** the bar's background, the track, the progress fill, the
  playhead, buttons for back 10 s, play or pause, forward 10 s, and
  repeat, a time readout (1:23 / 3:39) from digit sprites, a volume icon
  and slider, and the pointer.
- **XRAM:** under 10 KB of the 14 KB free, art and sprite array together.
  The bar's scanlines cost about 400 of the VGA's 1,600 clocks at 640
  wide.
- **The fade** is done with the palettes. Alpha is one bit, so a color
  cannot go half transparent. Instead each pixel of the art carries a rank
  from an ordered-dither pattern as well as its color, and the palette
  has an entry for each color and rank. Fading out turns the ranks
  transparent one at a time, so the bar dissolves in a few steps, over
  about half a second. With 4-bit color, each part's palette holds 3
  tones, its gel, the charcoal, and one between them for the smooth
  edges, in 5 ranks, plus transparent.
- **Colors:** pastels on the black and white, like light through colored
  paper.

### The design: gel discs

Chosen from four studies. There is no bar behind the controls: each one is
its own disc of pastel "stage gel" with a charcoal rim and icon, and the
track is a thin charcoal-edged line between them.

- **Discs, left to right:** back 10 s (sky), play or pause (butter),
  forward 10 s (sky), then the track, then repeat (mint) and the speaker
  (lilac), with a short volume slider after it.
- **The track:** charcoal edge, lilac inside, peach where it has played,
  and a peach playhead. The time rides above the playhead in a small
  butter pill.
- **Colors:** peach F4C6B4, butter F2E2A4, mint BCE2CF, sky BCD5ED, lilac
  D4C7EB, and charcoal 3D3A42. Each disc has its own palette, its gel and
  the charcoal, so a 4-bit palette holds its colors at full dissolve
  steps.
- **XRAM:** about 4 KB at full resolution: five 32x32 discs, track and
  fill pieces that repeat, the digits, and the pointer.
- **The pointer** is charcoal with a butter fill.

### Fading

- The bar and the pointer dissolve out together, in the pixelated steps
  of the palettes, after 3 seconds without input while playing.
- They come back at once, with no dissolve in, so the pointer is under
  control the moment it moves. The input that brings them back also
  does what it asks.
- They stay while paused.

### Controls

| | Tablet (mouse, pen, touch) | Gamepad |
|---|---|---|
| Play, pause | the play button | A (south) |
| Back, forward 10 s | the buttons | d-pad left, right |
| Scrub | drag the playhead or click the track | hold a shoulder button, or the left stick |
| Repeat | the repeat button | Y (north) |
| Volume | drag the slider | d-pad up, down |
| Mute | the speaker | X (west) |
| Show the bar | move the pointer | any button, which also does what it asks |

- The bar and pointer fade after 3 seconds without input while playing,
  and stay while paused.
- At start the player shows the title screen, below, with the bar, and
  waits. Repeat is off and the volume is full.
- At the end, with repeat off, the title screen comes back. With repeat
  on, the video loops as now and the title screen never shows.
- The speaker mutes and unmutes, and the slider sets the volume.

### Keyboard

| | Keys |
|---|---|
| Play, pause | Space |
| Back, forward 10 s | left, right arrows |
| Volume | up, down arrows |
| Mute | M |
| Repeat | R |

### The title screen

Shown at the very start, paused before frame 0, which is also where the
video returns when it ends with repeat off; always with the transport
over it. A paused video shows its frame, not the title.

- **A lazy start.** On the title, a click or tap anywhere above the
  transport starts the video. Someone on a touchscreen can tap the
  middle. Keys and buttons only do their transport actions.
- **Transport actions do what they say.** A click on the transport, or a
  mapped key or button, acts as it would during the video: forward 10 s,
  for one, leaves the title and pauses at 0:10.
- **The end.** The source already ends with 58 black frames, 1.9 s, so
  the title comes back after a natural pause, with nothing added.

```
                    Bad Apple!!
              for the Picocomputer 6502

  MUSIC   ZUN                  composer, "Bad Apple!!", 1998
          Masayoshi Minoshima  arrangement, 2007
          nomico               vocals
          Haruka               lyrics

  VIDEO   Μμ                   storyboard, 2008
          Anira and team       shadow-art animation, 2009

           Click or press Space to play
  Space play · ◀▶ 10 seconds · ▲▼ volume · M mute · R repeat
```

- **Type:** Shippori Mincho, from four studies, antialiased, at full
  resolution; Greek in Noto Serif, which Mincho lacks. `src/title.py`
  renders it.
- **Colors:** 4-bit tiles on plane 0: black, and white, butter, and lilac
  in five steps each from black, blended in linear light. White for the
  names, the Picocomputer line, and the keys; butter for the title, feat.
  nomico, and the prompt; lilac for the headings and roles.
- **Layout:** the text stops at line 396, above the transport, which
  always shows; the roles sit in a column clear of the longest name.
- **Tiles:** about 800 distinct tiles, so plane 0 runs in four bands of
  scanlines, each a mode 2 layer with 256 tiles of its own, all reading
  one map. 32 KB of tiles and the 4,800-byte map, `title.bin`, a ROM
  asset, read into the video's map buffers and ring, which the title does
  not use. Planes 1 and 2 are moved off the canvas. Starting the video
  reloads the video's tiles from the ROM and sets the three planes back.

### The web player

The ROM has its own play button now, so the web player no longer needs
one of its own. `rp6502_web()` in `CMakeLists.txt` drops `autoplay:
'off'`, for the default `on`, and sets `overlay: false`: the ROM starts
when the page loads and shows the title screen with its transport. The
browser allows sound at the first click on the player, the click that
starts the video. The README's screenshot then shows the title screen.

### XRAM

| | Bytes |
|---|---|
| Now: tiles, maps, ring | 51,388 |
| Tablet and gamepad state | about 100 |
| Transport art, palettes, sprite array | under 10,000 |
| Free | about 4,000 or more |

### Order of work

1. Keyframes, the index, and seeking, tested with keys in the emulator's
   script before there is a bar.
2. Volume scaling, and the emulator at lower clock speeds for the CPU
   margin.
3. The bar's art and sprites, from the chosen design, and the fade.
4. Tablet and gamepad input.
5. A short sample on the hardware.

### Results

- The encoder writes keyframes, `index.bin`, `title.bin`, and
  `transport.bin`. Keyframes add 0.7 MB; `frames.bin` is 35.1 MB.
- In the emulator, with the keyboard, the tablet, and a gamepad driven by
  its script: the title screen, a lazy start from a click, play and
  pause, 10-second skips, a click on the track, the
  volume slider, repeat, mute, the end back to the title or, with repeat
  on, a second pass, the dissolve after 3 seconds, the pointer leaving the
  canvas, and the transport coming back at once.
- The volume scaler halves the level exactly at -6 dB, checked against the
  stream.
- Late frames over the whole video, volume lowered, transport drawn: none
  at 8 MHz, 3 at 6 MHz. Drawing only what changed in the transport, and
  unrolling the scaler by four, bought that margin.

### Adjustments

- The title drops "feat. nomico", who is credited under MUSIC; it reads
  "Bad Apple!!", then "for the Picocomputer 6502".
- The keys line draws its arrows as solid triangles; Mincho's arrows were
  hairlines. The prompt reads "Click or press Space to play".
- The discs had light pixels outside their charcoal rims, which sparkled
  on black: Pillow scales RGBA with the alpha premultiplied and returns
  straight colors, which `src/transport.py` divided by the alpha again.
- The pointer the transport draws is a black and white desktop arrow.
- A click or tap on the video, above the top of the time label, plays and
  pauses it, and starts it from the title screen; a click on the
  transport does only what it hits. Keys and buttons do only their
  transport actions.
- The volume steps are even in level, as a web video player's are, so
  the middle of the slider is -6 dB. In steps of 3 dB the middle was
  -18 dB, which sounded far too quiet.
- Two arguments: `play` starts the video at once, without the title
  screen, and `repeat` turns repeat on. Anything else prints the two and
  stops.
- Any input acts at once, as well as showing the faded transport. At
  first the input that brought the transport back did nothing else, so a
  gamepad's A had to be pressed twice to pause.

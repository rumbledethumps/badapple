# Bad Apple!! on the Picocomputer 6502

A port of the Bad Apple!! shadow-art video and its music to the RP6502.
It is a mechanical port of other people's work, so the project takes no
credit, and the credits below go with it.

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

## Later steps (to be defined)

- Audio playback, when the PCM emulator and documentation arrive.

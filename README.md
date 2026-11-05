# Bad Apple!! for the Picocomputer 6502

The Bad Apple!! shadow-art video on the
[Picocomputer 6502](https://picocomputer.github.io/), all 6573 frames at
30 fps, as 640x480 black-and-white tiles. This is a port of other people's
work, so the project claims none of it. The credits are below.

The video plays today. The soundtrack waits on PCM audio for the RP6502,
which is in progress. The plan for it is under [The audio](#the-audio).

## Credits

| Year | Work | By |
|---|---|---|
| 1998 | "Bad Apple!!", the Stage 3 theme of *Touhou Gensokyo ~ Lotus Land Story* (PC-98) | ZUN |
| 2007 | "Bad Apple!! feat. nomico", on the album *Lovelight* (Alstroemeria Records) | Masayoshi Minoshima (arrangement), nomico (vocals), Haruka (lyrics) |
| 2008 | The storyboard of the shadow-art PV, Niconico `nm3601701` | Μμ |
| 2009 | The shadow-art PV, Niconico [`sm8628149`](https://www.nicovideo.jp/watch/sm8628149) | Anira (あにら) and team |

The video and the soundtrack both come from Anira's upload, `sm8628149`.

## The video

The source is Niconico's 512x384 stream of `sm8628149`: 30 fps, 6573 frames,
219.1 seconds. It is shadow art: hard black-and-white silhouettes, with soft
gray where the animation draws motion blur and glows.

### Marching squares

The VGA system draws each frame from two maps of 8x8 1bpp tiles
([mode 2](https://picocomputer.github.io/vga.html)), 80x60 tiles on a
640x480 canvas. `src/encode.py` picks the tiles:

1. **Corner samples.** Each frame is averaged down to an 81x61 grid, one
   sample at each corner of the 80x60 cells. Each sample is the average of
   a box one cell wide around its corner, so a soft edge gives it a gray
   value between black and white.
2. **Two outlines.** In each cell, marching squares finds where two outlines
   cross the cell's edges: a dark line at gray 128 of 255 and a light line
   at 192. Each crossing is interpolated between the cell's corners and
   snapped to one of three positions along the tile edge. Two cells that
   share an edge compute the same crossings from the same two corners, so
   outlines join up from tile to tile.
3. **Three levels.** The outlines split each tile into black (darker than
   the dark line), white (lighter than the light line), and a checkerboard
   fill, every other pixel, between them. The fill is a hint of the motion
   blur and the glows, and the silhouettes stay sharp.

### 511 tiles for the whole video

Mode 2 holds 256 tiles for each layer, and the player uses two layers, each
with its own tiles. Tile 0 of both layers is all black. Black is
transparent on the top layer, so each cell shows either a top tile over the
bottom layer's tile 0, or a bottom tile through the top layer's tile 0.
That gives 511 different tiles on screen, with no change to the tiles
during playback.

The whole video needs 862 different tiles. The 511 that it uses most cover
99.93% of its 31.5 million cells. Each other cell shows the nearest of the
511: the one with the fewest different pixels, where a pixel on the tile's
border counts four times. A small error inside a tile is hard to see, but
a step in an outline where two tiles meet is easy to see. On average a
frame is off from its exact tiles by about 6 of its 307,200 pixels.

`src/encode.py` writes two files to `data/encoded/`:

- `tiles.bin`, 4096 bytes: the 256 bottom tiles, then the 256 top tiles,
  8 bytes each, one byte per row, leftmost pixel in the high bit. The ROM
  loads it into XRAM before the program starts.
- `video.bin`: a 16-byte header (`BAD1`, the frame count, the first source
  frame, and the frame rate), then for each frame the 80x60 bottom map and
  the 80x60 top map, one tile number per byte. That is 9,600 bytes per
  frame, 288,000 bytes per second, and 63.1 MB for the whole video. The ROM
  carries it as the named asset `ROM:video`.

After writing the files, the encoder draws every frame back from them, the
way the two layers do, and checks that each one comes out as encoded. It
also writes `preview.mp4`, the encoded frames with the soundtrack. The
whole video encodes in under two minutes.

## The player

`src/main.c` plays `ROM:video` in a loop:

- **Double buffering.** XRAM holds two buffers of both maps. While one
  buffer is on screen, `read_xram()` reads the next frame's 9,600 bytes
  from the ROM straight into the other.
- **VSYNC.** The display runs at 60 Hz, so a frame lasts two VSYNCs. At the
  first VSYNC at or after a frame's time, the player points both layers at
  the new buffer. That is two 16-bit writes, done while the display is
  between frames, so nothing tears.
- **Catching up.** Each frame's time counts from the start of the loop,
  not from the frame before it. A frame that is already due when it
  finishes loading shows at the next VSYNC. When playback falls a whole
  frame behind, the player skips ahead to the frame that is due. At the
  end of each loop it prints how many frames were late and how many it
  skipped.

## The audio

The soundtrack is the audio of the same Niconico upload: AAC-LC, 44.1 kHz,
stereo, about 113 kbps. The port will play it as raw PCM at **32 kHz,
stereo, 16 bits**.

- **It is real stereo.** The two channels differ in 98% of samples and
  correlate at 0.91. Their difference averages 13 dB below their sum, and
  comes within about 3 dB of it in the widest passages.
- **32 kHz holds everything in the file.** Niconico's AAC encoder removed
  everything above about 15.4 kHz: the average spectrum falls from −49 dB at
  15 kHz to −75 dB at 15.5 kHz, and stays at the noise floor from there to
  22 kHz. A sample rate covers frequencies up to half its value, so 32 kHz
  carries up to 16 kHz, which is all that survived. The arrangement was
  released on CD at 44.1 kHz, but the detail above 15.4 kHz is gone from
  every copy that this port can use. A rate of 24 kHz or less would start
  to cut real content between 11 and 15 kHz, the cymbals and hi-hats.
- **16 bits is plenty.** The master is loud: its level averages −8.4 dBFS,
  and its peaks reach full scale. The resampler lowers the gain about 1 dB,
  so that its filter does not clip.

At 32 kHz, stereo, and 16 bits, the soundtrack is 128,000 bytes per second
and 28.0 MB for its 219 seconds. With the video, the player will read
416,000 bytes per second. An RP6502-PICO moves up to 800 KB per second from
a file to XRAM.

## Building

Requirements:

- CMake 3.28 or newer, Make or Ninja, and
  [llvm-mos](https://picocomputer.github.io/sdk.html#sdk-install).
- Python 3 with numpy, and ffmpeg.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp), to download the source
  video.

The source video and the encoded data stay in `data/`, which Git ignores.
Download the video, encode it, then build:

```text
yt-dlp -f "video-h264-360p-1+audio-aac-128kbps" -o "data/sm8628149-512x384.%(ext)s" \
    https://www.nicovideo.jp/watch/sm8628149
python3 src/encode.py data/sm8628149-512x384.mp4
cmake --preset llvm-mos/Release
cmake --build --preset llvm-mos/Release
```

`src/encode.py --start 10 --seconds 5` encodes part of the video, and
`--help` lists the other options. The first run builds the tile set from
the whole video and caches it in `data/encoded/tileset.npz`.

The build writes `build/llvm-mos/release/badapple/badapple.rp6502`. Without
the encoded data, it builds the player alone, which says that `ROM:video`
is missing.

## Running

- **Emulator.** In VS Code, press F5 with the RP6502-EMU launch
  configuration, or run
  `build/llvm-mos/release/badapple/rp6502-emu build/llvm-mos/release/badapple/badapple.rp6502`.
- **Web player.** The build also writes the web player to
  `build/llvm-mos/release/web/badapple/`, with the 63 MB ROM. The
  RP6502-WEB launch configuration serves it and opens it in a browser.
- **Test.** `ctest --test-dir build/llvm-mos/release` runs the `play`
  test: one pass of the whole video in the emulator, which passes when no
  frame is late or skipped.

On each push to `main`, `.github/workflows/web.yml` publishes the web player
to GitHub Pages, from the `rp6502` comment below. That build has no encoded
data, because `data/` is not in Git, so for now it plays the player alone.

<!-- rp6502
preset: llvm-mos/Release
publish: badapple.zip
-->
[Bad Apple!! in the browser](https://rumbledethumps.github.io/badapple/badapple/)

## Updating the tools

`tools/` holds the CMake and Python scripts of the
[RP6502 SDK](https://picocomputer.github.io/sdk.html). Update them with the
"RP6502: update tools" task (Terminal > Run Task), or with:

```text
cmake -P tools/rp6502.cmake
```

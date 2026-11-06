# Bad Apple!! for the Picocomputer 6502

The Bad Apple!! shadow-art video on the
[Picocomputer 6502](https://picocomputer.github.io/), all 6573 frames at
30 fps, as 640x480 black-and-white tiles. This is a port of other people's
work, so the project claims none of it. The credits are below.

The soundtrack plays through the PCM audio device of the RP6502 release
after 0.42. On older versions the player prints `No PCM device found.` and
stops, and so does the web player below until that release.

<!-- rp6502
preset: llvm-mos/Release
publish: badapple.zip
frames: 716
-->
[![Bad Apple!!, frame 357](https://rumbledethumps.github.io/badapple/badapple/screenshot.png)](https://rumbledethumps.github.io/badapple/badapple/)

[Play it in your browser](https://rumbledethumps.github.io/badapple/badapple/).

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

`src/encode.py` writes three files, and packs them into
`src/badapple.tar.xz` for the build:

- `tiles.bin`, 4096 bytes: the 256 bottom tiles, then the 256 top tiles,
  8 bytes each, one byte per row, leftmost pixel in the high bit. The ROM
  loads it into XRAM before the program starts.
- `video.bin`: a 16-byte header (`BAD1`, the frame count, the first source
  frame, and the frame rate), then for each frame the 80x60 bottom map and
  the 80x60 top map, one tile number per byte. That is 9,600 bytes per
  frame, 288,000 bytes per second, and 63.1 MB for the whole video. The ROM
  carries it as the named asset `ROM:video`.
- `audio.bin`: the soundtrack, as described under [The audio](#the-audio),
  cut to the exact length of the video, 28,044,800 bytes. The ROM carries
  it as the named asset `ROM:audio`.

The archive is 29.2 MB, and Git keeps it, so the build needs no source
video and no encoder. After writing the files, the encoder draws every frame back
from them, the way the two layers do, and checks that each one comes out as
encoded. It also writes `preview.mp4` in `data/encoded/`, the encoded frames
with the soundtrack.

## The player

`src/main.c` plays `ROM:video` and `ROM:audio` in a loop:

- **PCM first.** The player opens `PCM:32000,16,2` before anything else.
  When it cannot, it prints `No PCM device found.` and stops.
- **Double buffering.** XRAM holds two buffers of both maps. While one
  buffer is on screen, `read_xram()` reads the next frame's 9,600 bytes
  from the ROM straight into the other.
- **Sound.** XRAM also holds two 2,400-byte audio buffers. `read_xram()`
  fills them from `ROM:audio`, and `write_xram()` sends them on to the PCM
  device, so the samples never pass through 6502 RAM.
- **No waiting on calls.** The player starts each API call itself, through
  the RIA registers, and goes on with its loop while the call runs. When
  `RIA.busy` clears, it takes the result and starts the next call: a PCM
  write every other time, and in between a read: an empty audio buffer
  first, or else the next 4,800-byte map of the next frame.
- **VSYNC.** The display runs at 60 Hz, so a frame lasts two VSYNCs. The
  player keeps the last VSYNC count in a static, counts each change of
  the VSYNC register, and after two shows the next frame, whether or not
  a call is running.
- **Catching up.** When a frame runs long, VSYNC has already moved past the
  stored count, so the next frame shows as soon as it is loaded and the
  video catches up instead of stretching.
- **Each pass starts in sync.** Frame 0 and both audio buffers load, then
  frame 0 shows at a VSYNC and the sound starts right after it. At the
  end, the player sends the rest of the sound, waits for it to play, prints
  `Loop` and a count, and starts the next pass the same way.

## The audio

The soundtrack is the audio of the same Niconico upload: AAC-LC, 44.1 kHz,
stereo, about 113 kbps. The player plays it as raw PCM at **32 kHz,
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
and 28.0 MB for its 219 seconds. With the video, the player reads 416,000
bytes per second. An RP6502-PICO moves up to 800 KB per second from a file
to XRAM.

The PCM device plays from a 4,096-byte buffer, 32 ms of this sound. The
player reads each frame in two calls, one 4,800-byte map each, 6 ms on an
RP6502-PICO, so an audio read can come between them.

## Building

Building needs CMake 3.28 or newer, Make or Ninja, and
[llvm-mos](https://picocomputer.github.io/sdk.html#sdk-install):

```text
cmake --preset llvm-mos/Release
cmake --build --preset llvm-mos/Release
```

The build unpacks `src/badapple.tar.xz` into the build folder, and writes
the 91 MB ROM to `build/llvm-mos/release/badapple/badapple.rp6502`.

### Encoding the video

Encoding needs Python 3 with numpy, ffmpeg, and
[yt-dlp](https://github.com/yt-dlp/yt-dlp). The source video stays in
`data/`, which Git ignores. Download it, then encode it:

```text
yt-dlp -f "video-h264-360p-1+audio-aac-128kbps" -o "data/sm8628149-512x384.%(ext)s" \
    https://www.nicovideo.jp/watch/sm8628149
python3 src/encode.py data/sm8628149-512x384.mp4
```

The whole video encodes in about a minute, plus 30 seconds the first time
to build the tile set, which the encoder caches in
`data/encoded/tileset.npz`. The encoder writes `src/badapple.tar.xz`, and
the same video and settings give the same archive, byte for byte, so Git
sees a change only when the encoding changes.

`--start 10 --seconds 5` encodes five seconds from 10.0 s, video and sound,
into
`data/encoded/badapple.tar.xz`, so the archive in `src/` keeps the whole
video. To build a part, add `--archive src/badapple.tar.xz`. `--help` lists
the other options.

## Running

- **Emulator.** In VS Code, press F5 with the RP6502-EMU launch
  configuration, or run
  `build/llvm-mos/release/badapple/rp6502-emu build/llvm-mos/release/badapple/badapple.rp6502`.
- **Web player.** The build also writes the web player to
  `build/llvm-mos/release/web/badapple/`, with the 91 MB ROM. The
  RP6502-WEB launch configuration serves it and opens it in a browser.
- **Test.** `ctest --test-dir build/llvm-mos/release` runs the `play`
  test: two seconds in the emulator, which passes when the player finds
  its ROM assets.

Until the release with PCM audio, the emulator and the web player from the
rp6502 CI builds play the sound. Set `RP6502_EMU` and `RP6502_WEB` to their
files, as [Local Files](https://picocomputer.github.io/sdk.html) in the SDK
describes, for example in a `CMakeUserPresets.json`, which Git ignores.

On each push to `main`, `.github/workflows/web.yml` builds the ROM and
publishes the web player at the top of this page to GitHub Pages. Its
picture is the player's screen after 716 VSYNCs: frame 357 once the
release with PCM audio is out, and `No PCM device found.` until then.

## Updating the tools

`tools/` holds the CMake and Python scripts of the
[RP6502 SDK](https://picocomputer.github.io/sdk.html). Update them with the
"RP6502: update tools" task (Terminal > Run Task), or with:

```text
cmake -P tools/rp6502.cmake
```

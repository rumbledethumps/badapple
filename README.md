# Bad Apple!! for the Picocomputer 6502

The Bad Apple!! shadow-art video on the
[Picocomputer 6502](https://picocomputer.github.io/), all 6573 frames at
30 fps, as 640x480 black-and-white tiles.

The soundtrack plays through the PCM audio device of RP6502 0.43 and
later. On older versions the player prints `No PCM device found.` and
stops.

<!-- rp6502
preset: llvm-mos/Release
publish: badapple.zip
frames: 538
-->
[![Bad Apple!!, frame 268](https://rumbledethumps.github.io/badapple/badapple/screenshot.png)](https://rumbledethumps.github.io/badapple/badapple/)

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

### Hard edges over real gray

The VGA system draws each frame on three planes of 8x8 1bpp tiles
([mode 2](https://picocomputer.github.io/vga.html)), 80x60 tiles each on
a 640x480 canvas. `src/encode.py` picks the tiles:

1. **Real gray.** Source pixels from 31 to 254 of 255 are gray. Much of
   that gray is a thin band along a hard edge, its antialiasing. An
   opening drops it: the gray shrinks by 12 source pixels, then what is
   left grows back. A band thinner than that is gone, and wide gray, the
   motion blur, glows, and shadows, comes back.
2. **Corner samples.** Each frame is averaged down to an 81x61 grid, one
   sample at each corner of the 80x60 cells. Each sample is the average of
   a box one cell wide around its corner.
3. **Hard edges, planes 1 and 2.** In each cell, marching squares finds
   where the outline at gray 127 crosses the cell's edges. Each crossing
   is interpolated between the cell's corners and snapped to one of seven
   positions along the tile edge. Two cells that share an edge compute the
   same crossings from the same two corners, so outlines join up from tile
   to tile. The light side of the outline is white, and the rest is clear,
   as is everything inside the real gray.
4. **Gray, plane 0.** The real gray gets an outline of its own, made the
   same way, and is drawn as a checkerboard, every other pixel, on black.
   Plane 0 is opaque, so it is also the black under everything.

### Tiles for the whole video

Mode 2 holds 256 tiles for each plane. They load once, before the video
starts, and do not change.

- **Edges.** Planes 1 and 2 share the edge tiles. Tile 0 of both is
  clear, so a cell shows a tile from one or the other, which gives 511.
  The whole video uses 466, so every edge is exact.
- **Gray.** Plane 0 holds the 256 gray tiles used most, with tile 0 all
  black. The whole video uses 328. The next 45 go in the 45 spare edge
  slots: a checkerboard tile looks the same on plane 1 or 2, over plane
  0's black tile, in a cell with no edge.
- **Stand-ins.** A cell whose tiles did not fit shows the nearest kept
  tile: the one with the fewest different pixels, where a pixel on the
  tile's border counts four times, because a step in an outline where two
  tiles meet is easy to see. 1,339 of the video's 31.5 million cells use
  a stand-in.

`src/encode.py` writes two files, and packs them into
`src/badapple.tar.xz` for the build:

- `tiles.bin`, 6,144 bytes: 256 tiles for each of the three planes, 8
  bytes each, one byte per row, leftmost pixel in the high bit. The ROM
  loads it into XRAM before the program starts.
- `frames.bin`: a 16-byte header (`BAD4`, the frame count, the first
  source frame, the frame rate, and the length of frame 0's delta block),
  then for each frame its delta block and its sound, 4,108 bytes, as
  described under [The audio](#the-audio). The ROM carries it as the
  named asset `ROM:frames`.

A frame's three 80x60 maps, one tile number per byte, are 14,400 bytes,
but few of them change from frame to frame. The player keeps two map
buffers, so the buffer that a frame decodes into still holds the frame two
before it, and the delta block holds only the runs that change it: a
2-byte map offset, a count of 1 to 255, and that many tile numbers, with
gaps of up to four unchanged bytes carried in the run. FF FF ends the
block, which starts with the length of the next frame's block. Frames 0
and 1 are deltas against all zeros. The delta blocks average 1,126 bytes a
frame, 5,647 at most, and 7.4 MB in all, against 94.7 MB of maps. With the
sound, `frames.bin` is 34.4 MB.

The archive is 30.0 MB, and Git keeps it, so the build needs no source
video and no encoder. After writing the files, the encoder plays the
stream back the way the player does, into two map buffers, draws the
three planes, and checks that each frame comes out as encoded. It also
writes `preview.mp4` in `data/encoded/`, the encoded frames with the
soundtrack.

## The player

`src/main.c` plays `ROM:frames` in a loop:

- **PCM first.** The player opens `PCM:30810,16,2` before anything else.
  When it cannot, it prints `No PCM device found.` and stops.
- **A stream ring.** `read_xram()` reads the file into a 16 KB ring in
  XRAM, 4 to 8 KB a read, whenever the ring has room.
- **Decoding in the 6502.** Once a frame's delta block and sound are both
  in the ring, the 6502 applies the runs to the back map buffer:
  `src/copy.s` reads the ring through portal 1 and writes the maps through
  portal 0, eight bytes a pass, about 8.6 cycles a byte, with its counters
  in zero page. It stops after about 256 bytes, so the main loop can check
  VSYNC between steps. Near the end of the ring, where a run could wrap,
  C applies one run at a time.
- **Double buffering.** One map buffer is on screen while the next frame
  decodes into the other.
- **VSYNC.** A frame is shown by pointing all three planes at its maps.
  The display runs at 60 Hz, so a frame lasts two VSYNCs. The player keeps
  the last VSYNC count in a static, and at every second change it shows
  the next frame right away, in the 1.4 ms before the first scanline, so
  the picture never tears.
- **Catching up.** A frame that is not decoded by its VSYNC shows at the
  next one, and the frame after it one VSYNC sooner, so the video catches
  up instead of stretching.
- **Sound.** `write_xram()` sends each frame's sound from the ring to the
  PCM device, in order, so the samples never pass through 6502 RAM.
- **No waiting on calls.** The player starts each API call itself, through
  the RIA registers, and goes on with its loop, decoding and watching
  VSYNC, while the call runs. When `RIA.busy` clears, it takes the result
  and starts the next call.
- **Feeding the device.** Nothing feeds the PCM device during a read, and
  its 4,096-byte buffer plays for 33 ms. So the player fills the device
  before every read, and at every VSYNC.
- **Each pass starts in sync.** Both map buffers are cleared, the ring
  fills, and frame 0 decodes, then shows at a VSYNC, and its sound starts
  right after it. At the end, the player sends the rest of the sound,
  waits for it to play, and starts the next pass the same way.

XRAM holds the tiles, 6,144 bytes, the two map buffers, 28,800, and the
ring, 16,384: 51.4 KB, leaving about 14 KB.

In the emulator, over the whole video, no frame was late at the 6502's
8 MHz, and none at 4 MHz either. At 3 MHz, 19 frames were late. A
10-second sample played cleanly on an RP6502-PICO.

## The audio

The soundtrack is the audio of the same Niconico upload: AAC-LC, 44.1 kHz,
stereo, about 113 kbps. The player plays it as raw PCM at **30,810 Hz,
stereo, 16 bits**.

- **It is real stereo.** The two channels differ in 98% of samples and
  correlate at 0.91. Their difference averages 13 dB below their sum, and
  comes within about 3 dB of it in the widest passages.
- **30.8 kHz holds everything in the file.** Niconico's AAC encoder
  removed everything above about 15.4 kHz: the average spectrum falls from
  −49 dB at 15 kHz to −75 dB at 15.5 kHz, and stays at the noise floor from
  there to 22 kHz. A sample rate covers frequencies up to half its value,
  so 30.8 kHz carries all that survived. 30,810 Hz is the next rate up
  with a whole number of samples in each frame, 1,027, so every record
  holds the same amount of sound. The PCM device takes any rate up to
  48 kHz. The arrangement was
  released on CD at 44.1 kHz, but the detail above 15.4 kHz is gone from
  every copy that this port can use. A rate of 24 kHz or less would start
  to cut real content between 11 and 15 kHz, the cymbals and hi-hats.
- **16 bits is plenty.** The master is loud: its level averages −8.4 dBFS,
  and its peaks reach full scale. Decoded, the AAC overshoots to
  +2.05 dBFS, so the encoder lowers it 2.5 dB, and no sample clips. ffmpeg
  resamples it with soxr and dithers it to 16 bits.

At 30,810 Hz, stereo, and 16 bits, the soundtrack is 123,240 bytes per
second and 27.0 MB for its 219 seconds. With the delta blocks, the player
reads about 157,000 bytes per second.

## Building

Building needs CMake 3.28 or newer, Make or Ninja, and
[llvm-mos](https://picocomputer.github.io/sdk.html#sdk-install):

```text
cmake --preset llvm-mos/Release
cmake --build --preset llvm-mos/Release
```

The build unpacks `src/badapple.tar.xz` into the build folder, and writes
the 34 MB ROM to `build/llvm-mos/release/badapple/badapple.rp6502`.

### Encoding the video

Encoding needs Python 3 with numpy, ffmpeg, and
[yt-dlp](https://github.com/yt-dlp/yt-dlp). The source video stays in
`data/`, which Git ignores. Download it, then encode it:

```text
yt-dlp -f "video-h264-360p-1+audio-aac-128kbps" -o "data/sm8628149-512x384.%(ext)s" \
    https://www.nicovideo.jp/watch/sm8628149
python3 src/encode.py data/sm8628149-512x384.mp4
```

The whole video encodes in about two and a half minutes, plus two minutes
the first time to build the tile sets, which the encoder caches in
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
  `build/llvm-mos/release/web/badapple/`, with the 34 MB ROM. The
  RP6502-WEB launch configuration serves it and opens it in a browser.
- **Test.** `ctest --test-dir build/llvm-mos/release` runs the `play`
  test: two seconds in the emulator, which passes when the player finds
  its ROM assets.

Until the release with PCM audio, the emulator and the web player from the
rp6502 CI builds play the sound. Set `RP6502_EMU` and `RP6502_WEB` to their
files, as [Local Files](https://picocomputer.github.io/sdk.html) in the SDK
describes, for example in a `CMakeUserPresets.json`, which Git ignores.

On each push to `main`, `.github/workflows/web.yml` builds the ROM and
publishes the web player at the top of this page to GitHub Pages. The
player starts at the first click on it, with `autoplay: 'off'`, so the
song plays from the beginning. Its picture is the player's screen after
538 VSYNCs, frame 268.

## Updating the tools

`tools/` holds the CMake and Python scripts of the
[RP6502 SDK](https://picocomputer.github.io/sdk.html). Update them with the
"RP6502: update tools" task (Terminal > Run Task), or with:

```text
cmake -P tools/rp6502.cmake
```

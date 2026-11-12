# Bad Apple!! for the Picocomputer 6502

The Bad Apple!! shadow-art video on the
[Picocomputer 6502](https://picocomputer.github.io/), all 6573 frames at
30 fps, as 640x480 black-and-white tiles, with a title screen and a
transport: play and pause, 10-second skips, scrubbing, repeat, and
volume, from a mouse, pen, touchscreen, gamepad, or keyboard.

The soundtrack plays through the PCM audio device of RP6502 0.43 and
later. On older versions the player prints `No PCM device found.` and
stops.

<!-- rp6502
preset: llvm-mos/Release
publish: badapple.zip
frames: 538
-->
[![Bad Apple!!, the title screen](https://rumbledethumps.github.io/badapple/badapple/screenshot.png)](https://rumbledethumps.github.io/badapple/badapple/)

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
- `frames.bin`: a 16-byte header (`BAD5`, the frame count, the first
  source frame, the frame rate, and the length of frame 0's delta block),
  then for each frame its delta block and its sound, 4,108 bytes, as
  described under [The audio](#the-audio). The ROM carries it as the
  named asset `ROM:frames`.
- `index.bin`: for each second, the file offset of its first frame and
  the length of that frame's delta block, 6 bytes, 1.3 KB in all. The ROM
  carries it as `ROM:index`.
- `title.bin`: the title screen, from `src/title.py`, described under
  [The title screen](#the-title-screen). The ROM carries it as
  `ROM:title`.
- `transport.bin`: the transport's palettes and images, from
  `src/transport.py`. The ROM loads it into XRAM before the program
  starts.

A frame's three 80x60 maps, one tile number per byte, are 14,400 bytes,
but few of them change from frame to frame. The player keeps two map
buffers, so the buffer that a frame decodes into still holds the frame two
before it, and the delta block holds only the runs that change it: a
2-byte map offset, a count of 1 to 255, and that many tile numbers, with
gaps of up to four unchanged bytes carried in the run. FF FF ends the
block, which starts with the length of the next frame's block and a flag
byte. The first two frames of each second are keyframes, against cleared
maps, flagged so the player clears the buffer first: playback can start
at any second. The delta blocks average 1,235 bytes a frame, 5,648 at
most, and 8.1 MB in all, against 94.7 MB of maps. With the sound,
`frames.bin` is 35.1 MB.

The archive is 30.0 MB, and Git keeps it, so the build needs no source
video and no encoder. After writing the files, the encoder plays the
stream back the way the player does, into two map buffers, draws the
three planes, and checks that each frame comes out as encoded. It also
writes `preview.mp4` in `data/encoded/`, the encoded frames with the
soundtrack.

## The player

`src/main.c` plays `ROM:frames`:

- **PCM first.** The player opens `PCM:30810,16,2` before anything else.
  When it cannot, it prints `No PCM device found.` and stops.
- **The title screen** shows at start, and again at the end unless repeat
  is on, with the transport over it.
- **A stream ring.** `read_xram()` reads the file into a 16 KB ring in
  XRAM, 4 to 8 KB a read, whenever the ring has room.
- **Decoding in the 6502.** Once a frame's delta block and sound are both
  in the ring, the 6502 applies the runs to the back map buffer:
  `src/copy.s` reads the ring through portal 1 and writes the maps through
  portal 0, eight bytes a pass, about 8.6 cycles a byte. It stops after
  about 256 bytes, so the main loop can check VSYNC between steps. Near
  the end of the ring, where a run could wrap, C applies one run at a
  time. A keyframe's buffer is cleared first, about 1 KB a step.
- **Seeking.** `ROM:index` is read into 6502 RAM at start. To start at a
  second, the player empties the PCM device, moves to that second's place
  in the file, fills the ring, and decodes its keyframe.
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
- **Volume.** Below full volume, `src/copy.s` scales each frame's sound in
  place in the ring before it is sent, about 36 cycles a sample, from
  tables in 6502 RAM: twelve even steps of the level, as a web video
  player's slider has, so the middle is half, -6 dB; and mute.
- **No waiting on calls.** The player starts each API call itself, through
  the RIA registers, and goes on with its loop, decoding and watching
  VSYNC, while the call runs. When `RIA.busy` clears, it takes the result
  and starts the next call.
- **Feeding the device.** Nothing feeds the PCM device during a read, and
  its 4,096-byte buffer plays for 33 ms. So the player fills the device
  before every read, and at every VSYNC.

### The title screen

`src/title.py` sets the credits in Shippori Mincho, antialiased, in 4-bit
tiles on plane 0: black, and white, butter, and lilac in five steps each.
Antialiased type makes about 800 distinct tiles, so plane 0 runs in four
bands of scanlines, each a mode 2 layer with 256 tiles of its own, all
reading one map. The 32 KB of tiles and the map are read over the video's
map buffers and ring, which the title screen does not use, and planes 1
and 2 move off the canvas. The Greek of Μμ is set in Noto Serif, which
Mincho lacks. The fonts are under the SIL Open Font License, and only the
encoder needs them.

### The transport

Gel discs, drawn by `src/transport.py` and shown as mode 5 sprites on the
sprite layer of plane 2, over the video: back 10 seconds, play or pause,
forward 10 seconds, the track with the playhead and the time, repeat, the
speaker, which mutes, and the volume. Each image is drawn large and scaled
down, then set in three tones of its palette, its pastel, charcoal, and
one between them, so its edges are smooth.

| | Mouse, pen, or touch | Gamepad | Keyboard |
|---|---|---|---|
| Play, pause | the play disc | A | Space |
| Back, forward 10 s | the discs | d-pad left, right | left, right arrows |
| Scrub | drag the playhead, or click the track | hold L1 or R1, or the left stick | |
| Repeat | the repeat disc | Y | R |
| Volume | drag the slider | d-pad up, down | up, down arrows |
| Mute | the speaker | X | M |

A click or tap on the video, above the top of the time label, plays and
pauses it, as on a video site, and starts it from the title screen. A
click on the transport does only what it hits. While the video plays, the transport and the
pointer dissolve after 3 seconds without input, or at once when the
pointer leaves the canvas: each palette holds its tones in five ranks of
an ordered dither, and the ranks turn clear one at a time. They come back
at once on any input, which then does nothing else. The emulator and the
web player draw their own pointer; elsewhere the transport draws one, a
black and white desktop arrow.

### Memory

XRAM holds the video's tiles, 6,144 bytes, the two map buffers, 28,800,
and the ring, 16,384, or in their place the title screen's tiles and map,
37,568; the transport's palettes and images, 6,632, and its 25 sprites;
the keyboard, tablet, and gamepad; and the configurations and palettes.

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
reads about 160,000 bytes per second.

## Building

Building needs CMake 3.28 or newer, Make or Ninja, and
[llvm-mos](https://picocomputer.github.io/sdk.html#sdk-install):

```text
cmake --preset llvm-mos/Release
cmake --build --preset llvm-mos/Release
```

The build unpacks `src/badapple.tar.xz` into the build folder, and writes
the 35 MB ROM to `build/llvm-mos/release/badapple/badapple.rp6502`.

### Encoding the video

Encoding needs Python 3 with numpy and Pillow, ffmpeg,
[yt-dlp](https://github.com/yt-dlp/yt-dlp), and, for the title screen and
the transport's digits, the fonts
[Shippori Mincho](https://fonts.google.com/specimen/Shippori+Mincho)
(SemiBold and ExtraBold) and
[Noto Serif](https://fonts.google.com/noto/specimen/Noto+Serif) (the
variable font, `NotoSerif.ttf`) in `data/fonts/`. The source video stays in
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
- **Arguments.** `play` starts the video at once, without the title
  screen, and `repeat` turns repeat on, so `play repeat` loops the video
  with no input. In VS Code they go in `args` of the RP6502-EMU launch
  configuration; for the emulator, after `--`:
  `rp6502-emu badapple.rp6502 -- play repeat`; for the web player, in
  `args` of `rp6502_web()` in `CMakeLists.txt`.
- **Web player.** The build also writes the web player to
  `build/llvm-mos/release/web/badapple/`, with the 35 MB ROM. The
  RP6502-WEB launch configuration serves it and opens it in a browser.
- **Test.** `ctest --test-dir build/llvm-mos/release` runs the `play`
  test: two seconds in the emulator, which passes when the player finds
  its ROM assets.

Until the release with PCM audio, the emulator and the web player from the
rp6502 CI builds play the sound. Set `RP6502_EMU` and `RP6502_WEB` to their
files, as [Local Files](https://picocomputer.github.io/sdk.html) in the SDK
describes, for example in a `CMakeUserPresets.json`, which Git ignores.

On each push to `main`, `.github/workflows/web.yml` builds the ROM and
publishes the web player at the top of this page to GitHub Pages. The ROM
starts when the page loads, on its title screen, with no overlay, and the
browser allows sound at the first click on the player. Its picture is the
title screen, after 538 VSYNCs.

## Updating the tools

`tools/` holds the CMake and Python scripts of the
[RP6502 SDK](https://picocomputer.github.io/sdk.html). Update them with the
"RP6502: update tools" task (Terminal > Run Task), or with:

```text
cmake -P tools/rp6502.cmake
```

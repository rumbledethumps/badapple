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

### Exact tiles

The VGA system draws each frame on three planes of 8x8 1bpp tiles
([mode 2](https://picocomputer.github.io/vga.html)), 80x60 tiles each on
a 640x480 canvas. `src/encode_exact.py` cuts each frame's tiles from its
own pixels, so thin lines, like the broom handle at 2:09, keep every
piece:

1. **Hard edges.** The source is scaled to 640x480 and cut at gray 127 of
   255.
2. **Real gray.** Gray is every source pixel between black and white. A
   square opening drops the gray thinner than it: the antialiasing along a
   hard edge, and in a scene in motion, the motion blur. The opening comes
   from each frame's motion share. Gray that comes and goes, where the
   frame before or after has no gray within 4 pixels, is motion blur; gray
   that stays and is wider than a 6-pixel ramp between black and white is
   shadow. The share is blur over blur plus shadow, averaged over 8
   frames each side so the opening eases between scenes rather than
   flickering: at 32% or less the opening is 2 pixels, so a still scene
   keeps its shadows; at 64% or more it is 16, so a spinning yin-yang is
   drawn sharp; between, in proportion. 56% of frames take 2, 17% take 16.
3. **Dots.** Each pixel of real gray takes one of 17 levels, from its
   brightness with a gamma of 1.6, drawn as a 4x4 ordered dither fixed to
   the screen, so it holds still from frame to frame.

`data/tuner/dither-tuner.html`, built by `data/tuner/make_dither_tuner.py`,
tunes these against the source.

### A cache of tiles

A tile can show from any plane: plane 0 is opaque black under it, and
black is clear on planes 1 and 2. So the three planes are one cache of
765 tiles, 255 each after the empty tile 0, and the stream uploads tiles
into it as frames need them. The encoder plans the cache with the whole
video in view:

- **Two frames at once.** While a frame loads, the one before it is on
  screen, so their tiles must fit in the 765 slots together, and no frame
  takes more than 700. Where two frames need more, the later keeps its
  tiles in common with the earlier and its most used new ones; the rest
  show the nearest kept tile, counting a border pixel four times, because
  a step in an outline where two tiles meet is easy to see. That is 44,142
  of the video's 31.5 million cells, 0.14%.
- **Belady's rule.** A new tile takes the slot whose tile is needed again
  furthest in the future, or never, and never a slot of the frame on
  screen or the frame loading.
- **Uploading ahead.** The encoder plans the stream twice. Frames that
  would cost the 6502 more than 60,000 cycles to decode then have some of
  their tiles uploaded in cheaper frames before them.

Frames upload 107 tiles each on average, and the 6502's estimated decoding
time is 40,800 cycles in an average frame and 121,000 in the worst, of the
266,667 a frame has at 8 MHz.

### The stream

Every write in the stream is to an XRAM address: the tiles at 0, the two
map buffers from 6144, frame n in buffer n % 2. The player does what the
stream says. The buffer a frame loads into still holds the frame two
before it, so a frame's maps are only the runs that change it.

`src/encode_exact.py` writes these, and packs them into
`src/badapple.tar.xz` for the build:

- `frames.bin`: a 16-byte header (`BAD8`, the frame count, the first
  source frame, the frame rate, and the length of frame 0's block), then
  for each frame its block and its sound, 1,064 bytes of 4-bit DPCM, as
  described under [The audio](#the-audio). A block is the length of the next block, a flag
  byte, then writes of a 2-byte address, a count of 1 to 255, and that
  many bytes, joining writes up to four bytes apart, then FF FF. Blocks
  average 2,890 bytes; `frames.bin` is 26.0 MB. The ROM carries it as
  `ROM:frames`.
- `seek.bin`: for each second, what the stream expects in XRAM when that
  second starts, every tile slot and both map buffers, in parts of up to
  8 KB. Playback never reads it; a seek, and the start, do. 2.7 MB, as
  `ROM:seek`.
- `index.bin`: for each second, where it starts in `frames.bin` and in
  `seek.bin`, 12 bytes, 2.6 KB in all, as `ROM:index`.
- `title.bin`: the title screen, from `src/title.py`, described under
  [The title screen](#the-title-screen), as `ROM:title`.
- `transport.bin`: the transport's palettes and images, from
  `src/transport.py`. The ROM loads it into XRAM before the program
  starts.

The archive is 17.1 MB, and Git keeps it, so the build needs no source
video and no encoder. After writing the files, the encoder plays the
stream back into a model of XRAM, from the start and from every second's
seek record, and checks every frame. `src/encode.py`, the earlier
encoder, which drew a fixed set of 511 marching-squares tiles, keeps the
helpers that `src/encode_exact.py` shares.

## The player

`src/main.c` plays `ROM:frames`:

- **PCM first.** The player opens `PCM:30810,16,2` before anything else.
  When it cannot, it prints `No PCM device found.` and stops.
- **The title screen** shows at start, and again at the end unless repeat
  is on, with the transport over it.
- **A stream ring.** `read_xram()` reads the file into a 16 KB ring in
  XRAM, 1 to 8 KB a read, whenever the ring has room.
- **Decoding in the 6502.** Once a frame's block and sound are both in
  the ring, the 6502 does the block's writes, at the addresses it gives: `src/copy.s` reads the
  ring through portal 1 and writes through portal 0, eight bytes a pass,
  about 8.6 cycles a byte. It stops after about 256 bytes, so the main
  loop can check VSYNC between steps. Near the end of the ring, where a
  run could wrap, C applies one run at a time. The tiles are cleared at
  start, so tile 0 of each plane is empty.
- **Seeking.** `ROM:index` is read into 6502 RAM at start. To start at a
  second, the player empties the PCM device, clears both map buffers,
  reads that second's seek record in parts and does its writes, then
  moves to its place in `ROM:frames`, fills the ring, and decodes its
  first frame.
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
- **Sound.** A second decoder walks the stream on its own, a frame's
  sound at a time, as soon as the frame is all in the ring, so a busy
  video frame never holds the sound back. `src/copy.s` decodes the 4-bit
  DPCM through the portals, from the ring into the stage, a 4 KB ring of
  16-bit samples in XRAM, about 69 cycles a stereo pair, 71,000 a frame;
  `write_xram()` sends the stage to the PCM device. Each code byte indexes
  tables in 6502 RAM, 16 KB, that give both channels' deltas; the loop
  keeps its running samples in its own operands.
- **Volume.** The tables hold the deltas at the volume, so turning it
  down costs nothing while playing: twelve even steps of the level, as a
  web video player's slider has, so the middle is half, -6 dB; and mute.
  A change takes effect at the start of the next frame's sound, where the
  samples start again from the frame's start samples, so they stay in 16
  bits; filling the tables takes about 100,000 cycles, a scale a pass of
  the main loop.
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
at once on any input, which also does what it asks. The emulator and the
web player draw their own pointer; elsewhere the transport draws one, a
black and white desktop arrow.

### Memory

XRAM holds the video's tiles, 6,144 bytes, the two map buffers, 28,800,
and the ring, 16,384, or in their place the title screen's tiles and map,
37,568; the transport's palettes and images, 6,632, and its 25 sprites;
the keyboard, tablet, and gamepad; and the configurations and palettes.

## The audio

The soundtrack is the audio of the same Niconico upload: AAC-LC, 44.1 kHz,
stereo, about 113 kbps. The player plays it at **30,810 Hz,
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

At 30,810 Hz, stereo, and 16 bits, the soundtrack would be 123,240 bytes
per second, 27.0 MB for its 219 seconds. The stream carries it as 4-bit
DPCM, which the 6502 decodes with a table lookup and a 16-bit add a
sample:

- **The format.** Each frame's sound is 1,064 bytes: the left and right
  samples it starts from, 16 bits each, then 33 blocks of 32 pairs, the
  last of 3. A block is a byte of the two channels' scales, 4 bits each,
  then a byte a pair, the left code in the high 4 bits. A sample is the
  one before it plus (code - 8) times the scale's step, 16 steps from 4 to
  4,095, evenly spaced in decibels. The encoder never lets a sum leave 16
  bits, so the decoder needs no clamp. 31,920 bytes per second, a quarter
  of the PCM, and 7.0 MB in all.
- **The encoder.** `src/adpcm.c`, which `src/encode_exact.py` compiles and
  runs, picks each block's scale and codes together: the two scales that
  do best on a quick greedy pass are tried with a trellis that keeps 16
  paths.
- **The noise.** The error is about 30 dB under the music, a hiss spread
  evenly over frequency, so it is lowest against the music's strong bass
  and highest against the quiet treble. `--shaping` feeds the error back
  to move the noise out of the treble, but it lands at 1 to 4 kHz, where
  the ear is most sensitive, so the default is 0.

With the delta blocks, the player reads about 119,000 bytes per second.

## Building

Building needs CMake 3.28 or newer, Make or Ninja, and
[llvm-mos](https://picocomputer.github.io/sdk.html#sdk-install):

```text
cmake --preset llvm-mos/Release
cmake --build --preset llvm-mos/Release
```

The build unpacks `src/badapple.tar.xz` into the build folder, and writes
the 29 MB ROM to `build/llvm-mos/release/badapple/badapple.rp6502`.

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
python3 src/encode_exact.py data/sm8628149-512x384.mp4
```

The whole video encodes in about six and a half minutes, half of it the
sound, plus the playback check.
The encoder writes `src/badapple.tar.xz`, and
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
  `build/llvm-mos/release/web/badapple/`, with the 29 MB ROM. The
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

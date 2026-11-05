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

## Later steps (to be defined)

- Audio playback, when the PCM emulator and documentation arrive.

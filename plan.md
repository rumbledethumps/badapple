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

### The audio

What we need is a 3:39 FM version of the **Alstroemeria Records
arrangement**, the song the PV was animated to, so that it stays in sync
with the video.

- **The PV's soundtrack** is that arrangement: a produced vocal recording,
  3:39 long. The OPL2 cannot play a recording, so we need a cover of it
  arranged for FM. The AAC track in `data/` is the reference for timing
  and sync.
- **ZUN's 1998 original does not fit.** It is a different, shorter piece:
  the instrumental Stage 3 music of the game, reported at about 161 BPM
  and 1:22 long, which the game loops. The arrangement shares its melody,
  but not its structure, length, or timing. The original matters for the
  credits, not as a soundtrack. (For the record, it is PC-98 FM: YM2203 or
  YM2608, both 4-operator, per
  [TCRF](https://new.tcrf.net/Proto:Touhou_Gensoukyou:_Lotus_Land_Story).)
- **No OPL2 or AdLib cover found.** The DOS ports play digitized sound:
  8088 Domination (Trixter, 2014) uses Sound Blaster PCM
  ([blog](https://trixter.oldskool.org/2014/06/17/8088-domination)), and
  Abaduaber's 2013 DOS port offers PC speaker, Sound Blaster, or Covox,
  with sound code by Alexander Peslyak (from the strings of its data
  file, [BadAppleJS](https://github.com/sairoutine/BadAppleJS)). The
  Bad Apple music on [Demozoo](https://demozoo.org/search/?q=bad+apple) is
  SID, POKEY, AY, SN76489, SAA1099, and MOD, with no FM.

**FM covers of the arrangement found:**

| Port | Chips | Music by | Status |
|---|---|---|---|
| MSX, MDPC, 2023, [`sm41761403`](https://www.nicovideo.jp/watch/sm41761403) | PSG + FM (MSX-MUSIC, YM2413 OPLL, to confirm), plus vocals as FM speech synthesis | aro | ROM available from [File Hunter](https://www.file-hunter.com/Homebrew/index.php?id=badapple). It holds the music as an MGS file titled "BAD APPLE!!", played by MGSDRV 3.20. |
| Mega Drive, Mt.Chocolate (Future Driver), 2011, [`sm15708149`](https://www.nicovideo.jp/watch/sm15708149) | YM2612 FM + PSG | not stated; tagged as a self-made arrangement | Downloads were on Hotfile, which is gone ([page](http://68000.web.fc2.com/bad_apple.html), `apple_0.07.zip`). A later version sings through CSM speech synthesis from data the author was given ([`sm15762201`](https://www.nicovideo.jp/watch/sm15762201)). |

**Ruled out.** Both covers need FM and a PSG at the same time, and the
RP6502 maps either its PSG or its OPL2, not both. Fitting them onto the
OPL2 alone is too much work.
- **MIDI transcriptions of the arrangement exist.** They are the likely
  input for an OPL2 version:
  - [MuseScore score 678091](https://musescore.com/user/1467236/scores/678091),
    uploaded by livingston26 and credited to cherry_berry17. espbadapple
    used a modified copy, with a percussion track added by binary1230.
  - [MidiShow 188734](https://midishow.com/en/midi/bad-apple-midi-download-188734),
    a General MIDI version uploaded by ndxggm.

**Audio options, in order:**
1. Find an existing FM cover of the arrangement (OPL2 or OPL3, YM2413, or
   YM2612) by another artist that we can credit and adapt.
2. Convert a MIDI transcription of the arrangement to OPL2 ourselves,
   crediting the transcriber.

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
- [x] Search further for an existing FM or OPL cover of the arrangement,
      and its author.
- [ ] Decide on the audio source.

## Later steps (to be defined)

- Video encoder and decoder. One idea is to treat the video as a 3D
  volume, use marching cubes over x, y, and t, and slice it per frame. It
  is noted here as one option, not a commitment.
- Audio on the OPL2.

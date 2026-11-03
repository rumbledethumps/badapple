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
| 2008-06-08 | Storyboard of a shadow-art PV posted to Niconico, asking someone to animate it | Μμ |
| 2009-10-26/27 | The finished shadow-art PV, Niconico `sm8628149`. Sources give both dates. | Anira (あにら) and team |
| 2009-10-28 | Official PV upload by the label | Alstroemeria Records |

Sources: [Wikipedia: Bad Apple!!](https://en.wikipedia.org/wiki/Bad_Apple!!),
[Bilibili article on the PV's history](https://www.bilibili.com/read/cv3839234/),
[Niconico dictionary](https://dic.nicovideo.jp/a/bad%20apple%21%21%20feat.%20nomico).

Fan use: ZUN's guidelines allow derivative works without prior permission
if they follow the guidelines: attribution, no unauthorized commercial
distribution, and no crowdfunding (Wikipedia, citing the guidelines). We
need to read ZUN's guidelines ourselves, and check Alstroemeria Records'
position on fan use of the arrangement and the PV.

### The video

| Property | Value | Confidence |
|---|---|---|
| Resolution | 512x384 (4:3) | UNVERIFIED, from [espbadapple](https://github.com/cnlohr/espbadapple) and a [Minecraft port write-up](https://purplesyringa.moe/blog/we-built-the-best-bad-apple-in-minecraft/) |
| Frame rate | 30 fps | UNVERIFIED, from [Gigazine](https://gigazine.net/gsc_news/en/20240313-bad-apple-animation-font) |
| Duration | 3:39 | several sources |
| Frame count | 6570 ([espbadapple](https://github.com/cnlohr/espbadapple)); 6572 is also widely cited | UNVERIFIED |
| Color | Black-and-white shadow art, with gray at the edges in the encode | to check |

We need the original file to settle these. `ffprobe` on it gives the
exact numbers.

**Where to get it** (candidates, closest to the original first):

1. Niconico `sm8628149`, Anira's original upload. It may need an account
   to download.
2. The Alstroemeria Records official upload of 2009-10-28.
3. Re-uploads and archives, such as YouTube and archive.org. These are
   often re-encoded at 480x360, so they come last.

### The audio

- **The PV's soundtrack** is the Alstroemeria Records vocal arrangement,
  a produced recording. The OPL2 cannot play it as recorded, so playing it
  means a cover arranged for FM.
- **ZUN's original** is FM chip music on the PC-98, at about 161 BPM, and
  runs 1:22. It is not the PV's arrangement or length, so it cannot
  accompany the video as it stands. Lotus Land Story supports the
  PC-9801-26K board (YM2203, OPN) and the PC-9801-86 board (YM2608, OPNA).
  Both are 4-operator FM. The OPL2 is 2-operator, so a conversion means
  re-voicing the instruments, not copying the registers.
  ([TCRF](https://new.tcrf.net/Proto:Touhou_Gensoukyou:_Lotus_Land_Story),
  [vgmrips listing](https://vgmrips.net/packs/topic/2614))
- **No OPL2 or AdLib arrangement found yet.**
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
3. Convert ZUN's original FM track. It is authentic, but it does not match
   the video.

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

- [ ] Get the original video and record its exact resolution, frame rate,
      frame count, and duration with `ffprobe`.
- [ ] Read ZUN's derivative-work guidelines. Look for Alstroemeria
      Records' terms on fan use.
- [ ] Search further for an existing FM or OPL cover of the arrangement,
      and its author.
- [ ] Decide on the audio source.

## Later steps (to be defined)

- Video encoder and decoder. One idea is to treat the video as a 3D
  volume, use marching cubes over x, y, and t, and slice it per frame. It
  is noted here as one option, not a commitment.
- Audio on the OPL2.

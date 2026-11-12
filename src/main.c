#include <rp6502.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include "transport.h"
#include "xram.h"

/* Plays ROM:frames, made by src/encode.py.
 *
 * It starts on the title screen, ROM:title, and waits. A click on the
 * video, above the transport, plays and pauses it, and starts it from the
 * title screen; the transport's controls do what they say: Space plays and
 * pauses, the arrows go back and forward 10 seconds, R turns repeat on and
 * off. At the end the title screen comes back, or with repeat on, the
 * video plays again.
 *
 * The file streams into a 16 KB ring in XRAM, in reads of 4 to 8 KB. Each
 * frame in it is a delta block, then the frame's sound. A delta block holds
 * the runs that turn the maps of two frames back, which its buffer still
 * holds, into this frame's maps. The first two frames of each second are
 * keyframes, against cleared maps, and ROM:index, read into RAM, gives
 * each second's place in the file, so the player can start at any second.
 * The 6502 applies the runs, a step per pass of the main loop, while the
 * next read runs. The sound goes from the ring to the PCM device in order.
 *
 * Two map buffers hold the frame on screen and the next frame, decoding or
 * decoded. A frame is shown by pointing all three layers at its maps, at a
 * VSYNC, so it doesn't tear. A 30 fps frame lasts two 60 Hz VSYNCs. A frame
 * that isn't decoded by its VSYNC is shown at the next one.
 *
 * The main loop never waits for an API call. It starts one, then goes on
 * counting VSYNCs, showing frames, and decoding until RIA.busy clears. Then
 * it takes the result and starts the next call. Nothing feeds the PCM
 * device during a read, and its 4,096 bytes play for 33 ms, so the device
 * is filled before every read, and at every VSYNC. */

#define HEADER_BYTES 16
#define FPS 30
#define VSYNCS_PER_FRAME 2
#define AHEAD (BUFFERS - 1) /* frames decoded ahead of the one on screen */
#define READ_MIN 4096
#define READ_MAX 8192
#define SKIP_SECONDS 10
#define MAX_SECONDS 256
#define KEYFRAME 1 /* a delta block's flag: clear the buffer first */
#define SCALE_SAMPLES 128 /* samples a step of the volume scaler takes */
#define IDLE_VSYNCS 180   /* 3 s without input while playing, then the transport fades */
#define FADE_VSYNCS 6     /* between steps of the fade */
#define FADE_STEPS 5
#define SCRUB_VSYNCS 8    /* between seconds of a held scrub */

enum
{
    CALL_NONE,
    CALL_PCM,
    CALL_READ,
};

enum
{
    SHOW_TITLE, /* the title screen, before the video */
    SHOW_PLAY,
    SHOW_PAUSE,
};

static int frames_fd, pcm_fd;
static unsigned frames, seconds;
static struct
{
    uint32_t offset; /* the file position of the second's first frame */
    unsigned block;  /* the length of its delta block */
} second_at[MAX_SECONDS];

static uint8_t show_state;
static bool repeat;

static uint8_t vsync;  /* the last VSYNC counted */
static uint8_t ticks;  /* VSYNCs since the last frame was shown */
static uint8_t front;  /* the buffer on screen */
static uint8_t ahead;  /* frames decoded in the buffer after it */
static unsigned next;  /* the next frame to show */
static uint8_t load;   /* the buffer that frame next + ahead decodes into */

/* Positions in the stream count up and wrap at 64K. A byte's place in the
 * ring is its position & RING_MASK. */
static unsigned head;        /* bytes read into the ring */
static bool stream_end;      /* ROM:frames has no more */
static unsigned parse;       /* the next byte to decode */
static unsigned block;       /* the length of the next delta block */
static unsigned next_block;  /* the length of the one after it */
static bool decoding;        /* a delta block is being applied */
static unsigned clear_left;  /* groups of 8 bytes of a keyframe's buffer still to clear */
static unsigned clear_at;    /* the XRAM address of the next group */
static uint8_t run_left;     /* bytes left in a run that wraps the ring */
static unsigned run_to;      /* the XRAM address they go to */

/* In copy.s, for decode_runs(). */
extern unsigned dec_map;  /* the XRAM address of the maps being decoded */
extern uint8_t dec_limit; /* the first page of the ring where a run might wrap */

/* The volume, VOLUME_M[step] of 256: twelve even steps of the level, as a
 * web video player's slider has, so the middle is half, -6 dB. */
static const uint16_t VOLUME_M[] = {0, 21, 43, 64, 85, 107, 128, 149, 171, 192, 213, 235, 256};
#define VOLUME_FULL (sizeof(VOLUME_M) / sizeof(VOLUME_M[0]) - 1)
static uint8_t volume = VOLUME_FULL;
static bool muted;
static bool scaling; /* below full volume, each frame's sound is scaled before it is sent */
extern uint8_t vol_lo[256], vol_hl[256], vol_hh[256]; /* copy.s */

static unsigned sound_len[BUFFERS];   /* bytes of each buffer's sound still to send, 0 when sent */
static unsigned sound_ready[BUFFERS]; /* bytes of it scaled to the volume, ready to send */
static unsigned sound_at[BUFFERS];  /* where it starts in the stream */
static uint8_t sound_play;          /* the buffer whose sound goes to the PCM device */
static unsigned sound_sent;         /* bytes of its sound already sent */
static unsigned pcm_asked;          /* bytes the PCM write in flight was given */
static bool pcm_full;               /* a PCM write filled the device since the last read or VSYNC */

static uint8_t call;

static uint8_t keys_last[11]; /* the keyboard's first 11 bytes, at the last VSYNC */
static uint8_t pad_last[4];   /* the gamepad's dpad, sticks, btn0, btn1, at the last VSYNC */
static uint8_t tablet_last;   /* the pointer's buttons, at the last VSYNC */
static int pointer_x = -1, pointer_y; /* -1 until the pointer first moves */
static bool pointer_in;   /* over the canvas: a mouse, or a pen in range */
static bool host_cursor;  /* the emulator or web player draws the pointer */
static uint8_t cursor;    /* the host's pointer as last set: TABLET_CURSOR_ */

static uint8_t idle;      /* VSYNCs without input, while playing */
static uint8_t fade_step; /* 0 shown, FADE_STEPS hidden */
static uint8_t fade_wait;

enum
{
    DRAG_NONE,
    DRAG_TRACK,
    DRAG_VOLUME,
};
static uint8_t drag;
static uint8_t scrub_from;  /* the state before a scrub, to go back to */
static uint8_t scrub_wait;  /* VSYNCs to the next second of a held scrub */

/* What the inputs ask for. */
enum
{
    ACT_NONE,
    ACT_PLAY,     /* play or pause */
    ACT_BACK,
    ACT_FORWARD,
    ACT_REPEAT,
    ACT_MUTE,
    ACT_LOUDER,
    ACT_QUIETER,
};

void copy_run(uint8_t count);     /* copy.s */
void clear_groups(uint8_t count); /* copy.s */
uint8_t decode_runs(void);        /* copy.s */
void scale_samples(uint8_t count); /* copy.s */

static uint8_t after(uint8_t buffer)
{
    return buffer == BUFFERS - 1 ? 0 : buffer + 1;
}

static unsigned maps_of(uint8_t buffer)
{
    return XRAM_MAPS + buffer * FRAME_BYTES;
}

static void show(uint8_t buffer)
{
    unsigned maps = maps_of(buffer);
    uint8_t layer;
    for (layer = 0; layer < LAYERS; layer++)
        xram0_poke16(XRAM_CONFIG + layer * sizeof(mode2_config_t) +
                         offsetof(mode2_config_t, xram_data_ptr),
                     maps + layer * MAP_BYTES);
}

static uint8_t ring_get(void)
{
    RIA.step1 = 1;
    RIA.addr1 = XRAM_RING + (parse & RING_MASK);
    ++parse;
    return RIA.rw1;
}

/* The oldest byte in the ring still needed: unsent sound, or undecoded. */
static unsigned ring_tail(void)
{
    return sound_len[sound_play] ? sound_at[sound_play] + sound_sent : parse;
}

static void finish_frame(void)
{
    sound_at[load] = parse;
    sound_len[load] = SOUND_BYTES;
    sound_ready[load] = scaling ? 0 : SOUND_BYTES;
    parse += SOUND_BYTES;
    block = next_block;
    load = after(load);
    ++ahead;
    decoding = false;
}

/* One step of decoding: start the next frame's delta block once it and its
 * sound are all in the ring, clear its buffer if it is a keyframe, about
 * 1 KB a step, then apply its runs, about 256 bytes a step, in
 * decode_runs(). Near the ring's end, where a run might wrap, this applies
 * one run at a time itself. */
static void decode_step(void)
{
    uint8_t lo, hi, n;
    unsigned to_end, start;
    if (!decoding)
    {
        if (ahead >= AHEAD || next + ahead >= frames || sound_len[load] ||
            (unsigned)(head - parse) < block + SOUND_BYTES)
            return;
        lo = ring_get();
        hi = ring_get();
        next_block = lo | hi << 8;
        dec_map = maps_of(load);
        if (ring_get() & KEYFRAME)
        {
            clear_left = FRAME_BYTES / 8;
            clear_at = dec_map;
        }
        decoding = true;
        run_left = 0;
    }
    if (clear_left)
    {
        n = clear_left < 128 ? clear_left : 128;
        RIA.step0 = 1;
        RIA.addr0 = clear_at;
        clear_groups(n);
        clear_at += n * 8;
        clear_left -= n;
        return;
    }
    to_end = RING_BYTES - (parse & RING_MASK);
    start = XRAM_RING + (parse & RING_MASK);
    if (!run_left && (uint8_t)(start >> 8) < dec_limit)
    {
        RIA.step0 = 1;
        RIA.step1 = 1;
        RIA.addr1 = start;
        n = decode_runs();
        parse += RIA.addr1 - start;
        if (n == 1)
            finish_frame();
        return;
    }
    if (!run_left)
    {
        lo = ring_get();
        hi = ring_get();
        if (lo == 0xFF && hi == 0xFF)
        {
            finish_frame();
            return;
        }
        run_to = dec_map + (lo | hi << 8);
        run_left = ring_get();
        to_end = RING_BYTES - (parse & RING_MASK);
    }
    n = run_left;
    if (n > to_end)
        n = to_end;
    RIA.step0 = 1;
    RIA.addr0 = run_to;
    RIA.step1 = 1;
    RIA.addr1 = XRAM_RING + (parse & RING_MASK);
    copy_run(n);
    run_to += n;
    parse += n;
    run_left -= n;
}

/* Sets the volume tables for the step and mute. At full volume nothing is
 * scaled, and sound already waiting goes as it is. */
static void set_volume(void)
{
    unsigned m = muted ? 0 : VOLUME_M[volume], i;
    int hi;
    for (i = 0; i < 256; i++)
    {
        hi = (int8_t)i * (int)m;
        vol_lo[i] = (uint8_t)((i * m) >> 8);
        vol_hl[i] = (uint8_t)hi;
        vol_hh[i] = (uint8_t)(hi >> 8);
    }
    scaling = m != 256;
    if (!scaling)
        sound_ready[0] = sound_ready[1] = SOUND_BYTES;
}

/* One step of the volume scaler: up to SCALE_SAMPLES samples of the oldest
 * sound not yet scaled, in place in the ring. A sample split by the ring's
 * end is scaled here in C. */
static void scale_step(void)
{
    uint8_t b = sound_play, lo, hi;
    unsigned pos, left, to_end, n;
    int v;
    if (!sound_len[b] || sound_ready[b] >= SOUND_BYTES)
    {
        b = after(b);
        if (!sound_len[b] || sound_ready[b] >= SOUND_BYTES)
            return;
    }
    pos = sound_at[b] + sound_ready[b];
    left = SOUND_BYTES - sound_ready[b];
    to_end = RING_BYTES - (pos & RING_MASK);
    if (to_end == 1)
    {
        lo = xram0_peek8(XRAM_RING + RING_MASK);
        hi = xram0_peek8(XRAM_RING);
        v = vol_lo[lo] + (vol_hl[hi] | vol_hh[hi] << 8);
        xram0_poke8(XRAM_RING + RING_MASK, v);
        xram0_poke8(XRAM_RING, v >> 8);
        sound_ready[b] += 2;
        return;
    }
    n = left < to_end ? left : to_end;
    n /= 2;
    if (n > SCALE_SAMPLES)
        n = SCALE_SAMPLES;
    RIA.step0 = 1;
    RIA.step1 = 1;
    RIA.addr0 = RIA.addr1 = XRAM_RING + (pos & RING_MASK);
    scale_samples(n);
    sound_ready[b] += n * 2;
}

/* Starts read_xram() or write_xram() without waiting for it. */
static void start_call(uint8_t kind, uint8_t op, unsigned xaddr, unsigned count, int fd)
{
    RIA.xstack = xaddr >> 8;
    RIA.xstack = xaddr;
    RIA.xstack = count >> 8;
    RIA.xstack = count;
    RIA.a = fd;
    RIA.op = op;
    call = kind;
}

/* The part of the playing sound that is in one piece in the ring. */
static unsigned sound_piece(unsigned *at)
{
    unsigned start = sound_at[sound_play] + sound_sent, left = sound_ready[sound_play] - sound_sent,
             to_end = RING_BYTES - (start & RING_MASK);
    *at = XRAM_RING + (start & RING_MASK);
    return left < to_end ? left : to_end;
}

static void sound_done(int n)
{
    if (n > 0 && (sound_sent += n) >= sound_len[sound_play])
    {
        sound_len[sound_play] = 0;
        sound_play = after(sound_play);
        sound_sent = 0;
    }
}

static void finish_call(void)
{
    int n = RIA.a | RIA.x << 8;
    switch (call)
    {
    case CALL_PCM:
        /* A write that takes less than it was given filled the device. */
        if (n < (int)pcm_asked)
            pcm_full = true;
        sound_done(n);
        break;
    case CALL_READ:
        if (n > 0)
            head += n;
        else
            stream_end = true;
        pcm_full = false;
        break;
    }
    call = CALL_NONE;
}

/* Waits for the call in flight, if any, and takes its result. */
static void finish_calls(void)
{
    while (RIA.busy & 0x80)
        ;
    if (call != CALL_NONE)
        finish_call();
}

/* While playing, fills the PCM device; then reads 4 to 8 KB into the ring
 * when it has room. */
static void start_next_call(void)
{
    unsigned at, count, space;
    if (show_state == SHOW_PLAY && !pcm_full && sound_len[sound_play] &&
        sound_ready[sound_play] > sound_sent)
    {
        pcm_asked = sound_piece(&at);
        start_call(CALL_PCM, RIA_OP_WRITE_XRAM, at, pcm_asked, pcm_fd);
        return;
    }
    space = RING_BYTES - (unsigned)(head - ring_tail());
    if (stream_end || space < READ_MIN)
        return;
    count = RING_BYTES - (head & RING_MASK);
    if (count > space)
        count = space;
    if (count > READ_MAX)
        count = READ_MAX;
    start_call(CALL_READ, RIA_OP_READ_XRAM, XRAM_RING + (head & RING_MASK), count, frames_fd);
}

/* Shows the video's three planes, after the title screen. */
static void video_planes(void)
{
    uint8_t layer;
    for (layer = 0; layer < LAYERS; layer++)
    {
        xram0_poke16(XRAM_CONFIG + layer * sizeof(mode2_config_t) + offsetof(mode2_config_t, y_pos_px), 0);
        xreg_vga_mode2(MODE2_1BPP | MODE2_8X8, XRAM_CONFIG + layer * sizeof(mode2_config_t), layer, 0, 0);
    }
}

/* Starts the video at the start of a second, playing or paused there:
 * empties the PCM device, fills the ring from that second's place in the
 * file, and decodes its first frame, a keyframe, then shows it at a
 * VSYNC. */
static bool start_at(unsigned second, uint8_t state)
{
    uint8_t band;
    finish_calls();
    lseek(pcm_fd, 0, SEEK_SET);
    /* The ring and map buffers hold the title screen; hide it first. */
    if (show_state == SHOW_TITLE)
        for (band = 0; band < TITLE_BANDS; band++)
            xram0_poke16(XRAM_TITLE_CONFIG + band * sizeof(mode2_config_t) + offsetof(mode2_config_t, y_pos_px),
                         480);
    if (lseek(frames_fd, second_at[second].offset, SEEK_SET) < 0)
        return false;
    head = parse = 0;
    stream_end = false;
    while (head < RING_BYTES)
    {
        int n = read_xram(XRAM_RING + head, RING_BYTES - head < READ_MAX ? RING_BYTES - head : READ_MAX,
                          frames_fd);
        if (n <= 0)
        {
            stream_end = true;
            break;
        }
        head += n;
    }
    sound_len[0] = sound_len[1] = 0;
    block = second_at[second].block;
    decoding = false;
    clear_left = 0;
    front = load;
    ahead = 0;
    next = second * FPS;
    while (!ahead)
    {
        if (!decoding && (unsigned)(head - parse) < block + SOUND_BYTES)
            return false;
        decode_step();
    }
    ahead = 0;
    ++next;
    sound_play = front;
    sound_sent = 0;
    pcm_full = false;
    vsync = ria_vsync();
    while (ria_vsync() == vsync)
        ;
    ++vsync;
    show(front);
    if (show_state == SHOW_TITLE)
        video_planes();
    show_state = state;
    ticks = 0;
    return true;
}

/* Shows the title screen: reads ROM:title over the map buffers and ring,
 * runs plane 0 in its bands of 4-bit tiles, and moves planes 1 and 2 off
 * the canvas. */
static bool show_title(void)
{
    uint8_t header[HEADER_BYTES], band, bands;
    unsigned half;
    mode2_config_t config;
    int fd;
    finish_calls();
    lseek(pcm_fd, 0, SEEK_SET);
    fd = open("ROM:title", O_RDONLY);
    if (fd < 0 || read(fd, header, HEADER_BYTES) != HEADER_BYTES || header[0] != 'T' || header[3] != '1')
        return false;
    bands = header[4];
    half = bands * 256u * TITLE_TILE_BYTES / 2;
    if (bands > TITLE_BANDS || read_xram(XRAM_TITLE_PALETTE, 32, fd) != 32 ||
        read_xram(XRAM_TITLE_TILES, half, fd) != (int)half ||
        read_xram(XRAM_TITLE_TILES + half, half, fd) != (int)half ||
        read_xram(XRAM_TITLE_MAP, MAP_BYTES, fd) != MAP_BYTES)
        return false;
    close(fd);
    for (band = 1; band < LAYERS; band++)
        xram0_poke16(XRAM_CONFIG + band * sizeof(mode2_config_t) + offsetof(mode2_config_t, y_pos_px), 480);
    for (band = 0; band < bands; band++)
    {
        config = (mode2_config_t){
            .width_tiles = MAP_COLS,
            .height_tiles = MAP_ROWS,
            .xram_data_ptr = XRAM_TITLE_MAP,
            .xram_palette_ptr = XRAM_TITLE_PALETTE,
            .xram_tile_ptr = XRAM_TITLE_TILES + band * 256u * TITLE_TILE_BYTES,
        };
        xram0_write(XRAM_TITLE_CONFIG + band * sizeof(mode2_config_t), &config, sizeof(config));
        xreg_vga_mode2(MODE2_4BPP | MODE2_8X8, XRAM_TITLE_CONFIG + band * sizeof(mode2_config_t), 0,
                       header[5 + band] * 8, band + 1 < bands ? header[6 + band] * 8 : 0);
    }
    show_state = SHOW_TITLE;
    return true;
}

/* Sends what is left of the sound, lets it play, then plays again with
 * repeat on, or shows the title screen. */
static bool end_video(void)
{
    unsigned at, count;
    finish_calls();
    while (sound_len[sound_play])
    {
        int n;
        if (sound_ready[sound_play] <= sound_sent)
        {
            scale_step();
            continue;
        }
        count = sound_piece(&at);
        n = write_xram(at, count, pcm_fd);
        if (n < 0)
            break;
        sound_done(n);
    }
    syncfs(pcm_fd);
    return repeat ? start_at(0, SHOW_PLAY) : show_title();
}

/* Goes back or forward by whole seconds, from the second on screen, or
 * from 0:00 on the title screen. */
static bool skip(int by)
{
    int second = show_state == SHOW_TITLE ? 0 : (int)((next - 1) / FPS);
    second += by;
    if (second < 0)
        second = 0;
    if (second >= (int)seconds)
        second = seconds - 1;
    return start_at(second, show_state == SHOW_PLAY ? SHOW_PLAY : SHOW_PAUSE);
}

static void play_pause(void)
{
    if (show_state == SHOW_PLAY)
        show_state = SHOW_PAUSE;
    else
    {
        show_state = SHOW_PLAY;
        ticks = 0;
    }
}

static void change_volume(int by)
{
    if (by > 0 && volume < VOLUME_FULL)
        ++volume;
    if (by < 0 && volume)
        --volume;
    muted = false;
    set_volume();
}

/* Does what an input asks. */
static bool act(uint8_t action)
{
    switch (action)
    {
    case ACT_PLAY:
        if (show_state == SHOW_TITLE)
            return start_at(0, SHOW_PLAY);
        play_pause();
        break;
    case ACT_BACK:
        if (show_state != SHOW_TITLE)
            return skip(-SKIP_SECONDS);
        break;
    case ACT_FORWARD:
        return skip(SKIP_SECONDS);
    case ACT_REPEAT:
        repeat = !repeat;
        break;
    case ACT_MUTE:
        muted = !muted;
        set_volume();
        break;
    case ACT_LOUDER:
        change_volume(1);
        break;
    case ACT_QUIETER:
        change_volume(-1);
        break;
    }
    return true;
}

/* Any input shows the faded transport at once, and still does what it
 * asks. */
static void wake(void)
{
    idle = 0;
    if (fade_step)
    {
        fade_step = 0;
        transport_fade(0);
    }
}

static bool key_down(const uint8_t *keys, uint8_t code)
{
    return KEYBOARD_PRESSED(keys, code) && !KEYBOARD_PRESSED(keys_last, code);
}

/* The keyboard: the action of the first key that went down. */
static uint8_t keyboard(void)
{
    static const uint8_t KEYS[][2] = {
        {HID_KEY_SPACE, ACT_PLAY},         {HID_KEY_ARROW_LEFT, ACT_BACK}, {HID_KEY_ARROW_RIGHT, ACT_FORWARD},
        {HID_KEY_R, ACT_REPEAT},           {HID_KEY_M, ACT_MUTE},          {HID_KEY_ARROW_UP, ACT_LOUDER},
        {HID_KEY_ARROW_DOWN, ACT_QUIETER},
    };
    uint8_t keys[sizeof(keys_last)], i, action = ACT_NONE;
    RIA.step0 = 1;
    RIA.addr0 = XRAM_KEYBOARD;
    for (i = 0; i < sizeof(keys); i++)
        keys[i] = RIA.rw0;
    for (i = 0; i < sizeof(KEYS) / sizeof(KEYS[0]) && !action; i++)
        if (key_down(keys, KEYS[i][0]))
            action = KEYS[i][1];
    for (i = 0; i < sizeof(keys); i++)
        keys_last[i] = keys[i];
    return action;
}

/* The first gamepad that is connected: the action of a button that went
 * down; L1 and R1, or the left stick, held, scrub by seconds. */
static uint8_t gamepad(int *scrub)
{
    uint8_t p, pad[4], down[4], i;
    RIA.step0 = 1;
    for (p = 0; p < GAMEPAD_PLAYERS; p++)
    {
        RIA.addr0 = XRAM_GAMEPAD + p * sizeof(gamepad_player_t);
        for (i = 0; i < 4; i++)
            pad[i] = RIA.rw0;
        if (pad[0] & GAMEPAD_FEAT_CONNECTED)
            break;
    }
    if (p == GAMEPAD_PLAYERS)
        pad[0] = pad[1] = pad[2] = pad[3] = 0;
    pad[0] &= 0x0F; /* the d-pad, without the feature bits */
    for (i = 0; i < 4; i++)
    {
        down[i] = pad[i] & ~pad_last[i];
        pad_last[i] = pad[i];
    }
    *scrub = (pad[2] & GAMEPAD_BTN0_R1 || pad[1] & GAMEPAD_LSTICK_RIGHT) ? 1
             : (pad[2] & GAMEPAD_BTN0_L1 || pad[1] & GAMEPAD_LSTICK_LEFT) ? -1 : 0;
    if (down[2] & GAMEPAD_BTN0_A)
        return ACT_PLAY;
    if (down[0] & GAMEPAD_DPAD_LEFT)
        return ACT_BACK;
    if (down[0] & GAMEPAD_DPAD_RIGHT)
        return ACT_FORWARD;
    if (down[0] & GAMEPAD_DPAD_UP)
        return ACT_LOUDER;
    if (down[0] & GAMEPAD_DPAD_DOWN)
        return ACT_QUIETER;
    if (down[2] & GAMEPAD_BTN0_X)
        return ACT_MUTE;
    if (down[2] & GAMEPAD_BTN0_Y)
        return ACT_REPEAT;
    return ACT_NONE;
}

static unsigned second_at_x(int x)
{
    int s = (int)((long)(x - TRACK_X0) * frames / TRACK_W / FPS);
    return s < 0 ? 0 : s >= (int)seconds ? seconds - 1 : (unsigned)s;
}

static bool scrub_to(unsigned second)
{
    if (show_state != SHOW_TITLE && second == (next - 1) / FPS)
        return true;
    return start_at(second, SHOW_PAUSE);
}

static bool scrub_end(void)
{
    if (scrub_from == SHOW_PLAY)
    {
        show_state = SHOW_PLAY;
        ticks = 0;
    }
    return true;
}

static bool near(int x, int y, int cx)
{
    return x >= cx - DISC_R && x <= cx + DISC_R && y >= DISC_Y - DISC_R && y <= DISC_Y + DISC_R;
}

/* The tablet: the pointer, and what a left click or drag asks for. The
 * emulator and the web player draw the pointer themselves; elsewhere the
 * transport draws its own. */
static bool tablet(bool *moved)
{
    tablet_contact_t c, check;
    uint8_t pressed;
    int x, y;
    host_cursor = xram0_peek8(XRAM_TABLET + offsetof(tablet_t, status)) & TABLET_STATUS_HOST_CURSOR;
    do
    {
        xram0_read(&c, XRAM_TABLET + offsetof(tablet_t, contact), sizeof(c));
        xram0_read(&check, XRAM_TABLET + offsetof(tablet_t, contact), sizeof(c));
    } while (c.flags != check.flags || c.x_lo != check.x_lo || c.y_lo != check.y_lo || c.yx_hi != check.yx_hi);
    pointer_in = c.flags & (TABLET_FLAG_HOVER | TABLET_FLAG_LEFT);
    x = (c.yx_hi & 0x0F) << 8 | c.x_lo;
    y = (c.yx_hi >> 4) << 8 | c.y_lo;
    *moved = x != pointer_x || y != pointer_y;
    if (*moved && (pointer_x >= 0 || x || y))
    {
        pointer_x = x;
        pointer_y = y;
    }
    else
        *moved = false;
    pressed = c.flags & TABLET_FLAG_LEFT & ~tablet_last;
    if (!(c.flags & TABLET_FLAG_LEFT) && tablet_last & TABLET_FLAG_LEFT && drag)
    {
        uint8_t was = drag;
        tablet_last = c.flags;
        drag = DRAG_NONE;
        return was == DRAG_TRACK ? scrub_end() : true;
    }
    tablet_last = c.flags;
    if (drag == DRAG_TRACK)
        return scrub_to(second_at_x(x));
    if (drag == DRAG_VOLUME)
    {
        int v = (x - VOLUME_X0) * (int)VOLUME_FULL / VOLUME_W;
        uint8_t want = v < 0 ? 0 : v > (int)VOLUME_FULL ? VOLUME_FULL : v;
        if (want != volume || muted)
        {
            volume = want;
            muted = false;
            set_volume();
        }
        return true;
    }
    if (!pressed)
        return true;
    /* A click on the video plays or pauses it, as on a video site, and
     * starts it from the title screen. A click on the transport, from the
     * top of the time label down, does only what it hits. */
    wake();
    if (y < BAR_TOP)
        return act(ACT_PLAY);
    if (near(x, y, BACK_X))
        return act(ACT_BACK);
    if (near(x, y, PLAY_X))
        return act(ACT_PLAY);
    if (near(x, y, FORWARD_X))
        return act(ACT_FORWARD);
    if (near(x, y, REPEAT_X))
        return act(ACT_REPEAT);
    if (near(x, y, SPEAKER_X))
        return act(ACT_MUTE);
    if (y >= DISC_Y - DISC_R && y <= DISC_Y + DISC_R)
    {
        if (x >= TRACK_X0 - 12 && x <= TRACK_X0 + TRACK_W + 12)
        {
            drag = DRAG_TRACK;
            scrub_from = show_state;
            return scrub_to(second_at_x(x));
        }
        if (x >= VOLUME_X0 - 8 && x <= VOLUME_X0 + VOLUME_W + 8)
            drag = DRAG_VOLUME;
    }
    return true;
}

/* At each VSYNC: the inputs, the fade, and the transport's sprites. */
static bool inputs(void)
{
    bool moved, ok;
    int scrub;
    uint8_t action;
    transport_t t;
    bool was_in = pointer_in;
    ok = tablet(&moved);
    if (moved && fade_step)
        wake();
    /* A pointer that leaves the canvas takes the transport with it, as on
     * a video site. */
    if (was_in && !pointer_in && !moved && idle < IDLE_VSYNCS)
        idle = IDLE_VSYNCS;
    if (moved || drag)
        idle = 0;
    action = keyboard();
    if (!action)
        action = gamepad(&scrub);
    else
        gamepad(&scrub);
    if (action)
    {
        wake();
        ok = ok && act(action);
    }
    if (scrub)
    {
        wake();
        if (!scrub_wait--)
        {
            int second = show_state == SHOW_TITLE ? 0 : (int)((next - 1) / FPS) + scrub;
            if (drag != DRAG_TRACK)
            {
                if (scrub_wait == 0xFF && show_state != SHOW_PAUSE)
                    scrub_from = show_state;
                drag = DRAG_TRACK;
            }
            scrub_wait = SCRUB_VSYNCS;
            ok = ok && scrub_to(second < 0 ? 0 : second >= (int)seconds ? seconds - 1 : second);
        }
    }
    else if (drag == DRAG_TRACK && !(tablet_last & TABLET_FLAG_LEFT))
    {
        drag = DRAG_NONE;
        scrub_wait = 0;
        ok = ok && scrub_end();
    }

    if (show_state == SHOW_PLAY && !drag)
    {
        if (idle < IDLE_VSYNCS)
            ++idle;
        else if (fade_step < FADE_STEPS && !fade_wait--)
        {
            fade_wait = FADE_VSYNCS;
            transport_fade(++fade_step);
        }
    }
    else if (fade_step)
        wake();
    else
        idle = 0;

    t.title = show_state == SHOW_TITLE;
    t.playing = show_state == SHOW_PLAY || (drag == DRAG_TRACK && scrub_from == SHOW_PLAY);
    t.repeat = repeat;
    t.muted = muted;
    t.frame = t.title ? 0 : next - 1;
    t.frames = frames;
    t.volume = volume;
    t.volume_full = VOLUME_FULL;
    t.pointer_x = pointer_in && !host_cursor ? pointer_x : -1;
    t.pointer_y = pointer_y;
    transport_draw(&t);
    if (host_cursor)
    {
        uint8_t want = fade_step == FADE_STEPS ? TABLET_CURSOR_OFF : TABLET_CURSOR_ARROW;
        if (want != cursor)
        {
            cursor = want;
            xram0_poke8(XRAM_TABLET + offsetof(tablet_t, control), want);
        }
    }
    return ok;
}

static bool read_index(void)
{
    uint8_t entry[6];
    unsigned s;
    int fd = open("ROM:index", O_RDONLY);
    if (fd < 0 || seconds > MAX_SECONDS)
        return false;
    for (s = 0; s < seconds; s++)
    {
        if (read(fd, entry, 6) != 6)
            return false;
        second_at[s].offset =
            entry[0] | (uint32_t)entry[1] << 8 | (uint32_t)entry[2] << 16 | (uint32_t)entry[3] << 24;
        second_at[s].block = entry[4] | entry[5] << 8;
    }
    close(fd);
    return true;
}

/* The arguments: "play" starts the video at once, without the title
 * screen, and "repeat" turns repeat on. The C runtime asks here for room
 * for them; more than ARGV_BYTES is turned away, and main() gets none. */
#define ARGV_BYTES 64
void *__argv_mem(size_t size)
{
    static char argv_data[ARGV_BYTES];
    return size <= ARGV_BYTES ? argv_data : NULL;
}

static bool is_arg(const char *arg, const char *word)
{
    for (; *word; arg++, word++)
        if ((*arg | 0x20) != *word)
            return false;
    return !*arg;
}

int main(int argc, char *argv[])
{
    uint8_t header[HEADER_BYTES];
    mode2_config_t config;
    uint8_t layer;
    bool play = false;
    int a;

    for (a = 1; a < argc; a++)
    {
        if (is_arg(argv[a], "play"))
            play = true;
        else if (is_arg(argv[a], "repeat"))
            repeat = true;
        else
        {
            printf("Unknown argument: %s. Arguments: play, repeat.\n", argv[a]);
            return 1;
        }
    }

    pcm_fd = open("PCM:30810,16,2", O_WRONLY);
    if (pcm_fd < 0)
    {
        puts("No PCM device found.");
        return 1;
    }
    frames_fd = open("ROM:frames", O_RDONLY);
    if (frames_fd < 0 || read(frames_fd, header, HEADER_BYTES) != HEADER_BYTES ||
        header[0] != 'B' || header[1] != 'A' || header[2] != 'D' || header[3] != '5')
    {
        puts("ROM:frames is missing.");
        return 1;
    }
    frames = header[4] | header[5] << 8;
    seconds = (frames + FPS - 1) / FPS;
    if (!read_index())
    {
        puts("ROM:index is missing.");
        return 1;
    }
    /* A run is at most 258 bytes, so decode_runs() stops a page short. */
    dec_limit = (XRAM_RING + RING_BYTES - 258) >> 8;
    set_volume();

    for (layer = 0; layer < LAYERS; layer++)
    {
        xram0_poke16(XRAM_PALETTE + layer * 4, COLOR_FROM_RGBA(0, 0, 0, layer ? 0 : 255));
        xram0_poke16(XRAM_PALETTE + layer * 4 + 2, COLOR_FROM_RGBA(255, 255, 255, 255));
        config = (mode2_config_t){
            .width_tiles = MAP_COLS,
            .height_tiles = MAP_ROWS,
            .xram_data_ptr = maps_of(0) + layer * MAP_BYTES,
            .xram_palette_ptr = XRAM_PALETTE + layer * 4,
            .xram_tile_ptr = XRAM_TILES + layer * 256 * 8,
        };
        xram0_write(XRAM_CONFIG + layer * sizeof(mode2_config_t), &config, sizeof(config));
    }
    xreg_ria_keyboard(XRAM_KEYBOARD);
    xreg_ria_tablet(XRAM_TABLET);
    xreg_ria_gamepad(XRAM_GAMEPAD);
    cursor = TABLET_CURSOR_ARROW;
    /* Setting the canvas clears every mode, so the sprites come after it. */
    xreg_vga_canvas(CANVAS_640X480);
    transport_init();
    if (!show_title())
    {
        puts("ROM:title is missing.");
        return 1;
    }
    if (play && !start_at(0, SHOW_PLAY))
        return 1;
    vsync = ria_vsync();
    while (1)
    {
        if (ria_vsync() != vsync)
        {
            ++vsync;
            pcm_full = false;
            if (show_state == SHOW_PLAY && ++ticks >= VSYNCS_PER_FRAME)
            {
                if (next == frames)
                {
                    if (!end_video())
                        return 1;
                    continue;
                }
                if (ahead)
                {
                    front = after(front);
                    show(front);
                    --ahead;
                    ticks -= VSYNCS_PER_FRAME;
                    ++next;
                }
            }
            if (!inputs())
                return 1;
        }
        if (show_state == SHOW_TITLE)
            continue;
        decode_step();
        if (scaling)
            scale_step();
        if (RIA.busy & 0x80)
            continue;
        if (call != CALL_NONE)
            finish_call();
        start_next_call();
    }
}

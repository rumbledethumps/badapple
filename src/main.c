#include <rp6502.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include "xram.h"

/* Plays ROM:frames, made by src/encode.py, in a loop.
 *
 * The file streams into a 16 KB ring in XRAM, in reads of 4 to 8 KB. Each
 * frame in it is a delta block, then the frame's sound. A delta block holds
 * the runs that turn the maps of two frames back, which its buffer still
 * holds, into this frame's maps. The 6502 applies them, one run per pass of
 * the main loop, while the next read runs. The sound goes from the ring to
 * the PCM device in order.
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
#define VSYNCS_PER_FRAME 2
#define AHEAD (BUFFERS - 1) /* frames decoded ahead of the one on screen */
#define READ_MIN 4096
#define READ_MAX 8192

enum
{
    CALL_NONE,
    CALL_PCM,
    CALL_READ,
};

static int frames_fd, pcm_fd;
static unsigned frames, first_block, loops;

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
static uint8_t run_left;     /* bytes left in a run that wraps the ring */
static unsigned run_to;      /* the XRAM address they go to */

/* In zero page, in copy.s, for decode_runs(). */
extern unsigned dec_map;  /* the XRAM address of the maps being decoded */
extern uint8_t dec_limit; /* the first page of the ring where a run might wrap */

static unsigned sound_len[BUFFERS]; /* bytes of each buffer's sound still to send, 0 when sent */
static unsigned sound_at[BUFFERS];  /* where it starts in the stream */
static uint8_t sound_play;          /* the buffer whose sound goes to the PCM device */
static unsigned sound_sent;         /* bytes of its sound already sent */
static unsigned pcm_asked;          /* bytes the PCM write in flight was given */
static bool pcm_full;               /* a PCM write filled the device since the last read or VSYNC */

static uint8_t call;

void copy_run(uint8_t count);  /* copy.s */
uint8_t decode_runs(void);     /* copy.s */

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
    parse += SOUND_BYTES;
    block = next_block;
    load = after(load);
    ++ahead;
    decoding = false;
}

/* One step of decoding: start the next frame's delta block once it and its
 * sound are all in the ring, then apply its runs, about 256 bytes a step,
 * in decode_runs(). Near the ring's end, where a run might wrap, this
 * applies one run at a time itself. */
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
        decoding = true;
        run_left = 0;
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
    unsigned start = sound_at[sound_play] + sound_sent, left = sound_len[sound_play] - sound_sent,
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

/* Fills the PCM device, then reads 4 to 8 KB into the ring when it has
 * room. */
static void start_next_call(void)
{
    unsigned at, count, space;
    if (!pcm_full && sound_len[sound_play])
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

/* Every pass starts the same way, so sound and picture start together:
 * both map buffers cleared, the ring filled, frame 0 decoded, then on
 * screen at a VSYNC, and its sound right after. */
static bool start_pass(void)
{
    unsigned i;
    if (lseek(frames_fd, HEADER_BYTES, SEEK_SET) < 0)
        return false;
    RIA.step0 = 1;
    RIA.addr0 = XRAM_MAPS;
    for (i = 0; i < BUFFERS * FRAME_BYTES; i++)
        RIA.rw0 = 0;
    for (i = 0; i < BUFFERS; i++)
        sound_len[i] = 0;
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
    block = first_block;
    decoding = false;
    front = load = 0;
    ahead = 0;
    next = 0;
    while (!ahead)
    {
        if (!decoding && (unsigned)(head - parse) < block + SOUND_BYTES)
            return false;
        decode_step();
    }
    ahead = 0;
    next = 1;
    sound_play = front;
    sound_sent = 0;
    pcm_full = false;
    call = CALL_NONE;
    if (!loops)
    {
        xreg_vga_canvas(CANVAS_640X480);
        for (i = 0; i < LAYERS; i++)
            xreg_vga_mode2(MODE2_1BPP | MODE2_8X8, XRAM_CONFIG + i * sizeof(mode2_config_t), i);
    }
    vsync = ria_vsync();
    while (ria_vsync() == vsync)
        ;
    ++vsync;
    show(front);
    ticks = 0;
    return true;
}

/* Sends what is left of the sound, lets it play, and starts the next pass. */
static bool end_pass(void)
{
    unsigned at, count;
    while (RIA.busy & 0x80)
        ;
    if (call != CALL_NONE)
        finish_call();
    while (sound_len[sound_play])
    {
        int n;
        count = sound_piece(&at);
        n = write_xram(at, count, pcm_fd);
        if (n < 0)
            break;
        sound_done(n);
    }
    syncfs(pcm_fd);
    ++loops;
    return start_pass();
}

int main(void)
{
    uint8_t header[HEADER_BYTES];
    mode2_config_t config;
    uint8_t layer;

    pcm_fd = open("PCM:30810,16,2", O_WRONLY);
    if (pcm_fd < 0)
    {
        puts("No PCM device found.");
        return 1;
    }
    frames_fd = open("ROM:frames", O_RDONLY);
    if (frames_fd < 0 || read(frames_fd, header, HEADER_BYTES) != HEADER_BYTES ||
        header[0] != 'B' || header[1] != 'A' || header[2] != 'D' || header[3] != '4')
    {
        puts("ROM:frames is missing.");
        return 1;
    }
    frames = header[4] | header[5] << 8;
    first_block = header[9] | header[10] << 8;
    /* A run is at most 258 bytes, so decode_runs() stops a page short. */
    dec_limit = (XRAM_RING + RING_BYTES - 258) >> 8;

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

    if (!start_pass())
        return 1;
    while (1)
    {
        if (ria_vsync() != vsync)
        {
            ++vsync;
            ++ticks;
            pcm_full = false;
            if (ticks >= VSYNCS_PER_FRAME)
            {
                if (next == frames)
                {
                    if (!end_pass())
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
        }
        decode_step();
        if (RIA.busy & 0x80)
            continue;
        if (call != CALL_NONE)
            finish_call();
        start_next_call();
    }
}

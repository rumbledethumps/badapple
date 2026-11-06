#include <rp6502.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include "xram.h"

/* Plays ROM:frames, made by src/encode.py, in a loop. Each frame is a
 * record of the bottom and top maps and the frame's sound. Three buffers in
 * XRAM hold the frame on screen and up to two frames loaded ahead of it. A
 * frame is shown by pointing both layers at its maps, at a VSYNC, so it
 * doesn't tear. A 30 fps frame lasts two 60 Hz VSYNCs. A frame that isn't
 * loaded by its VSYNC is shown at the next one. The sound goes from the
 * records to the PCM device in order.
 *
 * The main loop never waits for an API call. It starts one, then goes on
 * counting VSYNCs and showing frames until RIA.busy clears. Then it takes
 * the result and starts the next call.
 *
 * Nothing feeds the PCM device during a read, and its 4,096 bytes play for
 * 32 ms, so a record is read in two halves, and the device is filled before
 * every read, and at every VSYNC for when there is nothing to read. */

#define HEADER_BYTES 16
#define VSYNCS_PER_FRAME 2
#define BUFFERS 3
#define AHEAD 2 /* frames loaded ahead of the one on screen */
#define READ_BYTES (RECORD_BYTES / 2)

/* A test build, BADAPPLE_TEST, reads frames.bin from the current directory
 * instead of the ROM, so the ROM stays small enough to upload quickly. */
#ifdef BADAPPLE_TEST
#define FRAMES_PATH "frames.bin"
#else
#define FRAMES_PATH "ROM:frames"
#endif

enum
{
    CALL_NONE,
    CALL_PCM,
    CALL_READ,
};

static int frames_fd, pcm_fd;
static unsigned frames, loops;

static uint8_t vsync;  /* the last VSYNC counted */
static uint8_t ticks;  /* VSYNCs since the last frame was shown */
static uint8_t front;  /* the buffer on screen */
static uint8_t ahead;  /* frames loaded in the buffers after it */
static unsigned next;  /* the next frame to show */
static uint8_t load;   /* the buffer that frame next + ahead loads into */
static unsigned got;   /* bytes of its record loaded */

static unsigned sound_len[BUFFERS]; /* bytes of sound in each buffer still to send, 0 when sent */
static uint8_t sound_play;          /* the buffer whose sound goes to the PCM device */
static unsigned sound_sent;         /* bytes of its sound already sent */
static bool pcm_full;               /* a PCM write filled the device since the last read or VSYNC */

static uint8_t call;

static uint8_t after(uint8_t buffer)
{
    return buffer == BUFFERS - 1 ? 0 : buffer + 1;
}

static void show(uint8_t buffer)
{
    unsigned maps = XRAM_RECORDS + buffer * RECORD_BYTES;
    xram0_poke16(XRAM_CONFIG + offsetof(mode2_config_t, xram_data_ptr), maps);
    xram0_poke16(XRAM_CONFIG + sizeof(mode2_config_t) + offsetof(mode2_config_t, xram_data_ptr),
                 maps + MAP_BYTES);
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

static void finish_call(void)
{
    int n = RIA.a | RIA.x << 8;
    switch (call)
    {
    case CALL_PCM:
        /* A write that takes less than it was given filled the device. */
        if (n < (int)(sound_len[sound_play] - sound_sent))
            pcm_full = true;
        if (n > 0 && (sound_sent += n) >= sound_len[sound_play])
        {
            sound_len[sound_play] = 0;
            sound_play = after(sound_play);
            sound_sent = 0;
        }
        break;
    case CALL_READ:
        if (n > 0 && (got += n) == RECORD_BYTES)
        {
            sound_len[load] = SOUND_BYTES;
            load = after(load);
            ++ahead;
            got = 0;
        }
        pcm_full = false;
        break;
    }
    call = CALL_NONE;
}

/* Fills the PCM device, then reads half a record, up to two frames ahead,
 * once the buffer's last sound has all gone to the device. */
static void start_next_call(void)
{
    if (!pcm_full && sound_len[sound_play])
        start_call(CALL_PCM, RIA_OP_WRITE_XRAM,
                   XRAM_RECORDS + sound_play * RECORD_BYTES + FRAME_BYTES + sound_sent,
                   sound_len[sound_play] - sound_sent, pcm_fd);
    else if (ahead < AHEAD && next + ahead < frames && !sound_len[load])
        start_call(CALL_READ, RIA_OP_READ_XRAM, XRAM_RECORDS + load * RECORD_BYTES + got,
                   got < READ_BYTES ? READ_BYTES - got : RECORD_BYTES - got, frames_fd);
}

/* Every pass starts the same way, so sound and picture start together:
 * frame 0 loaded, then on screen at a VSYNC, and its sound right after. */
static bool start_pass(void)
{
    uint8_t first = load, i;
    unsigned addr = XRAM_RECORDS + first * RECORD_BYTES, count = RECORD_BYTES;
    if (lseek(frames_fd, HEADER_BYTES, SEEK_SET) < 0)
        return false;
    while (count)
    {
        int n = read_xram(addr, count, frames_fd);
        if (n <= 0)
            return false;
        addr += n;
        count -= n;
    }
    for (i = 0; i < BUFFERS; i++)
        sound_len[i] = 0;
    sound_len[first] = SOUND_BYTES;
    sound_play = first;
    sound_sent = 0;
    pcm_full = false;
    front = first;
    ahead = 0;
    next = 1;
    load = after(first);
    got = 0;
    call = CALL_NONE;
    if (!loops)
    {
        xreg_vga_canvas(CANVAS_640X480);
        xreg_vga_mode2(MODE2_1BPP | MODE2_8X8, XRAM_CONFIG, 0);
        xreg_vga_mode2(MODE2_1BPP | MODE2_8X8, XRAM_CONFIG + sizeof(mode2_config_t), 1);
    }
    vsync = ria_vsync();
    while (ria_vsync() == vsync)
        ;
    ++vsync;
    show(first);
    ticks = 0;
    return true;
}

/* Sends what is left of the sound, lets it play, and starts the next pass. */
static bool end_pass(void)
{
    while (RIA.busy & 0x80)
        ;
    if (call != CALL_NONE)
        finish_call();
    while (sound_len[sound_play])
    {
        int n = write_xram(XRAM_RECORDS + sound_play * RECORD_BYTES + FRAME_BYTES + sound_sent,
                           sound_len[sound_play] - sound_sent, pcm_fd);
        if (n < 0)
            break;
        if ((sound_sent += n) >= sound_len[sound_play])
        {
            sound_len[sound_play] = 0;
            sound_play = after(sound_play);
            sound_sent = 0;
        }
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
    frames_fd = open(FRAMES_PATH, O_RDONLY);
    if (frames_fd < 0 || read(frames_fd, header, HEADER_BYTES) != HEADER_BYTES ||
        header[0] != 'B' || header[1] != 'A' || header[2] != 'D' || header[3] != '2')
    {
        puts(FRAMES_PATH " is missing.");
        return 1;
    }
    frames = header[4] | header[5] << 8;

    xram0_poke16(XRAM_PALETTE + 0, COLOR_FROM_RGBA(0, 0, 0, 255));
    xram0_poke16(XRAM_PALETTE + 2, COLOR_FROM_RGBA(255, 255, 255, 255));
    xram0_poke16(XRAM_PALETTE + 4, COLOR_FROM_RGBA(0, 0, 0, 0));
    xram0_poke16(XRAM_PALETTE + 6, COLOR_FROM_RGBA(255, 255, 255, 255));
    for (layer = 0; layer < 2; layer++)
    {
        config = (mode2_config_t){
            .width_tiles = MAP_COLS,
            .height_tiles = MAP_ROWS,
            .xram_data_ptr = XRAM_RECORDS + layer * MAP_BYTES,
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
        if (RIA.busy & 0x80)
            continue;
        if (call != CALL_NONE)
            finish_call();
        start_next_call();
    }
}

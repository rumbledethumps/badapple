#include <rp6502.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include "xram.h"

/* Plays ROM:video and ROM:audio, made by src/encode.py, in a loop. Each
 * frame is the bottom and top maps, read into the back buffer in XRAM, then
 * shown by pointing both layers at it. A 30 fps frame lasts two 60 Hz
 * VSYNCs. Sound goes from ROM:audio into two buffers in XRAM, and from them
 * to the PCM device.
 *
 * The main loop never waits for an API call. It starts one, then goes on
 * counting VSYNCs and showing frames until RIA.busy clears. Then it takes
 * the result and starts the next call, a PCM write every other time. */

#define HEADER_BYTES 16
#define VSYNCS_PER_FRAME 2

enum
{
    CALL_NONE,
    CALL_PCM,
    CALL_AUDIO,
    CALL_VIDEO,
};

static int video_fd, audio_fd, pcm_fd;
static unsigned frames, loops;

static uint8_t vsync;       /* the last VSYNC counted */
static uint8_t ticks;       /* VSYNCs since the last frame was shown */
static uint8_t back;        /* the buffer that the next frame loads into */
static unsigned next;       /* the next frame to show */
static unsigned video_got;  /* bytes of it loaded */

static unsigned audio_len[2]; /* bytes in each audio buffer, 0 when empty */
static uint8_t audio_play;    /* the buffer going to the PCM device */
static uint8_t audio_load;    /* the buffer to fill next */
static unsigned audio_sent;   /* bytes of audio_play already sent */
static bool audio_end;        /* ROM:audio has no more */

static uint8_t call;
static bool pcm_turn;

static void show(uint8_t buffer)
{
    unsigned maps = XRAM_MAPS + buffer * FRAME_BYTES;
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
        if (n > 0 && (audio_sent += n) >= audio_len[audio_play])
        {
            audio_len[audio_play] = 0;
            audio_play ^= 1;
            audio_sent = 0;
        }
        break;
    case CALL_AUDIO:
        if (n > 0)
        {
            audio_len[audio_load] = n;
            audio_load ^= 1;
        }
        else
            audio_end = true;
        break;
    case CALL_VIDEO:
        if (n > 0)
            video_got += n;
        break;
    }
    call = CALL_NONE;
}

static void start_pcm(void)
{
    start_call(CALL_PCM, RIA_OP_WRITE_XRAM, XRAM_AUDIO + audio_play * AUDIO_BYTES + audio_sent,
               audio_len[audio_play] - audio_sent, pcm_fd);
}

/* A PCM write every other call. Between them, fill an empty audio buffer,
 * or else load the next frame. */
static void start_next_call(void)
{
    bool pcm_ready = audio_len[audio_play] != 0;
    if (pcm_turn && pcm_ready)
    {
        start_pcm();
        pcm_turn = false;
        return;
    }
    pcm_turn = true;
    if (!audio_end && !audio_len[audio_load])
        start_call(CALL_AUDIO, RIA_OP_READ_XRAM, XRAM_AUDIO + audio_load * AUDIO_BYTES,
                   AUDIO_BYTES, audio_fd);
    else if (next < frames && video_got < FRAME_BYTES)
        start_call(CALL_VIDEO, RIA_OP_READ_XRAM, XRAM_MAPS + back * FRAME_BYTES + video_got,
                   FRAME_BYTES - video_got, video_fd);
    else if (pcm_ready)
        start_pcm();
}

static bool load(int fd, unsigned addr, unsigned count)
{
    while (count)
    {
        int n = read_xram(addr, count, fd);
        if (n <= 0)
            return false;
        addr += n;
        count -= n;
    }
    return true;
}

/* Every pass starts the same way, so sound and picture start together:
 * frame 0 and both audio buffers loaded, then frame 0 on screen at a VSYNC
 * and the first sound right after it. */
static bool start_pass(void)
{
    uint8_t i, first = back;
    if (lseek(video_fd, HEADER_BYTES, SEEK_SET) < 0 || lseek(audio_fd, 0, SEEK_SET) < 0 ||
        !load(video_fd, XRAM_MAPS + first * FRAME_BYTES, FRAME_BYTES))
        return false;
    for (i = 0; i < 2; i++)
    {
        int n = read_xram(XRAM_AUDIO + i * AUDIO_BYTES, AUDIO_BYTES, audio_fd);
        audio_len[i] = n > 0 ? n : 0;
    }
    audio_play = audio_load = 0;
    audio_sent = 0;
    audio_end = false;
    back = first ^ 1;
    next = 1;
    video_got = 0;
    call = CALL_NONE;
    pcm_turn = true;
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
    while (audio_len[audio_play])
    {
        int n = write_xram(XRAM_AUDIO + audio_play * AUDIO_BYTES + audio_sent,
                           audio_len[audio_play] - audio_sent, pcm_fd);
        if (n < 0)
            break;
        if ((audio_sent += n) >= audio_len[audio_play])
        {
            audio_len[audio_play] = 0;
            audio_play ^= 1;
            audio_sent = 0;
        }
    }
    syncfs(pcm_fd);
    printf("Loop %u\n", ++loops);
    return start_pass();
}

int main(void)
{
    uint8_t header[HEADER_BYTES];
    mode2_config_t config;
    uint8_t layer;

    pcm_fd = open("PCM:32000,16,2", O_WRONLY);
    if (pcm_fd < 0)
    {
        puts("No PCM device found.");
        return 1;
    }
    video_fd = open("ROM:video", O_RDONLY);
    audio_fd = open("ROM:audio", O_RDONLY);
    if (video_fd < 0 || audio_fd < 0 || read(video_fd, header, HEADER_BYTES) != HEADER_BYTES ||
        header[0] != 'B' || header[1] != 'A' || header[2] != 'D' || header[3] != '1')
    {
        puts("ROM:video or ROM:audio is missing.");
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
            .xram_data_ptr = XRAM_MAPS + layer * MAP_BYTES,
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
        }
        if (ticks >= VSYNCS_PER_FRAME)
        {
            if (next == frames)
            {
                if (!end_pass())
                    return 1;
                continue;
            }
            if (video_got == FRAME_BYTES)
            {
                show(back);
                back ^= 1;
                ticks -= VSYNCS_PER_FRAME;
                ++next;
                video_got = 0;
            }
        }
        if (RIA.busy & 0x80)
            continue;
        if (call != CALL_NONE)
            finish_call();
        start_next_call();
    }
}

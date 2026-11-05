#include <rp6502.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include "xram.h"

/* Plays ROM:video, made by src/encode.py, in a loop. Each frame is the
 * bottom and top maps, read straight into the back buffer in XRAM, then
 * shown by pointing both layers at it. A 30 fps frame lasts two 60 Hz
 * VSYNCs. */

#define HEADER_BYTES 16
#define VSYNCS_PER_FRAME 2

static uint8_t vsync;

/* Waits for the VSYNC after the last one waited for. When playback is
 * behind, VSYNC has already moved on, so this returns at once and the
 * video catches up. */
static void wait_vsync(void)
{
    while (ria_vsync() == vsync)
        ;
    ++vsync;
}

static void show(uint8_t buffer)
{
    unsigned maps = XRAM_MAPS + buffer * FRAME_BYTES;
    xram0_poke16(XRAM_CONFIG + offsetof(mode2_config_t, xram_data_ptr), maps);
    xram0_poke16(XRAM_CONFIG + sizeof(mode2_config_t) + offsetof(mode2_config_t, xram_data_ptr),
                 maps + MAP_BYTES);
}

static bool load(int fd, uint8_t buffer)
{
    unsigned addr = XRAM_MAPS + buffer * FRAME_BYTES, left = FRAME_BYTES;
    while (left)
    {
        int n = read_xram(addr, left, fd);
        if (n <= 0)
            return false;
        addr += n;
        left -= n;
    }
    return true;
}

int main(void)
{
    uint8_t header[HEADER_BYTES];
    mode2_config_t config;
    unsigned frames, frame = 0, loops = 0;
    uint8_t back = 1, layer, i;
    int fd = open("ROM:video", O_RDONLY);

    if (fd < 0 || read(fd, header, HEADER_BYTES) != HEADER_BYTES ||
        header[0] != 'B' || header[1] != 'A' || header[2] != 'D' || header[3] != '1')
    {
        puts("ROM:video is missing or not a Bad Apple!! stream.");
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

    if (!load(fd, 0))
    {
        puts("ROM:video ended early.");
        return 1;
    }
    xreg_vga_canvas(CANVAS_640X480);
    xreg_vga_mode2(MODE2_1BPP | MODE2_8X8, XRAM_CONFIG, 0);
    xreg_vga_mode2(MODE2_1BPP | MODE2_8X8, XRAM_CONFIG + sizeof(mode2_config_t), 1);

    vsync = ria_vsync();
    while (1)
    {
        if (++frame == frames)
        {
            printf("Loop %u\n", ++loops);
            frame = 0;
            if (lseek(fd, HEADER_BYTES, SEEK_SET) < 0)
                return 1;
        }
        if (!load(fd, back))
            return 1;
        for (i = 0; i < VSYNCS_PER_FRAME; i++)
            wait_vsync();
        show(back);
        back ^= 1;
    }
}

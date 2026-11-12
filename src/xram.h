/* RP6502 XRAM Mapping */

#ifndef XRAM_H
#define XRAM_H

#include <rp6502.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* From the VGA page: Canvas Types and Mode 2. */

#define xreg_vga_canvas(...) xreg(0x1, 0x0, 0x00, __VA_ARGS__)

#define CANVAS_CONSOLE 0
#define CANVAS_320X240 1
#define CANVAS_320X180 2
#define CANVAS_640X480 3
#define CANVAS_640X360 4
#define CANVAS_320X200 5
#define CANVAS_640X400 6

#define xreg_vga_mode2(...) xreg(0x1, 0x0, 0x01, 2, __VA_ARGS__)

#define MODE2_1BPP 0x00
#define MODE2_2BPP 0x01
#define MODE2_4BPP 0x02
#define MODE2_8BPP 0x03

#define MODE2_8X8 0x00
#define MODE2_16X16 0x08

typedef struct
{
    bool x_wrap;
    bool y_wrap;
    int16_t x_pos_px;
    int16_t y_pos_px;
    int16_t width_tiles;
    int16_t height_tiles;
    uint16_t xram_data_ptr;
    uint16_t xram_palette_ptr;
    uint16_t xram_tile_ptr;
} mode2_config_t; /* layout */

#define COLOR_FROM_RGBA(r, g, b, alpha)                             \
    ((((unsigned)(b) >> 3) << 11) | (((unsigned)(g) >> 3) << 6) | \
     (((unsigned)(alpha) >> 7) << 5) | ((unsigned)(r) >> 3))

/* Bad Apple!! on three 80x60 maps of 8x8 1bpp tiles, a 640x480 canvas.
 * Layer 0 (plane 0) draws the gray as a checkerboard on black. Layers 1 and
 * 2 (planes 1 and 2) draw the hard white edges over it. Their tile 0 is
 * clear, because black is transparent on them.
 *
 * Each frame is a record in ROM:frames: the three maps, then the frame's
 * sound, 1,027 samples of 30,810 Hz 16-bit stereo. */

#define MAP_COLS 80
#define MAP_ROWS 60
#define MAP_BYTES (MAP_COLS * MAP_ROWS)
#define LAYERS 3
#define FRAME_BYTES (LAYERS * MAP_BYTES)
#define SOUND_BYTES 4108
#define RECORD_BYTES (FRAME_BYTES + SOUND_BYTES)
#define BUFFERS 2

typedef struct
{
    uint8_t maps[LAYERS][MAP_BYTES];  /* [layer] */
    uint8_t sound[SOUND_BYTES];
} record_t;

typedef struct
{
    uint8_t tiles[LAYERS][256][8];  /* [layer], loaded from tiles.bin */
    mode2_config_t config[LAYERS];  /* [layer] */
    uint16_t palette[LAYERS][2];    /* [layer][color] */
    record_t records[BUFFERS];       /* [buffer] */
} xram_layout_t;

#define XRAM_TILES offsetof(xram_layout_t, tiles)
#define XRAM_CONFIG offsetof(xram_layout_t, config)
#define XRAM_PALETTE offsetof(xram_layout_t, palette)
#define XRAM_RECORDS offsetof(xram_layout_t, records)

#endif

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

/* From the RIA page: Keyboard. */

#define xreg_ria_keyboard(...) xreg(0x0, 0x0, 0x00, __VA_ARGS__)
#define KEYBOARD_NO_KEY 0
#define KEYBOARD_PRESSED(keys, code) ((keys)[(code) >> 3] & (1 << ((code) & 7)))
#define HID_KEY_M 0x10
#define HID_KEY_R 0x15
#define HID_KEY_SPACE 0x2C
#define HID_KEY_ARROW_RIGHT 0x4F
#define HID_KEY_ARROW_LEFT 0x50
#define HID_KEY_ARROW_DOWN 0x51
#define HID_KEY_ARROW_UP 0x52

typedef struct
{
    uint8_t keys[32];
} keyboard_t; /* layout */

/* Bad Apple!! on three 80x60 maps of 8x8 1bpp tiles, a 640x480 canvas.
 * Layer 0 (plane 0) draws the gray as a checkerboard on black. Layers 1 and
 * 2 (planes 1 and 2) draw the hard white edges over it. Their tile 0 is
 * clear, because black is transparent on them.
 *
 * ROM:frames streams into a ring: per frame a delta block, the runs that
 * turn the maps of two frames back into this frame's, then the frame's
 * sound, 1,027 samples of 30,810 Hz 16-bit stereo.
 *
 * The title screen, ROM:title, is one 4-bit map on plane 0, in bands of
 * scanlines with 256 tiles each. While it shows, its tiles and map take
 * the place of the video's map buffers and ring. */

#define MAP_COLS 80
#define MAP_ROWS 60
#define MAP_BYTES (MAP_COLS * MAP_ROWS)
#define LAYERS 3
#define FRAME_BYTES (LAYERS * MAP_BYTES)
#define SOUND_BYTES 4108
#define BUFFERS 2
#define RING_BYTES 16384
#define RING_MASK (RING_BYTES - 1)
#define TITLE_BANDS 4
#define TITLE_TILE_BYTES 32 /* 8x8, 4 bits a pixel */

typedef struct
{
    uint8_t tiles[LAYERS][256][8];             /* [layer], loaded from tiles.bin */
    mode2_config_t config[LAYERS];             /* [layer] */
    mode2_config_t title_config[TITLE_BANDS];  /* [band] */
    uint16_t palette[LAYERS][2];               /* [layer][color] */
    uint16_t title_palette[16];
    keyboard_t keyboard;
    union
    {
        struct
        {
            uint8_t maps[BUFFERS][LAYERS][MAP_BYTES];  /* [buffer][layer] */
            uint8_t ring[RING_BYTES];                  /* ROM:frames, as read */
        } video;
        struct
        {
            uint8_t tiles[TITLE_BANDS][256][TITLE_TILE_BYTES];
            uint8_t map[MAP_BYTES];
        } title;
    } area;
} xram_layout_t;

#define XRAM_TILES offsetof(xram_layout_t, tiles)
#define XRAM_CONFIG offsetof(xram_layout_t, config)
#define XRAM_TITLE_CONFIG offsetof(xram_layout_t, title_config)
#define XRAM_PALETTE offsetof(xram_layout_t, palette)
#define XRAM_TITLE_PALETTE offsetof(xram_layout_t, title_palette)
#define XRAM_KEYBOARD offsetof(xram_layout_t, keyboard)
#define XRAM_MAPS offsetof(xram_layout_t, area.video.maps)
#define XRAM_RING offsetof(xram_layout_t, area.video.ring)
#define XRAM_TITLE_TILES offsetof(xram_layout_t, area.title.tiles)
#define XRAM_TITLE_MAP offsetof(xram_layout_t, area.title.map)

#endif

#include <rp6502.h>
#include <string.h>
#include "transport.h"
#include "xram.h"

/* The images of transport.bin, in its order, after its palettes. */
enum
{
    IMG_BACK,
    IMG_PLAY,
    IMG_PAUSE,
    IMG_FORWARD,
    IMG_REPEAT_ON,
    IMG_REPEAT_OFF,
    IMG_SPEAKER,
    IMG_MUTED,
    IMG_TRACK_LEFT,
    IMG_TRACK,
    IMG_TRACK_RIGHT,
    IMG_FILL,
    IMG_PLAYHEAD,
    IMG_LABEL,
    IMG_DIGIT,                 /* 0 to 9, then the colon */
    IMG_COLON = IMG_DIGIT + 10,
    IMG_VOLUME_TRACK,
    IMG_VOLUME_FILL,
    IMG_POINTER,
    IMAGES,
};

enum
{
    PAL_SKY,
    PAL_BUTTER,
    PAL_MINT,
    PAL_STONE,
    PAL_LILAC,
    PAL_PEACH,
    PAL_WHITE,
};

static const struct
{
    uint8_t w, h, palette;
} IMAGE[IMAGES] = {
    {32, 32, PAL_SKY}, {32, 32, PAL_BUTTER}, {32, 32, PAL_BUTTER}, {32, 32, PAL_SKY},
    {32, 32, PAL_MINT}, {32, 32, PAL_STONE}, {32, 32, PAL_LILAC}, {32, 32, PAL_LILAC},
    {64, 8, PAL_LILAC}, {64, 8, PAL_LILAC}, {64, 8, PAL_LILAC}, {64, 4, PAL_PEACH},
    {16, 16, PAL_PEACH}, {48, 16, PAL_BUTTER},
    {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER},
    {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER},
    {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER}, {8, 12, PAL_BUTTER},
    {48, 8, PAL_LILAC}, {48, 4, PAL_MINT}, {12, 20, PAL_WHITE},
};

/* The sprites, in drawing order: later ones cover earlier ones. */
enum
{
    S_TRACK,                    /* 5 pieces */
    S_FILL = S_TRACK + 5,       /* 6 pieces */
    S_PLAYHEAD = S_FILL + 6,
    S_LABEL,
    S_DIGIT,                    /* m:ss, 4 */
    S_BACK = S_DIGIT + 4,
    S_PLAY,
    S_FORWARD,
    S_REPEAT,
    S_SPEAKER,
    S_VOLUME_TRACK,
    S_VOLUME_FILL,
    S_POINTER,
    S_COUNT,
};
_Static_assert(S_COUNT == SPRITES, "the sprite array holds every sprite");

#define PALETTE_BYTES 32
#define RANKS 5
#define HIDDEN -64

static unsigned image_at[IMAGES];
static transport_t last;   /* what the sprites show */
static bool redraw = true; /* draw everything at the next call */
static bool hidden;        /* faded all the way out */
static mode5_csprite_t shown[SPRITES]; /* what XRAM holds */
static uint16_t base[TRANSPORT_PALETTES][16];

static void put(uint8_t slot, uint8_t img, int x, int y, uint8_t w)
{
    mode5_csprite_t s;
    s.x_pos_px = x;
    s.y_pos_px = y;
    s.xram_sprite_ptr = image_at[img];
    s.palette_ptr = XRAM_TRANSPORT + IMAGE[img].palette * PALETTE_BYTES;
    s.width_height = MODE5_SIZE(w ? w : IMAGE[img].w, IMAGE[img].h);
    s.attributes = MODE5_4BPP;
    if (memcmp(&s, &shown[slot], sizeof(s)))
    {
        shown[slot] = s;
        xram0_write(XRAM_SPRITES + slot * sizeof(s), &s, sizeof(s));
    }
}

static void hide(uint8_t slot, uint8_t img)
{
    put(slot, img, 0, HIDDEN, 0);
}

void transport_init(void)
{
    unsigned at = XRAM_TRANSPORT + TRANSPORT_PALETTES * PALETTE_BYTES;
    uint8_t i, j;
    for (i = 0; i < IMAGES; i++)
    {
        image_at[i] = at;
        at += IMAGE[i].w * IMAGE[i].h / 2;
    }
    for (i = 0; i < TRANSPORT_PALETTES; i++)
        for (j = 0; j < 16; j++)
            base[i][j] = xram0_peek16(XRAM_TRANSPORT + i * PALETTE_BYTES + j * 2);
    memset(shown, 0xFF, sizeof(shown));
    for (i = 0; i < SPRITES; i++)
        hide(i, IMG_FILL);
    xreg_vga_mode5(MODE5_CUSTOM, XRAM_SPRITES, SPRITES, 2, 0, 0);
}

/* Draws what changed since the last call, so a VSYNC with nothing new
 * costs almost nothing. While the transport is faded out, only the pointer
 * moves; everything is drawn again when it comes back. */
void transport_draw(const transport_t *t)
{
    unsigned x, seconds, w;
    uint8_t i, digits[4];
    int start;
    bool all = redraw;
    redraw = false;

    if (t->pointer_x != last.pointer_x || t->pointer_y != last.pointer_y || all)
    {
        if (t->pointer_x >= 0)
            put(S_POINTER, IMG_POINTER, t->pointer_x - 1, t->pointer_y - 1, 0);
        else
            hide(S_POINTER, IMG_POINTER);
    }
    if (hidden)
    {
        last.pointer_x = t->pointer_x;
        last.pointer_y = t->pointer_y;
        redraw = true;
        return;
    }
    if (all)
        /* The track, five pieces from 148 to 468. */
        for (i = 0; i < 5; i++)
            put(S_TRACK + i, i == 0 ? IMG_TRACK_LEFT : i == 4 ? IMG_TRACK_RIGHT : IMG_TRACK,
                TRACK_X0 - 2 + 64 * i, DISC_Y - 4, 0);
    if (all || t->title != last.title || t->playing != last.playing || t->repeat != last.repeat ||
        t->muted != last.muted || t->volume != last.volume)
    {
        put(S_BACK, IMG_BACK, BACK_X - DISC_R, DISC_Y - DISC_R, 0);
        put(S_PLAY, t->playing && !t->title ? IMG_PAUSE : IMG_PLAY, PLAY_X - DISC_R, DISC_Y - DISC_R, 0);
        put(S_FORWARD, IMG_FORWARD, FORWARD_X - DISC_R, DISC_Y - DISC_R, 0);
        put(S_REPEAT, t->repeat ? IMG_REPEAT_ON : IMG_REPEAT_OFF, REPEAT_X - DISC_R, DISC_Y - DISC_R, 0);
        put(S_SPEAKER, t->muted ? IMG_MUTED : IMG_SPEAKER, SPEAKER_X - DISC_R, DISC_Y - DISC_R, 0);
        put(S_VOLUME_TRACK, IMG_VOLUME_TRACK, VOLUME_X0 - 2, DISC_Y - 4, 0);
        w = t->muted ? 0 : (t->volume * VOLUME_W + t->volume_full / 2) / t->volume_full;
        if (w)
            put(S_VOLUME_FILL, IMG_VOLUME_FILL, VOLUME_X0, DISC_Y - 2, (w + 3) & ~3u);
        else
            hide(S_VOLUME_FILL, IMG_VOLUME_FILL);
    }
    if (!all && t->frame == last.frame && t->title == last.title)
    {
        last = *t;
        return;
    }
    last = *t;
    x = TRACK_X0 + (unsigned)((uint32_t)t->frame * TRACK_W / t->frames);
    seconds = t->frame / 30;

    /* The played part: solid pieces, the last as wide as it needs. */
    for (i = 0; i < 6; i++)
    {
        start = TRACK_X0 + 64 * i;
        if (start >= (int)x)
        {
            hide(S_FILL + i, IMG_FILL);
            continue;
        }
        w = x - start;
        w = w >= 64 ? 64 : (w + 3) & ~3u;
        put(S_FILL + i, IMG_FILL, start, DISC_Y - 2, w);
    }
    put(S_PLAYHEAD, IMG_PLAYHEAD, x - 8, DISC_Y - 8, 0);

    /* The time, m:ss, in a label above the playhead. */
    put(S_LABEL, IMG_LABEL, x - 24, DISC_Y - 30, 0);
    digits[0] = IMG_DIGIT + seconds / 60 % 10;
    digits[1] = IMG_COLON;
    digits[2] = IMG_DIGIT + seconds % 60 / 10;
    digits[3] = IMG_DIGIT + seconds % 10;
    for (i = 0; i < 4; i++)
        put(S_DIGIT + i, digits[i], x - 16 + 8 * i, DISC_Y - 28, 0);
}

void transport_fade(uint8_t step)
{
    uint8_t p, j;
    uint16_t c;
    hidden = step >= RANKS;
    RIA.step0 = 1;
    for (p = 0; p < TRANSPORT_PALETTES; p++)
    {
        RIA.addr0 = XRAM_TRANSPORT + p * PALETTE_BYTES + 2;
        for (j = 1; j < 16; j++)
        {
            c = base[p][j];
            if ((j - 1) % RANKS < step)
                c &= ~(1u << 5);
            RIA.rw0 = c;
            RIA.rw0 = c >> 8;
        }
    }
}

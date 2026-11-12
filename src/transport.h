/* The gel-disc transport: sprites on plane 2, drawn from transport.bin,
 * which src/transport.py makes and the ROM loads into XRAM. */

#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>
#include <stdint.h>

/* Where things are on the canvas. */
#define BAR_TOP 410     /* the transport's area starts here */
#define DISC_Y 444      /* the centers of the discs and the track */
#define DISC_R 16
#define BACK_X 32
#define PLAY_X 72
#define FORWARD_X 112
#define REPEAT_X 512
#define SPEAKER_X 556
#define TRACK_X0 150    /* the playhead's center at 0:00 */
#define TRACK_W 316     /* and at the end, TRACK_X0 + TRACK_W; the track is
                           five 64-pixel pieces, 148 to 468 */
#define VOLUME_X0 580   /* the volume fill, 0 to VOLUME_W wide */
#define VOLUME_W 44

typedef struct
{
    bool title, playing, repeat, muted;
    unsigned frame, frames; /* the frame on screen, of frames */
    uint8_t volume, volume_full;
    int pointer_x, pointer_y;
} transport_t;

void transport_init(void);

/* Moves the sprites to match, at a VSYNC. */
void transport_draw(const transport_t *t);

/* Fades the transport and pointer: 0 shows them, 5 hides them, in the
 * steps of the palettes' dissolve. */
void transport_fade(uint8_t step);

#endif

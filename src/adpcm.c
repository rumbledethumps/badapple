/* Bad Apple!! sound encoder: 4-bit block DPCM for the 6502 to decode.
 *
 * usage: adpcm SHAPING PATHS < in.raw > out.bin
 *
 * in.raw is 16-bit stereo PCM, little-endian, 1,027 sample pairs a frame.
 * For each frame, out.bin has 1,064 bytes:
 *   - the left and right samples the frame starts from, 2 bytes each,
 *   - 33 blocks, 32 pairs each but the last, which has 3: a header byte,
 *     the left channel's scale in the high 4 bits and the right's in the
 *     low 4, then a byte a pair, the left code in the high 4 bits and the
 *     right in the low 4.
 * A sample is the one before it plus DELTA(scale, code), (code - 8) times
 * STEP[scale], in 16 bits; the encoder never lets a sample leave 16 bits,
 * so the decoder needs no clamp. That makes decoding a table lookup and a
 * 16-bit add a sample.
 *
 * Each block's scale and codes are searched together: the scales that do
 * best on a quick greedy pass are tried with a trellis of PATHS paths. The
 * error is shaped by feeding back SHAPING times the last error: a negative
 * value moves the noise down from the treble, where the music is quiet, to
 * where the music hides it. */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAIRS 1027
#define BLOCK 32
#define BLOCKS ((PAIRS + BLOCK - 1) / BLOCK)
#define FRAME_OUT (4 + BLOCKS + PAIRS)
#define SCALES 16
#define TRIES 2
#define MAXPATHS 64

static int STEP[SCALES];

static int delta(int scale, int code)
{
    return (code - 8) * STEP[scale];
}

typedef struct
{
    int acc;     /* the decoded sample */
    double e1;   /* the last error, fed back */
    double cost;
    unsigned char codes[BLOCK];
} path_t;

/* Codes for one channel's block from acc, at one scale; returns the cost. */
static double search(const short *x, int n, int stride, int scale, int acc, double e1, double shaping, int paths,
                     unsigned char *codes, int *acc_out, double *e1_out)
{
    static path_t a[MAXPATHS], b[MAXPATHS * 16];
    int na = 1, i;
    a[0].acc = acc;
    a[0].e1 = e1;
    a[0].cost = 0;
    for (i = 0; i < n; i++)
    {
        int nb = 0, j, c;
        for (j = 0; j < na; j++)
        {
            double target = x[i * stride] - shaping * a[j].e1;
            for (c = 0; c < 16; c++)
            {
                int y = a[j].acc + delta(scale, c);
                double e;
                if (y > 32767 || y < -32768)
                    continue;
                e = y - target;
                b[nb] = a[j];
                b[nb].acc = y;
                b[nb].e1 = e;
                b[nb].cost = a[j].cost + e * e;
                b[nb].codes[i] = c;
                nb++;
            }
        }
        /* Keep the best paths, one for each decoded value. */
        for (j = 1; j < nb; j++)
        {
            path_t t = b[j];
            int k = j - 1;
            while (k >= 0 && b[k].cost > t.cost)
            {
                b[k + 1] = b[k];
                k--;
            }
            b[k + 1] = t;
        }
        na = 0;
        for (j = 0; j < nb && na < paths; j++)
        {
            int k, dup = 0;
            for (k = 0; k < na; k++)
                if (a[k].acc == b[j].acc)
                    dup = 1;
            if (!dup)
                a[na++] = b[j];
        }
    }
    memcpy(codes, a[0].codes, n);
    *acc_out = a[0].acc;
    *e1_out = a[0].e1;
    return a[0].cost;
}

/* A quick greedy cost, to choose which scales to search. */
static double greedy(const short *x, int n, int stride, int scale, int acc, double e1, double shaping)
{
    double cost = 0;
    int i, c;
    for (i = 0; i < n; i++)
    {
        double target = x[i * stride] - shaping * e1, best = 1e300;
        int by = acc;
        for (c = 0; c < 16; c++)
        {
            int y = acc + delta(scale, c);
            double e = y - target;
            if (y > 32767 || y < -32768)
                continue;
            if (e * e < best)
            {
                best = e * e;
                by = y;
            }
        }
        cost += best;
        e1 = by - target;
        acc = by;
    }
    return cost;
}

int main(int argc, char **argv)
{
    double shaping = argc > 1 ? atof(argv[1]) : 0;
    int paths = argc > 2 ? atoi(argv[2]) : 16, k, frame;
    short in[PAIRS * 2];
    unsigned char out[FRAME_OUT];
    int acc[2] = {0, 0};
    double e1[2] = {0, 0};
    if (paths > MAXPATHS)
        paths = MAXPATHS;
    /* 16 scales from 4 to 4,095, so that 8 steps fit in 16 bits. */
    for (k = 0; k < SCALES; k++)
        STEP[k] = (int)lround(4 * pow(4095.0 / 4, k / 15.0));
    for (frame = 0; fread(in, 4, PAIRS, stdin) == PAIRS; frame++)
    {
        int at = 0, blk, ch;
        for (ch = 0; ch < 2; ch++)
        {
            out[at++] = acc[ch];
            out[at++] = acc[ch] >> 8;
        }
        for (blk = 0; blk < BLOCKS; blk++)
        {
            int first = blk * BLOCK, n = PAIRS - first < BLOCK ? PAIRS - first : BLOCK, i;
            unsigned char codes[2][BLOCK];
            int scale[2];
            for (ch = 0; ch < 2; ch++)
            {
                double g[SCALES], best = 1e300;
                int order[SCALES], t;
                for (k = 0; k < SCALES; k++)
                {
                    g[k] = greedy(in + first * 2 + ch, n, 2, k, acc[ch], e1[ch], shaping);
                    order[k] = k;
                }
                for (k = 0; k < SCALES; k++)
                    for (t = k + 1; t < SCALES; t++)
                        if (g[order[t]] < g[order[k]])
                        {
                            int s = order[k];
                            order[k] = order[t];
                            order[t] = s;
                        }
                for (t = 0; t < TRIES; t++)
                {
                    unsigned char c[BLOCK];
                    int a;
                    double e, cost = search(in + first * 2 + ch, n, 2, order[t], acc[ch], e1[ch], shaping, paths,
                                            c, &a, &e);
                    if (cost < best)
                    {
                        best = cost;
                        scale[ch] = order[t];
                        memcpy(codes[ch], c, n);
                    }
                }
                /* Run the chosen codes to carry the state on exactly. */
                for (i = 0; i < n; i++)
                {
                    double target = in[(first + i) * 2 + ch] - shaping * e1[ch];
                    acc[ch] += delta(scale[ch], codes[ch][i]);
                    e1[ch] = acc[ch] - target;
                }
            }
            out[at++] = scale[0] << 4 | scale[1];
            for (i = 0; i < n; i++)
                out[at++] = codes[0][i] << 4 | codes[1][i];
        }
        fwrite(out, 1, FRAME_OUT, stdout);
    }
    return 0;
}

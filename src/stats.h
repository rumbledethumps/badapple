/* Measurements for the test build, BADAPPLE_TEST, printed every five
 * seconds. In the normal build these do nothing.
 *
 * VIA Timer 1 counts PHI2 cycles down from $FFFF and starts over, and
 * stats_poll() adds up how far it went, so the main loop must call it at
 * least once a lap, 8 ms at 8 MHz. A blocking call can hold the loop up
 * longer, so the VSYNC gap after one is not counted. */

#ifndef STATS_H
#define STATS_H

#include <stdint.h>

#ifdef BADAPPLE_TEST
#include <rp6502.h>
#include <stdbool.h>
#include <stdio.h>
#include <unistd.h>

#define VSYNC_HZ 60 /* VGA timing, 25.2 MHz / (800 x 525) */
#define VSYNC_SLOP_US 200

static uint32_t clock_now; /* PHI2 cycles */
static uint16_t clock_last;
static long phi2_khz;
static uint32_t vsync_at;

static struct
{
    uint32_t start;
    bool skip;          /* do not count the next VSYNC gap */
    uint16_t vsyncs;
    uint32_t gap_min, gap_max;
    uint16_t gaps_off;  /* VSYNC gaps more than VSYNC_SLOP_US from 1/60 s */
    uint16_t due[3];    /* VSYNCs with a frame due, by frames loaded ahead; 0 repeats a frame */
    uint16_t reads;
    uint32_t bytes;
    uint32_t read_cycles, read_at, read_max;
    long low;           /* the fewest bytes left in the PCM device at the end of a read */
} stats;

static void stats_poll(void)
{
    uint8_t hi, lo;
    uint16_t t;
    do
    {
        hi = VIA.t1_hi;
        lo = VIA.t1_lo;
    } while (VIA.t1_hi != hi);
    t = lo | hi << 8;
    clock_now += (uint16_t)(clock_last - t);
    clock_last = t;
}

static unsigned long us(uint32_t cycles)
{
    return cycles * 1000 / phi2_khz;
}

static unsigned long ms(uint32_t cycles)
{
    return cycles / phi2_khz;
}

static void stats_reset(void)
{
    stats = (typeof(stats)){0};
    stats.skip = true;
    stats.gap_min = UINT32_MAX;
    stats.low = 4096;
}

/* At the start of every pass. */
static void stats_start(void)
{
    phi2_khz = ria_attr_get(RIA_ATTR_PHI2_KHZ);
    VIA.acr = (VIA.acr & 0x3F) | 0x40;
    VIA.t1l_lo = 0xFF;
    VIA.t1l_hi = 0xFF;
    VIA.t1_lo = 0xFF;
    VIA.t1_hi = 0xFF;
    clock_last = 0xFFFF;
    stats_reset();
}

/* At every VSYNC that the main loop sees. */
static void stats_vsync(void)
{
    uint32_t gap = clock_now - vsync_at, want = phi2_khz * 1000 / VSYNC_HZ,
             slop = phi2_khz * VSYNC_SLOP_US / 1000;
    vsync_at = clock_now;
    if (stats.skip)
    {
        /* The five seconds start here, after the blocking call. */
        stats.skip = false;
        stats.start = clock_now;
        return;
    }
    ++stats.vsyncs;
    if (gap < stats.gap_min)
        stats.gap_min = gap;
    if (gap > stats.gap_max)
        stats.gap_max = gap;
    if (gap > want + slop || gap < want - slop)
        ++stats.gaps_off;
}

static void stats_due(uint8_t ahead)
{
    ++stats.due[ahead];
}

static void stats_read_start(void)
{
    stats.read_at = clock_now;
}

static void stats_read_done(int n, int pcm_fd)
{
    long level;
    uint32_t took = clock_now - stats.read_at;
    stats.read_cycles += took;
    if (took > stats.read_max)
        stats.read_max = took;
    level = lseek(pcm_fd, 0, SEEK_CUR);
    if (level < stats.low)
        stats.low = level;
    ++stats.reads;
    if (n > 0)
        stats.bytes += n;
}

/* Called right after a PCM write fills the device, so the print has the
 * device's 33 ms. */
static void stats_print(unsigned frame)
{
    unsigned long run_ms, read_ms;
    if (stats.vsyncs < 300)
        return;
    run_ms = ms(clock_now - stats.start);
    read_ms = ms(stats.read_cycles);
    printf("frame %u, %lu ms: VSYNC gaps %lu-%lu us, %u off; frame due %u times, "
           "2 ahead %u, 1 ahead %u, none %u\n",
           frame, run_ms, us(stats.gap_min), us(stats.gap_max), stats.gaps_off,
           stats.due[0] + stats.due[1] + stats.due[2], stats.due[2], stats.due[1], stats.due[0]);
    printf("  %u reads, %lu bytes, %lu ms reading, longest %lu us, %lu kB/s reading, "
           "%lu kB/s overall, PCM low %ld\n",
           stats.reads, stats.bytes, read_ms, us(stats.read_max),
           read_ms ? stats.bytes / read_ms : 0, run_ms ? stats.bytes / run_ms : 0, stats.low);
    stats_reset();
}
#else
static inline void stats_poll(void) {}
static inline void stats_start(void) {}
static inline void stats_vsync(void) {}
static inline void stats_due(uint8_t ahead) { (void)ahead; }
static inline void stats_read_start(void) {}
static inline void stats_read_done(int n, int pcm_fd) { (void)n; (void)pcm_fd; }
static inline void stats_print(unsigned frame) { (void)frame; }
#endif

#endif

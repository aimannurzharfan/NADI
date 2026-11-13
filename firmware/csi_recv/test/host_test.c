/*
 * Runs the receiver's feature and report code on a PC with made-up CSI:
 * a still room, the same room with one gain jump, and someone walking through; and the RSSI motion source.
 * Build and run (from firmware/csi_recv/test, any machine with gcc, e.g. the espressif/idf image):
 *   sh run_host_test.sh
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "csi_features.h"
#include "report.h"

#define PACKETS 1000  // 20 s at 50 packets per second
#define PI 3.14159265358979

static double noise(void)
{
    return ((double)rand() / RAND_MAX - 0.5) * 2.0;  // -1..1
}

/* One packet: two fixed paths (walls) plus, if walking, a third path whose length changes over time.
 * walking = packets per full phase turn of that path (0 = nobody): 40 is a slow shuffle, 4 a brisk walk. */
static void make_packet(int8_t *buf, int t, int walking, double gain)
{
    for (int k = 0; k < NADI_SUBCARRIERS; k++) {
        int sc = k < 32 ? k : k - 64;
        double re = 30 * cos(0.11 * sc) + 12 * cos(0.37 * sc + 1.0);
        double im = 30 * sin(0.11 * sc) + 12 * sin(0.37 * sc + 1.0);
        if (walking) {
            double phase = 0.23 * sc + 2 * PI * t / walking;
            re += 10 * cos(phase);
            im += 10 * sin(phase);
        }
        re = re * gain + noise();
        im = im * gain + noise();
        buf[2 * k] = (int8_t)lround(fmax(-127, fmin(127, im)));
        buf[2 * k + 1] = (int8_t)lround(fmax(-127, fmin(127, re)));
    }
}

static nadi_features_t run(int walking, int gain_jump, nadi_motion_source_t source)
{
    nadi_window_t w;
    nadi_window_init(&w);
    int8_t buf[2 * NADI_SUBCARRIERS];
    for (int t = 0; t < PACKETS; t++) {
        make_packet(buf, t, walking, gain_jump && t >= PACKETS / 2 ? 1.6 : 1.0);
        nadi_window_add(&w, buf, sizeof(buf), -50 - (t % 3));
    }
    nadi_features_t f;
    nadi_window_result(&w, source, &f);
    return f;
}

/* RSSI source on a fixed RSSI sequence, split over two windows like two reports. */
static void rssi_window(const int *rssi, int n, nadi_window_t *w, nadi_features_t *f)
{
    int8_t buf[2 * NADI_SUBCARRIERS];
    for (int t = 0; t < n; t++) {
        make_packet(buf, t, 0, 1.0);
        nadi_window_add(w, buf, sizeof(buf), rssi[t]);
    }
    nadi_window_result(w, NADI_MOTION_RSSI, f);
    nadi_window_reset(w);
}

static int failures;
static void check(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
    failures += !ok;
}

int main(void)
{
    srand(1);
    nadi_features_t still = run(0, 0, NADI_MOTION_CSI), jump = run(0, 1, NADI_MOTION_CSI), slow = run(40, 0, NADI_MOTION_CSI),
                    walk = run(4, 0, NADI_MOTION_CSI);
    printf("still:   motion_mean %.4f motion_std %.4f amp_var %.6f rssi %.1f n %lu\n", still.motion_mean,
           still.motion_std, still.amp_var, still.rssi_mean, (unsigned long)still.n_packets);
    printf("gain:    motion_mean %.4f motion_std %.4f amp_var %.6f\n", jump.motion_mean, jump.motion_std, jump.amp_var);
    printf("slow:    motion_mean %.4f motion_std %.4f amp_var %.6f\n", slow.motion_mean, slow.motion_std, slow.amp_var);
    printf("walking: motion_mean %.4f motion_std %.4f amp_var %.6f\n", walk.motion_mean, walk.motion_std, walk.amp_var);

    check(still.n_packets == PACKETS, "every packet is used");
    check(fabs(still.rssi_mean + 51.0) < 0.01, "rssi_mean is the average RSSI");
    check(walk.motion_mean > 3 * still.motion_mean, "walking raises motion_mean at least 3x");
    check(slow.motion_mean > 3 * still.motion_mean, "slow movement raises motion_mean at least 3x");
    check(walk.motion_std > 2 * still.motion_std && slow.motion_std > 2 * still.motion_std, "movement raises motion_std at least 2x");
    check(walk.amp_var > 10 * still.amp_var && slow.amp_var > 10 * still.amp_var, "movement raises amp_var at least 10x");
    check(jump.motion_mean < 1.5 * still.motion_mean, "a gain change alone is not motion");

    // RSSI source: -50, -51, -52 repeating gives std about sqrt(2/3) dB and mean step (1 + 1 + 2) / 3 dB
    srand(1);
    nadi_features_t r = run(4, 0, NADI_MOTION_RSSI);
    srand(1);
    nadi_features_t c = run(4, 0, NADI_MOTION_CSI);
    printf("rssi:    motion_mean %.4f motion_std %.4f amp_var %.6f\n", r.motion_mean, r.motion_std, r.amp_var);
    double sum = 0, sq = 0;
    for (int t = 0; t < PACKETS; t++) {
        sum += -50 - (t % 3);
        sq += (double)(-50 - (t % 3)) * (-50 - (t % 3));
    }
    double want = sqrt(sq / PACKETS - (sum / PACKETS) * (sum / PACKETS));
    check(fabs(want - sqrt(2.0 / 3)) < 1e-3 && fabs(r.motion_std - want) < 1e-9,
          "RSSI: motion_std is the RSSI standard deviation");
    check(fabs(r.motion_mean - 4.0 / 3) < 1e-3, "RSSI: motion_mean is the mean step between packets");
    check(r.amp_var == c.amp_var && r.rssi_mean == c.rssi_mean && r.n_packets == c.n_packets,
          "RSSI: amp_var, rssi_mean and n_packets are the same as with CSI amplitude");

    nadi_window_t rw;
    nadi_window_init(&rw);
    nadi_features_t f1, f2, f3;
    int flat[] = {-40, -40, -40, -40};
    int moving[] = {-37, -43, -37, -43};
    rssi_window(flat, 4, &rw, &f1);
    rssi_window(moving, 4, &rw, &f2);
    rssi_window(flat, 4, &rw, &f3);
    check(f1.motion_std == 0 && f1.motion_mean == 0, "RSSI: a steady signal gives 0");
    check(fabs(f2.motion_std - 3.0) < 1e-9, "RSSI: +-3 dB swings give motion_std 3 dB");
    check(fabs(f2.motion_mean - 5.25) < 1e-9, "RSSI: the step from the last packet of the window before counts: (3+6+6+6)/4");
    check(f3.motion_std == 0 && fabs(f3.motion_mean - 0.75) < 1e-9, "RSSI: back to steady, only the first step (3 dB) left");

    nadi_window_t empty;
    nadi_window_init(&empty);
    int8_t zeros[2 * NADI_SUBCARRIERS] = {0};
    check(nadi_window_add(&empty, zeros, sizeof(zeros), -50) != 0, "an all-zero buffer is ignored");
    check(nadi_window_add(&empty, zeros, 10, -50) != 0, "a short buffer is ignored");

    char json[512];
    nadi_health_t health = {"1.1.0", 3600, -55, 180000, 2};
    int n = nadi_csi_json(json, sizeof(json), "room1", 1761800000LL, &walk, &health);
    check(n > 0 && n < 4096, "report fits the 4 KB IoTDA limit");
    printf("%s\n", json);
    check(nadi_csi_json(json, 20, "room1", 0, &walk, &health) == -1, "a too-small buffer is reported, not overrun");

    // Fixed values: tests/test_firmware_contract.py expects exactly this line
    nadi_features_t fixed = {0.12345, 0.04567, 0.0007891, -48.25, 987};
    nadi_csi_json(json, sizeof(json), "room1", 1761800000LL, &fixed, &health);
    printf("fixed: %s\n", json);
    return failures ? 1 : 0;
}

#include "csi_features.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#define AVG_WEIGHT 0.02f  // weight of each new packet in the running average: about 50 packets, 1 s at 50 per second

/* LLTF subcarrier index i: 0..31 = subcarriers 0..31, 32..63 = -32..-1.
 * Not used: 0 (DC), 1 (can sit in the first word, which the radio marks invalid on some packets)
 * and 27..37 (guard bands +27..+31 and -32..-27). 51 remain. */
static int used(int i)
{
    return i > 1 && (i < 27 || i > 37);
}

void nadi_window_init(nadi_window_t *w)
{
    memset(w, 0, sizeof(*w));
}

void nadi_window_reset(nadi_window_t *w)
{
    float avg[NADI_SUBCARRIERS];
    int have_avg = w->have_avg, prev_rssi = w->prev_rssi, have_prev = w->have_prev;
    memcpy(avg, w->avg, sizeof(avg));
    nadi_window_init(w);
    memcpy(w->avg, avg, sizeof(avg));
    w->have_avg = have_avg;
    w->prev_rssi = prev_rssi;
    w->have_prev = have_prev;
}

int nadi_window_add(nadi_window_t *w, const int8_t *buf, int len, int rssi)
{
    if (!buf || len < 2 * NADI_SUBCARRIERS) {
        return -1;
    }
    float amp[NADI_SUBCARRIERS] = {0};
    double total = 0;
    int n = 0;
    for (int i = 0; i < NADI_SUBCARRIERS; i++) {
        if (!used(i)) {
            continue;
        }
        float im = buf[2 * i], re = buf[2 * i + 1];
        amp[i] = sqrtf(re * re + im * im);
        total += amp[i];
        n++;
    }
    double mean = total / n;
    if (mean < 1.0) {
        return -1;  // empty or broken buffer
    }

    double motion = 0;
    w->n_packets++;
    for (int i = 0; i < NADI_SUBCARRIERS; i++) {
        if (!used(i)) {
            continue;
        }
        float a = (float)(amp[i] / mean);
        if (w->have_avg) {
            motion += fabsf(a - w->avg[i]);
            w->avg[i] += AVG_WEIGHT * (a - w->avg[i]);
        } else {
            w->avg[i] = a;
        }
        double d = a - w->sc_mean[i];
        w->sc_mean[i] += d / w->n_packets;
        w->sc_m2[i] += d * (a - w->sc_mean[i]);
    }
    if (w->have_avg) {
        motion /= n;
        w->n_motion++;
        w->motion_sum += motion;
        w->motion_sq += motion * motion;
    }
    w->have_avg = 1;
    w->rssi_sum += rssi;
    w->rssi_sq += (double)rssi * rssi;
    if (w->have_prev) {
        w->diff_sum += abs(rssi - w->prev_rssi);
        w->n_diff++;
    }
    w->prev_rssi = rssi;
    w->have_prev = 1;
    return 0;
}

void nadi_window_result(const nadi_window_t *w, nadi_motion_source_t source, nadi_features_t *out)
{
    memset(out, 0, sizeof(*out));
    out->n_packets = w->n_packets;
    if (w->n_packets == 0) {
        return;
    }
    out->rssi_mean = w->rssi_sum / w->n_packets;
    if (source == NADI_MOTION_RSSI) {
        double var = w->rssi_sq / w->n_packets - out->rssi_mean * out->rssi_mean;
        out->motion_std = var > 0 ? sqrt(var) : 0;
        out->motion_mean = w->n_diff ? w->diff_sum / w->n_diff : 0;
    } else if (w->n_motion > 0) {
        out->motion_mean = w->motion_sum / w->n_motion;
        double var = w->motion_sq / w->n_motion - out->motion_mean * out->motion_mean;
        out->motion_std = var > 0 ? sqrt(var) : 0;
    }
    if (w->n_packets > 1) {
        double sum = 0;
        int n = 0;
        for (int i = 0; i < NADI_SUBCARRIERS; i++) {
            if (used(i)) {
                sum += w->sc_m2[i] / (w->n_packets - 1);
                n++;
            }
        }
        out->amp_var = sum / n;
    }
}

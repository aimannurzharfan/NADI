/*
 * Motion features over one report window, from the CSI of the sender's packets.
 * Plain C with no ESP-IDF calls, so it also builds and runs on a PC (see ../test/).
 *
 * motion_mean and motion_std come from one of two sources (menuconfig NADI_MOTION_SOURCE):
 *   RSSI (default)  motion_std  standard deviation of the packets' RSSI over the window, dB
 *                   motion_mean mean absolute difference between consecutive packets' RSSI, dB
 *   CSI amplitude   per packet, the amplitude of each used LLTF subcarrier divided by that packet's mean amplitude
 *                   (so automatic gain changes do not look like motion); motion = mean absolute difference between
 *                   those and their running average over about the last second
 *                   motion_mean average motion over the window, motion_std its standard deviation
 *                   On the boards the radio's automatic CSI scaling keeps amplitudes near 13 counts, which hid
 *                   people moving in the 2026-11-02 tests; RSSI reacted.
 * Either way:
 *   amp_var     variance over the window of each normalised amplitude, averaged over subcarriers
 *   rssi_mean   average signal strength, dBm
 *   n_packets   packets used
 */
#pragma once

#include <stdint.h>

#define NADI_SUBCARRIERS 64  // LLTF: 64 subcarriers, 2 bytes each (imaginary, real)

typedef struct {
    uint32_t n_packets;
    double rssi_sum;
    uint32_t n_motion;
    double motion_sum;
    double motion_sq;
    double rssi_sq;
    uint32_t n_diff;                   // consecutive RSSI differences (the previous packet is kept across windows)
    double diff_sum;
    int prev_rssi;
    int have_prev;
    double sc_mean[NADI_SUBCARRIERS];  // Welford running mean and M2 per subcarrier
    double sc_m2[NADI_SUBCARRIERS];
    float avg[NADI_SUBCARRIERS];       // running average (about 1 s), kept across windows
    int have_avg;
} nadi_window_t;

typedef enum {
    NADI_MOTION_CSI = 0,
    NADI_MOTION_RSSI = 1,
} nadi_motion_source_t;

typedef struct {
    double motion_mean;
    double motion_std;
    double amp_var;
    double rssi_mean;
    uint32_t n_packets;
} nadi_features_t;

void nadi_window_init(nadi_window_t *w);
/* Start a new window; keeps the running average and the last RSSI so motion stays continuous. */
void nadi_window_reset(nadi_window_t *w);
/* One CSI buffer (int8 pairs: imaginary, real) and its RSSI. Returns 0 if the packet was used. */
int nadi_window_add(nadi_window_t *w, const int8_t *buf, int len, int rssi);
void nadi_window_result(const nadi_window_t *w, nadi_motion_source_t source, nadi_features_t *out);

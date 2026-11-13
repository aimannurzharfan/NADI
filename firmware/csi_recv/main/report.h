/*
 * The one message the receiver publishes per window: IoTDA property report, service "csi".
 * Same topic and JSON in local mode (Mosquitto) and huawei mode (IoTDA); see the project brief, "Data contracts".
 * sim/fake_board.py reads NADI_CSI_JSON_FMT from this file, so keep it on one line.
 */
#pragma once

#include <stddef.h>

#include "csi_features.h"

#define NADI_REPORT_TOPIC_FMT "$oc/devices/%s/sys/properties/report"
#define NADI_CSI_JSON_FMT "{\"services\":[{\"service_id\":\"csi\",\"properties\":{\"room_id\":\"%s\",\"ts\":%lld,\"motion_mean\":%.4f,\"motion_std\":%.4f,\"amp_var\":%.6f,\"rssi_mean\":%.1f,\"n_packets\":%lu,\"fw_version\":\"%s\",\"uptime_s\":%lu,\"wifi_rssi\":%d,\"free_heap\":%lu,\"dropped\":%lu}}]}"

/* Board health sent with every report, for the dashboard's sensor list (no extra messages). */
typedef struct {
    const char *fw_version;
    unsigned long uptime_s;
    int wifi_rssi;           // dBm of the access point, 0 if unknown
    unsigned long free_heap;  // bytes
    unsigned long dropped;    // CSI packets lost in this window because the receiver was busy
} nadi_health_t;

/* Returns the JSON length, or -1 if it did not fit in out. */
int nadi_csi_json(char *out, size_t size, const char *room_id, long long ts, const nadi_features_t *f,
                  const nadi_health_t *h);

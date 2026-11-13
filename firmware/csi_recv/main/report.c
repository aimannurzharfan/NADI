#include "report.h"

#include <stdio.h>

int nadi_csi_json(char *out, size_t size, const char *room_id, long long ts, const nadi_features_t *f,
                  const nadi_health_t *h)
{
    int n = snprintf(out, size, NADI_CSI_JSON_FMT, room_id, ts, f->motion_mean, f->motion_std, f->amp_var,
                     f->rssi_mean, (unsigned long)f->n_packets, h->fw_version, h->uptime_s, h->wifi_rssi,
                     h->free_heap, h->dropped);
    return (n < 0 || (size_t)n >= size) ? -1 : n;
}

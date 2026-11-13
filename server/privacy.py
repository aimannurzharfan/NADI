"""Delete every stored record, for a PDPA request (see PRIVACY.md). Used by POST /api/data/delete (admin) and
scripts/delete_all_data.py. Both need the typed confirmation (CONFIRM, or its Malay
form) and refuse while emergency mode or a drill is on.

Deleted: history (MySQL occupancy and climate), live counts and device health (Redis/Valkey), alerts and their
acknowledgements, the audit log, incident and drill reports with their snapshots (INCIDENT_DIR), headcount labels
(ml/data/labels.csv) and the training table made from them (ml/data/train.csv).
Kept: settings in .env, the trained model (weights only, no readings), rate-limit counters, and log files
(LOG_FILE and Docker's container logs rotate on their own; delete them by hand if needed).
"""
from pathlib import Path

from server import energy, incident, labels, store
from server.strings import t

CONFIRM = t("privacy.phrase", "en")  # "DELETE ALL DATA"; the Malay page asks for "PADAM SEMUA DATA"
PHRASES = {t("privacy.phrase", "en"), t("privacy.phrase", "ms")}
REDIS_KEYS = ("rooms", "alerts", "alert_ack", "audit", "devices", "sensor_state", "iotda_last_push")
REDIS_PATTERNS = ("room:*", "device:*", "device_rooms:*", "device_services:*", "waste_rm:*", "waste_rm_h:*", "waste_kwh:*", "waste_co2:*",
                  "seen:*", "pending_count:*", "suspicious_alert:*", "devrate:*", "incident:*")
TRAIN = Path(__file__).resolve().parent.parent / "ml" / "data" / "train.csv"


class Refused(Exception):
    pass


def delete_all(confirm):
    """Delete everything listed above. Raises Refused for a wrong confirmation or during an emergency.
    Returns what was removed: {"redis_keys", "occupancy", "climate", "incidents", "files"}."""
    if confirm not in PHRASES:
        raise Refused("confirmation")
    if store.emergency()["on"]:
        raise Refused("emergency")
    n = store.r.delete(*REDIS_KEYS)
    for pattern in REDIS_PATTERNS:
        keys = list(store.r.scan_iter(pattern, count=500))
        for i in range(0, len(keys), 500):
            n += store.r.delete(*keys[i:i + 500])
    with store._buffer_lock:
        store._buffer.clear()
    rows = {}
    with store.mysql() as conn, conn.cursor() as cur:
        for table in ("occupancy", "climate"):
            rows[table] = cur.execute(f"DELETE FROM {table}")
        cur.execute(energy.TABLE)  # the saved energy settings name who changed them: they go too, defaults apply again
        cur.execute("DELETE FROM energy_settings")
    energy.reset()
    files = 0
    for path in (labels.path(), TRAIN):
        if path.exists():
            path.unlink()
            files += 1
    return {"redis_keys": n, **rows, "incidents": incident.delete_all(), "files": files}

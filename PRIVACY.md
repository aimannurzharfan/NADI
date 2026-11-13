# Privacy

NADI is designed so that only a number per room leaves the room.

## What NADI collects

| Data | Collected | Detail |
|---|---|---|
| Headcount per room (0, 1, 2 or 3+ from Wi-Fi sensing; 0 to 1000 from an optional people counter) | Yes | Worked out from the readings below |
| Wi-Fi signal features | Yes | Five numbers per room every 20 seconds: average and spread of signal changes, signal strength, packet count. They describe movement in the room, not who is moving. |
| Temperature and humidity per room | Yes | From the climate node, every 60 seconds |
| Which board sent a reading | Yes | The board's device ID (for example `nadi-recv-1`), so training data can be checked |
| Images, video or sound | **No** | There are no cameras or microphones |
| Names or identities | **No** | |
| MAC addresses, phone or device tracking | **No** | The receiver only listens to the NADI sender board's packets and keeps no packet contents |
| Raw Wi-Fi packets | **No** | Processed on the board; only the five numbers are sent |

The admin-only audit log records which admin token (by its label, such as `warden1`), from which IP address and at what time, started or ended emergency mode or a drill, marked a room during one, or deleted all stored data. The public dashboard shows only the label and the time.

Incident and drill reports and their snapshots hold counts per room, times, and the labels of the wardens who marked rooms or acknowledged alerts. They hold no IP addresses.

## Where it is stored and for how long

| Where | What | How long |
|---|---|---|
| Valkey (local Docker, or Huawei DCS for Redis) | Current count, temperature and emergency state per room; last 200 alerts; last 200 audit entries; rate-limit counters per IP address (one minute) and lockouts (15 minutes) | Live values are replaced by each new reading; alerts and audit entries roll over at those limits; counters expire by themselves |
| MySQL (local Docker, or Huawei RDS) | Every reading, for history and model training | **Deleted automatically after `HISTORY_RETENTION_DAYS` (default 90)**, once a day in small batches. `scripts/reset_demo_data.py --yes` clears all of it (local mode only) |
| Server log (console, and `LOG_FILE` if set) | Start-up messages, rejected reports with the device ID, alerts, wrong-token lockouts with the IP address | `LOG_FILE` rotates at `LOG_MAX_MB` (10 MB) with 5 old files kept; Docker keeps 3 x 10 MB per service |
| `ml/data/labels.csv` | Training labels: room, start and end time, headcount | Until deleted; never committed to git |
| `data/incidents/` (`INCIDENT_DIR`) | One folder per emergency or drill: the report, and a snapshot every minute (JSON and printable HTML) | Until deleted; never committed to git. The demo scenario keeps only its last 5 |

All times are stored as Unix time (UTC) and shown in Malaysia time.

In local mode nothing leaves the computer running NADI. In Huawei Cloud mode the data is stored in the team's own Huawei Cloud account, in the region chosen at set-up.

## Malaysia's Personal Data Protection Act (PDPA)

NADI does not collect names, images or device identifiers of people, and a headcount on its own does not identify anyone. Even so:

- **Ask before collecting.** Get permission from the building owner and tell people in the room before installing boards or collecting training data (for example, a notice on the door: "Occupancy sensors in use: counts only, no cameras").
- **Labelling sessions** record who was in the room only as a number; do not write names in labels or notes.
- **Audit log IP addresses** may be personal data: keep the admin token private and delete audit entries that are no longer needed.
- Do not collect data on a network or in a building without written permission from whoever is responsible for it.

## Deleting everything (a PDPA request)

When someone asks for their data to be deleted, or a pilot ends, delete every stored record:

- **In the console:** Alerts page, **Delete all stored data** (admin only). Type `DELETE ALL DATA` (or `PADAM SEMUA DATA` on the Malay page) and press **Delete everything**.
- **Without the server running:** `python scripts/delete_all_data.py`, which asks you to type the same phrase.

Both refuse while emergency mode or a drill is on. They delete every reading in MySQL (occupancy and climate), live counts and board health in Valkey, all alerts and acknowledgements, the whole audit log, every incident and drill report and snapshot, `ml/data/labels.csv` and `ml/data/train.csv`. One audit entry remains: who deleted everything, and when.

They do **not** delete the server log file (`LOG_FILE`) or Docker's container logs (both rotate by themselves; delete them by hand if they must go now), the settings in `.env`, the trained model (its weights hold no readings), or `ml/data/labels_synth.csv` (made-up labels from `ml/synth_labels.py`).

This is not legal advice; check with your organisation's data protection officer before a real deployment.

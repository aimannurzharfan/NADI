# Real board test results, 2 November 2026

First tests on real hardware. Every number below was measured tonight; nothing is simulated or estimated. Where something was not measured or not tested, it says so.

## Setup

| Item | Value |
|---|---|
| Boards | 2 for occupancy: SEND-1 (`firmware/csi_send`) and RECV-1 (`firmware/csi_recv`), plus CLIMATE-1 (`firmware/climate_node`, DHT22) |
| Hardware | ESP32-S3 DevKitC-1 N16R8 (CP2102 USB-serial), each on a USB charger |
| Distance between SEND-1 and RECV-1 | 3 to 4 m |
| Height | Not recorded |
| Network | A 2.4 GHz phone hotspot, channel 11; laptop runs Mosquitto, Valkey, MySQL and the server in local mode |
| Radio link | 50 packets per second from SEND-1; RECV-1 sends one report every 10 s with 488 to 498 packets; RSSI at RECV-1 about -51 dBm |
| Set-up | Each board flashed and configured with `scripts/provision.py` (all checks PASS) |

### Motion feature: RSSI, not CSI amplitude

The receiver now computes `motion_std` and `motion_mean` from the RSSI of SEND-1's packets (menuconfig "Motion features from", default RSSI):

- `motion_std`: standard deviation of the packets' RSSI over the 10 s report window, in dB
- `motion_mean`: mean absolute change in RSSI between consecutive packets, in dB
- `amp_var`, `rssi_mean`, `n_packets` and all field names are unchanged, so the server, calibration and dashboard did not change.

The first method, CSI subcarrier amplitude, is still available in menuconfig. It was dropped for tonight because it did not react to people:

| Test (CSI amplitude feature) | Result |
|---|---|
| Walk test, boards close together (RSSI about -35 dBm) | walking / empty `motion_std` = 0.70 |
| Hand waved 10 cm from RECV-1, 30 s each | waving / still `motion_std` = 1.48 |

Raw CSI captured from RECV-1 (about 25 packets per second, 10 to 12 s per step) showed the data itself was well-formed: every packet HT, MCS 0, 20 MHz, 128 bytes (LLTF only), null subcarriers exactly where the code expects them (0 and 27 to 37), no saturated values. But the CSI amplitude did not follow clear changes in the radio channel:

| Step | RSSI std (dB) | RSSI range (dB) | Normalised amplitude variation | Mean amplitude std |
|---|---|---|---|---|
| Still | 0.23 | 2 | 0.0319 | 0.570 |
| Hand on and off RECV-1's antenna | 1.99 (x8.5) | 7 | 0.0432 (x1.4) | 0.569 (x1.0) |
| SEND-1 carried around | 3.11 (x13.4) | 17 | 0.0356 (x1.1) | 0.581 (x1.0) |

The mean CSI amplitude stayed at about 13 counts while RSSI moved by 17 dB. The cause is not confirmed. The first thing to try is manual CSI scaling (`manu_scale`) in the receiver's CSI settings.

## Walk test (RSSI feature, boards 3 to 4 m apart)

Reports read from the server (MySQL), 60 s per phase.

| Phase | Reports | `motion_std` per report (dB) | Average `motion_std` | Average `motion_mean` |
|---|---|---|---|---|
| Empty, reports 4 to 7 (settled) | 4 | 0.2452, 0.3168, 0.3051, 0.2843 | 0.2878 | 0.0726 |
| One person walking through the line every 2 to 3 s | 6 | 2.8487, 2.1379, 3.2534, 2.5585, 2.4717, 2.5196 | 2.6316 | 0.4254 |

- Walking / empty: **`motion_std` 9.1x**, `motion_mean` 5.9x.
- The first three empty reports (0.4720, 0.5026, 0.7467) were left out: the first one's window started before the phase, and the area was still settling.

## Calibration

Labels made through the `/label` page's API (`/api/labels`), 2 minutes each, then `scripts/calibrate.py --room room1`.

| Label | Reports | Lowest | Highest | 10th / 50th / 90th percentile |
|---|---|---|---|---|
| 0 (empty) | 11 | 0.1002 | 0.7214 | 0.1689 / 0.4822 / 0.6357 |
| 1 (one person) | 12 | 1.8960 | 2.8645 | 1.966 / 2.396 / 2.834 |

- Result: **`HEADCOUNT_THRESHOLDS=1.301,99,99`** (empty versus occupied), **100% on the 23 labelled reports**. `MODEL_PATH=off`.
- One more empty report (1.5654) was left out: its 10 s window started before the label did.

## Live check on new data

Three phases of 40 s, after calibration. The dashboard headcount was read every second (141 reads, none failed). The first report after each change was not scored, as agreed before the test.

| Phase | Expected | Scored reports correct | `motion_std` of scored reports (dB) |
|---|---|---|---|
| Empty | 0 | 3/3 | 0.7306, 0.5269, 0.5109 |
| One person (walking through the line, sometimes standing and moving arms) | 1 | 3/3 | 1.8482, 2.1757, 1.6186 |
| Empty | 0 | 3/3 | 0.4629, 0.5142, 0.6062 |

- **9/9 scored correct; 12/12 including the unscored first reports.**
- Dashboard lag: **10.9 s** (empty to one person) and **10.6 s** (one person to empty), about one report interval.

## Climate and air conditioning waste

- CLIMATE-1 (DHT22) next to the laptop read 26.3 C.
- Moved into open room air in an air-conditioned cafe, it read 25.9, 25.4, 24.9, 24.8 and 24.7 C over 4 minutes (one report a minute), settling at **24.7 C**.
- The server counts the air conditioning as on below 26.0 C. With room1 empty, the waste alert was raised at 19:36:42: "Demo Room has been empty with the air conditioning on for 1 minute (24.9 C). About RM0.06 wasted so far." This used `WASTE_MINUTES=1`, the stage demo setting; the normal setting is 10.

## Recorded waves (per-packet signal strength)

The room panel of the console can show recorded waves: the RSSI of every packet between the two boards, about 50 a
second, for a still room and for a person walking through the line.

- **No recording is in the repository yet.** The raw per-packet captures from the 2 November diagnostic session
  (still room, hand wave, sender moved) were kept in a temporary folder that has since been cleared, so they cannot
  be shown. The figures from that session quoted above stand, but there are no packets to draw.
- Until a recording exists, the room panel shows the sensor pair picture and the live signal only.
- How a recording is made: the receiver is flashed with a diagnostic build that prints one line per packet
  (time and RSSI, nothing else), `python scripts/record_waves.py --room room1 --kind empty --seconds 15 --distance <metres>`
  saves it to `web/public/recordings/`, the same again with `--kind walk`, and the normal firmware is put back with
  `python scripts/provision.py --role recv`.
- Each recording used will be listed here with its date, the distance between the boards, the packet count and the
  measured spread (standard deviation, dB).

| Recording | Date | Setup | Packets | Spread (std, dB) |
|---|---|---|---|---|
| none yet | | | | |

## Known limits

- **Standing still has a thin margin.** In the live check, one person standing and moving their arms read 1.45 to 2.18 dB; the lowest was 0.15 dB above the 1.301 threshold. A person sitting still was not tested and may read as empty.
- **A single spike can show "occupied" for one report.** The excluded empty report (1.5654) is above the threshold.
- **Counts above 1 are not supported.** Only 0 and 1 were calibrated; the thresholds for 2 and 3+ are set to 99, so the dashboard shows at most 1 for this room.
- **Turning the air conditioner off is a manual command, not automatic.** `python scripts/send_command.py` sends `ac_off` to CLIMATE-1; the server does not send it, and there is no dashboard button. Recording the remote's off code (`learn`) and sending it were not tested tonight.
- **The air conditioning rule uses temperature only.** It cannot tell a running air conditioner from a room that is naturally below 26.0 C.
- **Recalibrate after moving the boards.** The threshold belongs to this placement.

## Not tested tonight

Huawei Cloud mode, MQTT over TLS, more than one room, emergency mode with real boards, and infrared learn and send.

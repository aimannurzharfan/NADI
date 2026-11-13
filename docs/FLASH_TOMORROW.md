# Board day checklist: flash and set up

**Quick path.** Fill `NADI_WIFI_SSID` and `NADI_WIFI_PASS` in `.env` (the 2.4 GHz hotspot), join the hotspot, set `MQTT_LAN_IP` to the laptop's hotspot IP, `docker compose up -d --wait`. Then plug in **one** board at a time and run, in this order:

```powershell
.\.venv\Scripts\python scripts\provision.py --role send      # SEND-1
.\.venv\Scripts\python scripts\provision.py --role recv      # RECV-1 (SEND-1 on a charger or power bank, not the laptop)
.\.venv\Scripts\python scripts\provision.py --role climate   # CLIMATE-1
```

Each one finds the board's port (CP2102, or CH340 on some boards), flashes, answers `setup` from `.env` (passwords never shown), reads the log for 40 s and prints a PASS/FAIL table. If it says "Hold BOOT, tap RST, release BOOT, then press Enter", do that. Settings only, no flashing: add `--skip-flash`. SEND-1's MAC and channel go to `data\provision\sender.json`, which the RECV-1 run compares against. The manual steps below are the fallback.

Boards: 3x ESP32-S3-DevKitC-1 N16R8 clones (CP2102 USB-serial chip, CH340 on some; two USB-C ports) and one DHT22 module.
Everything is already built: `firmware\csi_send\build\merged.bin`, `firmware\csi_recv\build\merged.bin`, and the climate sketch compiles with arduino-cli. Run every command from the repo root in PowerShell. Never write passwords on paper or in this file: read them from `.env`.

| Label | Folder | Device ID | Room |
|---|---|---|---|
| SEND-1 | `firmware\csi_send` | (none, it does not use MQTT) | |
| RECV-1 | `firmware\csi_recv` | `nadi-recv-1` | `room1` |
| CLIMATE-1 | `firmware\climate_node` | `nadi-climate-1` | `room1` |

1. **USB port.** Always use the USB-C port labelled **UART**, with a data cable. The other port is the chip's own USB and shows nothing useful.
2. **COM number.** Device Manager > Ports (COM & LPT) > `Silicon Labs CP210x USB to UART Bridge (COMx)` (on a CH340 board: `USB-SERIAL CH340 (COMx)`). Or `.\.venv\Scripts\python -m serial.tools.list_ports -v`. Plug in one board at a time and stick its label on it.
3. **Flash** (replace `COMx`):
   - SEND-1: `.\.venv\Scripts\python -m esptool --chip esp32s3 -p COMx -b 460800 write_flash 0x0 firmware\csi_send\build\merged.bin`
   - RECV-1: `.\.venv\Scripts\python -m esptool --chip esp32s3 -p COMx -b 460800 write_flash 0x0 firmware\csi_recv\build\merged.bin`
   - CLIMATE-1 (`secrets.h` already exists, no passwords in it):
     `arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=default,UploadMode=default,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,FlashMode=dio firmware\climate_node`
     `arduino-cli upload -p COMx --fqbn esp32:esp32:esp32s3:CDCOnBoot=default,UploadMode=default,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,FlashMode=dio firmware\climate_node`
   - Pass: `Hash of data verified.` Then press **RST**.
4. **"Failed to connect" recovery.** Hold **BOOT**, press and release **RST**, release **BOOT**, run the flash command again. Still failing: retry with `-b 115200`, then try another cable. Press RST after flashing.
5. **Serial log.** `.\.venv\Scripts\python -m serial.tools.miniterm COMx 115200` (quit: `Ctrl+]`). Press RST to see it from the start.
6. **Laptop IP for the boards.** Join the demo hotspot (2.4 GHz). `ipconfig` > "Wireless LAN adapter Wi-Fi" > "IPv4 Address". Put it in `.env` as `MQTT_LAN_IP=`, then `docker compose up -d --wait`. Check: `docker compose ps mosquitto` shows `<that IP>:1883`. Set the hotspot to **Private** in Windows Wi-Fi settings. If the firewall rule is still missing, in an **Administrator** PowerShell: `New-NetFirewallRule -DisplayName "NADI MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Private`
7. **`setup` on each board** (type `setup`, Enter; Enter alone keeps the value in brackets; the board restarts after saving):
   - SEND-1: Wi-Fi name the receiver uses; fallback channel (leave 6). No password needed.
   - RECV-1 and CLIMATE-1: Wi-Fi name; Wi-Fi password; broker address = `MQTT_LAN_IP`; broker port `1883`; MQTT password = `MQTT_PASSWORD_NADI_RECV_1` or `MQTT_PASSWORD_NADI_CLIMATE_1` from `.env`; room ID `room1`.
   - Type `show` to check (passwords show as `********`).
8. **LED colours** (GPIO 48; no LED at all means the board uses 38: receiver/sender `cd firmware\csi_recv` then `..\idf.ps1 menuconfig` > Status LED pin > 38, `..\idf.ps1 build`, flash again; climate `#define LED_PIN 38` in `secrets.h`):

   | Colour | RECV-1 | SEND-1 | CLIMATE-1 |
   |---|---|---|---|
   | Red | No Wi-Fi | Cannot start | No Wi-Fi |
   | Yellow | Wi-Fi, no MQTT broker | | Wi-Fi, no MQTT broker |
   | Purple | No CSI from the sender for 3 s | | DHT22 not answering |
   | Green steady | Working | | Working |
   | Green blink 1/s | | Sending packets | |
   | Blue blink | Report sent | | Climate report sent |

9. **Pair check.** Sender log: `Found the Wi-Fi network "..." on channel N` and `Sent 500 packets ... in the last 10 s`. Receiver log: same channel N, then one `Report sent:` every **10 s** with about **500 packets**.
10. **Walk test** (sender and receiver 3 to 5 m apart, chest height; do not move them afterwards). Start the server (`.\.venv\Scripts\python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --limit-concurrency 200 --timeout-keep-alive 5`). From the receiver log write down `motion_std`:
    - E: 3 reports with nobody near the line.
    - W: 3 reports while walking back and forth across the line.
    - S: 3 reports with one person sitting and typing.
    - Pass: W several times bigger than E, and back near E within 1 or 2 reports after stepping away.
11. **Label and calibrate.** On the laptop open http://127.0.0.1:8000/calibration (the **Calibration** page, at the bottom of the sidebar): in **Label headcount**, pick the room, tap **0** for 2 minutes of empty room, then **1** for 2 minutes of walking, then **Stop**. Then:
    `.\.venv\Scripts\python scripts\calibrate.py --room room1`
    Copy the printed `HEADCOUNT_THRESHOLDS=...` line into `.env` and restart the server. (`MODEL_PATH=off` is already set.)

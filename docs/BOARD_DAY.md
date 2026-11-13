# Board day: from unboxing to a live room

One ordered checklist. Times are estimates for a first run; detail for each step is in [firmware/README.md](../firmware/README.md). Do it at home first, then repeat steps 9 to 14 at UTM and at the venue (only `setup` changes, no reflashing).

| # | Step | Expected result | LED | Time |
|---|---|---|---|---|
| 1 | **Unbox and inspect.** 3 DevKitC-1 boards, DHT22, KY-022, KY-005, data cables, charger. Check the KY-005 has a small resistor; note which pin is S, -, +. | Nothing loose or bent | | 10 min |
| 2 | **Laptop ready.** Docker Desktop running, `docker compose up -d --wait`, `python -m pip install esptool==4.8.1`, ESP-IDF image pulled once (`docker pull espressif/idf:v5.4.1`, about 11 GB). | `docker compose ps` shows redis, mysql, mosquitto running | | 15 min (+ download) |
| 3 | **Broker logins.** `.env`: `MQTT_LAN_IP` = laptop Wi-Fi IPv4 (`ipconfig`), `MQTT_DEVICE_IDS=nadi-sim,nadi-recv-1,nadi-climate-1`, `DEVICE_ROOMS=nadi-sim:*,nadi-recv-1:room1,nadi-climate-1:room1`. Run `python scripts\mqtt_users.py`, then `docker compose up -d --force-recreate mosquitto`. | `Wrote deploy\mosquitto\passwd with nadi-server and 3 device(s)` | | 5 min |
| 4 | **Firewall.** Wi-Fi profile set to Private; allow TCP 1883 (firmware README section 1, step 5). | | | 3 min |
| 5 | **Find each board's COM port.** Plug into the port marked COM. Device Manager > Ports. Label each board with tape: SEND, RECV, CLIMATE. | A new `COMx` per board | | 5 min |
| 6 | **Flash the sender.** `cd firmware\csi_send`, `..\idf.ps1 build`, then `python -m esptool --chip esp32s3 -p COM5 -b 460800 write_flash 0x0 build\merged.bin`. | `Hash of data verified.` | | 10 min |
| 7 | **Sender log.** `python -m serial.tools.miniterm COM5 115200`, press RST. Type `setup`: your 2.4 GHz Wi-Fi name, channel 6. | `NADI CSI sender 1.1.0 is starting.` then `Found the Wi-Fi network "..." on channel N.` and `Sent 500 packets ... in the last 10 s.` | Green blink once a second | 5 min |
| 8 | **Flash the receiver.** `cd firmware\csi_recv`, `..\idf.ps1 build`, flash to its port. | `Hash of data verified.` | Red (no settings yet) | 10 min |
| 9 | **Receiver setup.** Open its serial port, type `setup`: Wi-Fi name and password, broker address (**Sensors** page > **Board address**, admin), port 1883, password `MQTT_PASSWORD_NADI_RECV_1` from `.env`, room `room1`. | `Saved. Restarting in 2 s.` | Red, then yellow | 5 min |
| 10 | **Receiver online.** Watch the log after the restart. | `Connected to "..." on channel N` (same N as the sender), `Connected to the MQTT broker at ...`, then every 20 s `Report sent: ~1000 packets` | Yellow, then green; blue blink every 20 s | 2 min |
| 11 | **Climate node.** Arduino IDE settings from the firmware README (USB CDC On Boot: Disabled), copy `secrets.example.h` to `secrets.h`, upload. Serial Monitor 115200, "Newline". Type `setup` (password `MQTT_PASSWORD_NADI_CLIMATE_1`). | `Connected to the MQTT broker at ...` and `Climate report sent: 24.6 C, humidity 63.2%.` | Green; blue blink every 60 s | 20 min |
| 12 | **IR.** `irtest` while looking through a phone camera; then `learn` and press the remote's OFF (5 cm away); then `send` with the air conditioner on, from 1 to 2 m. | Flashes on the phone screen; `Recorded: protocol ...`; the unit switches off | White blinks | 10 min |
| 13 | **Dashboard.** Start the server and open http://127.0.0.1:8000. | room1 shows a count and a temperature and is not marked offline; the receiver and climate node appear as online in `GET /api/devices` (admin only: open it on the server computer, or send the admin token) | | 2 min |
| 14 | **Place the boards.** Sender and receiver 3 to 5 m apart, about 1 m high, across where people sit; DHT22 away from the board and the sun. Tape them down. | Receiver stays green (purple means the sender is out of range or off) | Green | 10 min |
| 15 | **Walk test.** Firmware README section 5: one minute still, one minute walking. | `motion_std` several times higher while walking | | 5 min |
| 16 | **Calibrate.** On the **Calibration** page (`/calibration`; the old `/label` address opens it), label a still period (0) and a walking period (1), then `python scripts\calibrate.py --room room1`. Put the printed `HEADCOUNT_THRESHOLDS=...` line in `.env`, set `MODEL_PATH=off`, restart the server. | Dashboard shows 0 when empty and 1+ when someone walks | | 15 min |

**Total:** about 2.5 hours the first time; about 15 minutes at a new site (steps 9 to 14 and a quick walk test).

**If something is wrong:** the LED tells you where to look. Red = Wi-Fi name or password (`setup`), yellow = broker address, password or firewall, purple = sender off, too far, or on a different channel (compare channels in both logs). The troubleshooting table in the firmware README lists every message.

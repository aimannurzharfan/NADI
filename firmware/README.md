# NADI firmware: flashing the boards on Windows

Three boards, all DIYMORE ESP32-S3 DevKitC-1 N16R8 (16 MB flash, 8 MB octal PSRAM):

| Folder | Board | Built with | What it does |
|---|---|---|---|
| `csi_send/` | Sender | ESP-IDF v5.4.1 (Docker) | Sends 50 small Wi-Fi packets a second on the Wi-Fi network's channel |
| `csi_recv/` | Receiver | ESP-IDF v5.4.1 (Docker) | Joins the Wi-Fi network, measures CSI from the sender, sends one report every 10 s (huawei mode: 20 s) |
| `climate_node/` | Climate node | Arduino IDE | DHT22 temperature every 60 s; switches the air conditioner off by IR on the command `ac_off` |

Each board has two USB-C ports. **Always use the one marked COM (or UART)**, for flashing and for the serial log.

Both modes use the same topic and JSON. Local mode (Mosquitto on the laptop) works today with no Huawei Cloud account; huawei mode (IoTDA over MQTTS) only changes the broker settings.

## Change settings without reflashing

menuconfig (and `secrets.h` for the climate node) only sets the **defaults**. On site, open the board's serial port at 115200 baud and type a command, then Enter:

| Command | What it does |
|---|---|
| `setup` | Asks for each setting in turn; Enter alone keeps the value in brackets. Receiver and climate node: Wi-Fi name, Wi-Fi password, broker address, broker port, MQTT password, room ID. Sender: Wi-Fi name and fallback channel. Saved in flash, then the board restarts. |
| `show` | Prints the settings. Passwords show as `********`. |
| `reset` | Forgets the saved settings, so the compiled defaults apply again. |
| `restart` | Restarts the board (receiver and sender). |

Passwords are never echoed: you see `*` for each character you type. Any serial terminal works: the Arduino Serial Monitor (line ending "Newline"), PuTTY, or `python -m serial.tools.miniterm COM5 115200`.

The address to type as **broker address** is shown on the dashboard: **Board address** in the footer (local mode, needs the admin token or the server computer). It also warns if Mosquitto is still listening on an old address.

Example on the receiver (`setup`, then answers):

```
Setup: type a new value and press Enter, or press Enter to keep the value in brackets.
Wi-Fi name (2.4 GHz) [HomeNet]: NADI-Hotspot
Wi-Fi password [********, Enter keeps it]: ***********
Broker address (the laptop IP shown on the dashboard) [192.168.1.50]: 192.168.1.60
Broker port [1883]:
MQTT password [********, Enter keeps it]:
Room ID (for example room1) [room1]:
Saved. Restarting in 2 s to use them.
```

## Status LED

The onboard RGB LED shows the board's state at a glance. It is on GPIO 48 by default; some DevKitC-1 versions use GPIO 38 (menuconfig "Status LED pin", or `LED_PIN` in `secrets.h`); `-1` turns it off.

| Colour | Receiver | Sender | Climate node |
|---|---|---|---|
| Red | No Wi-Fi | Cannot start (see the log) | No Wi-Fi |
| Yellow | Wi-Fi, but no MQTT broker | | Wi-Fi, but no MQTT broker |
| Purple | No CSI from the sender for 3 s | | The DHT22 does not answer |
| Green, steady | Working | | Working |
| Green blink, once a second | | Sending packets | |
| Blue blink | Report sent | | Climate report sent |
| White blink | | | IR code sent (also during `irtest`) |

## Self-recovery

- If Wi-Fi or the MQTT broker has been unreachable for **5 minutes**, the receiver and climate node print why and restart themselves (never while you are typing in `setup` or in learn mode).
- A task watchdog restarts a board whose main task is stuck for 30 seconds.
- The climate node waits at most 5 seconds for a broker that does not answer, so the serial commands and learn mode stay responsive.

## Health in every report

Each report also carries `fw_version`, `uptime_s`, `wifi_rssi`, `free_heap` and `dropped` (receiver: CSI packets lost in that report window; climate node: reports that could not be sent since start-up). No extra messages are sent, so the IoTDA budget is unchanged, and a report is about 300 bytes. The server keeps the latest values per board for the dashboard's sensor list (`GET /api/devices`, admin only).

## Wiring and placement tips

- **Breadboard:** the DevKitC-1 is too wide for one 830-hole breadboard (no free holes on one side). Use female-to-female jumpers straight onto the pins, or two breadboards side by side with the board across the gap.
- **KY-005 / KY-022 pin labels** differ between clones. Follow the printed **S** (signal), **-** (GND) and **+** (3.3 V) marks on your module, not a photo of another one.
- **KY-005 resistor:** check the module has a small resistor in series with the IR LED. If it has none, keep IR tests short (the LED and the GPIO are driven harder than they should be).
- **IR check with a phone camera:** type `irtest`; the IR LED flashes once a second for 10 s. Point a phone camera at it: you see a purple-white flash. Some phones filter IR on the main camera; try the front camera.
- **DHT22:** at least 10 cm from the board (the ESP32 warms up), out of direct sunlight and away from the air conditioner's outlet.
- **Sender and receiver:** 3 to 5 m apart, about 1 m high, so the line between them crosses where people sit. **Do not move them** between labelling and the demo: the readings depend on the exact positions.
- **Power banks** that switch off when the current is low can cut a board after a minute. Use a charger, or a power bank with an "always on" or low-current mode.

## Why the sender must use the network's channel

The receiver stays connected to the Wi-Fi network the whole time, because it sends its reports over MQTT. A Wi-Fi radio listens on one channel at a time, so the receiver only hears the sender if the sender is on the network's channel too. You do not set the channel by hand: give the sender the **network name** and it scans for it, uses its channel, and checks again every 5 minutes. The receiver prints the channel it is on, and the sender prints the channel it found; they must match.

The ESP32-S3 only uses **2.4 GHz** Wi-Fi. A phone hotspot works if it is set to 2.4 GHz.

## 1. One-time set-up on the laptop

1. Docker Desktop running (it already runs Redis, MySQL and Mosquitto).
2. The ESP-IDF image, about 11 GB, once: `docker pull espressif/idf:v5.4.1`
3. esptool for flashing, same version as in the image:
   ```powershell
   python -m pip install esptool==4.8.1
   ```
4. Mosquitto open to the boards. In `.env`:
   - `MQTT_LAN_IP=` the laptop's Wi-Fi IPv4 address. Find it with `ipconfig` (section "Wireless LAN adapter Wi-Fi", line "IPv4 Address", for example `192.168.1.50`).
   - `MQTT_DEVICE_IDS=nadi-sim,nadi-recv-1,nadi-climate-1` (one ID per board; this is the allowlist).
   - Then, from the repo root:
     ```powershell
     python scripts\mqtt_users.py                    # writes deploy\mosquitto\passwd, fills in the passwords in .env
     docker compose up -d --force-recreate mosquitto
     docker compose ps mosquitto                     # PORTS shows 127.0.0.1:1883 and <your IP>:1883
     ```
   - Each board has its own password in `.env`: `MQTT_PASSWORD_NADI_RECV_1` for `nadi-recv-1`, `MQTT_PASSWORD_NADI_CLIMATE_1` for `nadi-climate-1`. You type it into that board's settings below. A password read out of one board cannot be used to log in as another.
5. Windows Firewall must let other devices reach port 1883. Set the Wi-Fi network to **Private** (Settings > Network & internet > Wi-Fi > the network > Private network). If the boards still cannot connect, open an **Administrator** PowerShell and run:
   ```powershell
   New-NetFirewallRule -DisplayName "NADI MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Private
   ```
6. If the laptop's IP address changes (another network, new DHCP lease), update `MQTT_LAN_IP`, run `docker compose up -d mosquitto`, and type `setup` on the receiver and climate node to enter the new address (no reflashing). The dashboard's **Board address** button shows the current one.

## 2. Find the COM port

1. Plug the board into the **COM** USB-C port with a data cable (some cables only charge).
2. Open Device Manager > **Ports (COM & LPT)**. A new entry appears, for example `USB-Enhanced-SERIAL CH343 (COM5)` or `Silicon Labs CP210x USB to UART Bridge (COM5)`. The number is your port.
3. Or in PowerShell: `python -m serial.tools.list_ports -v`
4. No new port? Look at the small chip next to the COM port:
   - `CH343` or `CH340`: install the WCH driver `CH343SER.EXE` from wch-ic.com, then replug.
   - `CP2102`: install the Silicon Labs "CP210x Universal Windows Driver", then replug.
   - Try another cable before anything else.

Below, replace `COM5` with your port.

## 3. Sender (`csi_send`)

```powershell
cd firmware\csi_send
..\idf.ps1 menuconfig
```

In menuconfig (arrow keys, Enter to open, `S` to save, `Q` to quit), open **NADI CSI sender**:

| Setting | Value |
|---|---|
| Wi-Fi network name (SSID) the receiver uses | the same network name the receiver joins (no password needed) |
| Channel to use if the network is not found | leave 6 |
| Packets per second | leave 50 |
| Sender MAC address | leave `1a:00:00:00:00:00` (a second room uses `1a:00:00:00:00:02` on both its boards) |

Build and flash:

```powershell
..\idf.ps1 build
python -m esptool --chip esp32s3 -p COM5 -b 460800 write_flash 0x0 build\merged.bin
```

Watch the serial log (press the board's **RST** button to see it from the start; quit with `Ctrl+]`):

```powershell
python -m serial.tools.miniterm COM5 115200
```

Expected:

```
I (...) nadi_send: NADI CSI sender 1.1.0 is starting. Type setup and press Enter to change the Wi-Fi name or channel.
I (...) nadi_send: Found the Wi-Fi network "YourNetwork" on channel 6.
I (...) nadi_send: Sending 50 packets per second on channel 6 from 1a:00:00:00:00:00.
I (...) nadi_send: Sent 500 packets on channel 6 in the last 10 s.
```

## 4. Receiver (`csi_recv`)

```powershell
cd firmware\csi_recv
..\idf.ps1 menuconfig
```

Open **NADI CSI receiver**:

| Setting | Value |
|---|---|
| Wi-Fi network name (SSID), Wi-Fi password | your 2.4 GHz network |
| Device ID | `nadi-recv-1` (must be in `MQTT_DEVICE_IDS`) |
| Room ID | `room1` (the room this pair watches) |
| Seconds per report | leave 10 (huawei mode: 20, to stay under the IoTDA free limit of 10,000 messages a day) |
| Sender MAC address | same as the sender |
| Where reports go | **Local mode: Mosquitto on the laptop** |
| Laptop IP address on the Wi-Fi network | `MQTT_LAN_IP` from `.env` |
| Mosquitto port | 1883 |
| MQTT password | `MQTT_PASSWORD_NADI_RECV_1` from `.env` |

The settings are saved in `firmware\csi_recv\sdkconfig`, which git ignores, so the passwords never reach GitHub.

```powershell
..\idf.ps1 build
python -m esptool --chip esp32s3 -p COM6 -b 460800 write_flash 0x0 build\merged.bin
python -m serial.tools.miniterm COM6 115200
```

Expected (the first report arrives about 10 s after start-up):

```
I (...) nadi_recv: NADI CSI receiver 1.1.0 is starting. Device nadi-recv-1, room room1, one report every 10 s, local mode (Mosquitto on the laptop).
I (...) nadi_recv: Type setup and press Enter to change the Wi-Fi network, broker or room; show to see the settings.
I (...) nadi_recv: Listening for CSI from the sender 1a:00:00:00:00:00.
I (...) nadi_recv: Connecting to the Wi-Fi network "YourNetwork".
I (...) nadi_recv: Connected to "YourNetwork" on channel 6. IP address: 192.168.0.120.
I (...) nadi_recv: The sender must also use channel 6. It finds it by itself when its network name is set.
I (...) nadi_recv: Clock set from pool.ntp.org.
I (...) nadi_recv: Connecting to the MQTT broker at 192.168.1.50:1883.
I (...) nadi_recv: Connected to the MQTT broker at 192.168.1.50:1883.
I (...) nadi_recv: Report sent: 500 packets, motion_mean 0.0170, motion_std 0.0018, amp_var 0.000412, RSSI -51.0 dBm.
```

The numbers above come from simulated CSI; yours will differ. About 500 packets per report (50 a second for 10 s) means the pair is working. If the sender is off or on another channel, the receiver sends **no** report and says so, so the dashboard shows the room as offline rather than empty.

On the laptop, with the server running (`python -m uvicorn server.main:app --host 127.0.0.1 --port 8000`), the room turns live on the dashboard at http://127.0.0.1:8000.

## 5. The 2-minute walk test

1. Put the sender and receiver 3 to 5 m apart at about chest height, with a clear line between them.
2. Keep the receiver's serial log open.
3. **Minute 1, nobody near the line:** wait for 3 reports and write down `motion_std` (call it E).
4. **Minute 2, walk back and forth across the line between the boards:** write down `motion_std` from the 3 reports (call it W).
5. Step away again: within one or two reports, `motion_std` falls back near E.

Pass: W is clearly bigger than E, several times over. On simulated CSI the jump is about 20 times (`firmware/csi_recv/test/`); a real room will differ. Also try one person sitting at a desk and typing, and note where that lands.

**Before trusting the headcount on the dashboard:** the current model (`ml/model/nadi_model.json`) was trained on simulator numbers, which are on a different scale from real boards, so it gives wrong counts for real readings (a still room came out as 3 people in testing). Until real labelled data is collected and the model retrained (build steps 5 and 6), switch to the threshold rule and set it from your walk test. In `.env`:

```
MODEL_PATH=off
HEADCOUNT_THRESHOLDS=T,99,99
```

where T is halfway between E and the lowest value you saw with someone in the room (for example E = 0.002 and W = 0.030 gives T = 0.016). With `99,99` it reports 0 (empty) or 1 (occupied) only, which is what CSI does reliably before training. Restart the server after changing `.env`.

## 6. Climate node (`climate_node`, Arduino IDE)

Wiring: DHT22 VCC 3.3 V, GND, DATA GPIO 4. KY-022 VCC 3.3 V, GND, OUT GPIO 18. KY-005 GND, SIG GPIO 17.

One-time Arduino IDE set-up:

1. File > Preferences > Additional boards manager URLs: `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. Tools > Board > Boards Manager: install **esp32 by Espressif Systems**, version 3.3.12 (the version this sketch was compiled with).
3. Tools > Manage Libraries, install: **IRremoteESP8266** 2.9.0, **DHT sensor library** 1.4.7 (and **Adafruit Unified Sensor** when asked), **PubSubClient** 2.8.0, **ArduinoJson** 7.4.3.

Settings:

1. Copy `firmware\climate_node\secrets.example.h` to `secrets.h` in the same folder and fill it in: Wi-Fi, `DEVICE_ID "nadi-climate-1"`, `ROOM_ID`, `NADI_TARGET_LOCAL 1`, `MQTT_HOST` = `MQTT_LAN_IP`, `MQTT_PASSWORD` = `MQTT_PASSWORD_NADI_CLIMATE_1`. `secrets.h` is git-ignored.
2. Open `firmware\climate_node\climate_node.ino`.
3. Tools menu:

| Option | Value |
|---|---|
| Board | ESP32S3 Dev Module |
| USB CDC On Boot | **Disabled** (otherwise the log goes to the other USB port) |
| Flash Mode | DIO 80MHz |
| Flash Size | 16MB (128Mb) |
| Partition Scheme | 16M Flash (3MB APP/9.9MB FATFS) |
| PSRAM | OPI PSRAM |
| Upload Mode | UART0 / Hardware CDC |
| Port | your COM port |

4. Upload, then Tools > Serial Monitor at **115200** baud, line ending **Newline**.

Expected:

```
NADI climate node 1.1.0 is starting. Type setup and press Enter to change the Wi-Fi network or broker.
Device nadi-climate-1, room room1, firmware 1.1.0, local mode (Mosquitto on the laptop).
Wi-Fi: not connected. MQTT: not connected. Stored air conditioner code: none (type learn).
Connecting to the Wi-Fi network "YourNetwork".
Connected to "YourNetwork". IP address: 192.168.0.121.
Clock set from pool.ntp.org.
No air conditioner code is stored yet. Type learn to record the remote's OFF button.
Connected to the MQTT broker at 192.168.1.50. Listening for the command ac_off.
Climate report sent: 24.6 C, humidity 63.2%.
```

### Record the air conditioner remote (learn mode)

1. Turn the air conditioner **on** with its remote first (many remotes send the full state, so record the "off" press from a normal setting).
2. In the Serial Monitor, type `learn` and press Enter.
3. Hold the remote about 5 cm from the KY-022 receiver and press **OFF** once.
4. Expected:
   ```
   Recorded: protocol DAIKIN, 280 bits, 583 timings.
   uint16_t rawData[583] = {...};
   Saved in flash; it stays after a restart. ...
   ```
   (the protocol and sizes depend on the brand). If the protocol is recognised, the decoded code is stored and sent, which is more reliable than raw timings; if it shows `UNKNOWN`, the raw timings are sent. Raw timings are always kept as a backup.
5. Test: air conditioner on, aim the KY-005 directly at it from 1 to 2 m, type `send`. It should switch off. Every send goes out **twice**, 150 ms apart, because one burst is easily missed across a room; the LED blinks white.
6. Test the full path from the laptop, as the server would send it:
   ```powershell
   python scripts\send_command.py
   ```
   Expected on the laptop: `Reply: {"result_code":0,"response_name":"ac_off","paras":{"result":"sent"}}`, and the air conditioner switches off.

Type `status` at any time to see the connection state, and `irtest` to check the IR LED with a phone camera.

## 6b. MQTT over TLS on the laptop (optional)

Encrypts reports on the Wi-Fi network. On the laptop: `.\.venv\Scripts\python scripts\mqtt_tls.py`, then `docker compose up -d --force-recreate mosquitto` (port 8883; same logins). The script copies the CA to `csi_recv/main/mqtt_ca.pem` and `climate_node/mqtt_ca.h` (git-ignored; the CA is public, not a secret).

- Receiver: `idf.py menuconfig` > NADI CSI receiver > **MQTT over TLS**, port **8883**, then build and flash. The certificate names the laptop IP, so the board checks it; if the IP changes, run the script again (same CA, no reflash needed) or, as a last resort, turn on "Do not check the broker address".
- Climate node: in `secrets.h` set `MQTT_TLS 1` and `MQTT_PORT 8883`, then upload.
- Allow TCP 8883 in Windows Firewall (Private profile). Full steps: [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).

Both are compiled in all modes by the compile checks (local, local with TLS, huawei).

## 7. Huawei mode (when IoTDA is available)

Not tested yet: there is no Huawei Cloud access. What changes:

- IoTDA console: register each board as a device and note its device ID and secret; host name from Overview > Access Details (MQTTS, port 8883).
- Receiver: menuconfig > Where reports go > **Huawei mode**, then IoTDA host name, port 8883, device secret; Device ID = the IoTDA device ID. The server certificate is checked with ESP-IDF's built-in root certificate bundle.
- Climate node: `NADI_TARGET_LOCAL 0`, `IOTDA_HOST`, `IOTDA_DEVICE_SECRET`, and `IOTDA_CA_PEM` (the IoTDA CA certificate from the console, pasted into `secrets.h`).
- Login is the same as `sim/fake_sensor.py`: client ID `{device_id}_0_0_{YYYYMMDDHH}`, password HMAC-SHA256 of the secret keyed with that timestamp.

## Security

What a board keeps, and what protects it today:

- **Secrets in flash are stored unencrypted.** `setup` saves the Wi-Fi password and the MQTT password (local mode) or
  the IoTDA device secret (huawei mode) in flash: NVS on the CSI receiver and sender (`nadi_common`), Preferences
  (also NVS) on the climate node. Compiled-in defaults from `sdkconfig` / `secrets.h` are in the firmware image too.
  Anyone who holds a board and a USB cable can read them out with `esptool.py read_flash`.
- **The production fix**, for boards installed in a real building, is ESP-IDF's
  - **NVS encryption** (keys in an encrypted `nvs_keys` partition),
  - **flash encryption** (`CONFIG_SECURE_FLASH_ENC_ENABLED`, release mode), and
  - **secure boot v2** (`CONFIG_SECURE_BOOT`, signed bootloader and app).

  Each of these burns **one-time eFuses** on the ESP32-S3. Once burnt they cannot be undone: a wrong key or a wrong
  setting can leave a board that no longer accepts new firmware, and release-mode flash encryption stops plain USB
  reflashing for good. They are therefore **not enabled on the demo boards**, which are reflashed many times a day.
  Enable them only on boards that are finished, with the keys stored safely off the laptop.
- **Until then:** every board has its own MQTT password (`MQTT_PASSWORD_<ID>` in `.env`) and may use only its own
  topics, so a lost or stolen board is cut off by removing its device ID from `MQTT_DEVICE_IDS` and running
  `python scripts\mqtt_users.py` (the other boards keep working). `DEVICE_ROOMS` stops a board reporting for other
  rooms, and the server holds back sudden jumps in a count. Use MQTT over TLS (section 6b) so the password does not
  cross the Wi-Fi network in plain text.
- **Roadmap: signed over-the-air updates.** ESP-IDF OTA with app signing (secure boot v2 keys), so a fixed firmware
  reaches every board without opening the enclosure, and a board only installs firmware signed by the team. Not
  built yet; today every update is a USB flash.

See also [SECURITY.md](../SECURITY.md).

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| No COM port in Device Manager | Charge-only cable (try another), wrong USB port (use COM, not USB), or the USB-serial driver is missing (section 2). |
| `Failed to connect to ESP32-S3: No serial data received` when flashing | Hold **BOOT**, press and release **RST**, release **BOOT**, then run the flash command again. Close any serial monitor or Arduino Serial Monitor using the port first. |
| `Could not open COM5, the port is busy` | Another program has the port open (serial monitor, Arduino IDE). Close it. |
| `Brownout detector was triggered`, board restarts in a loop | Not enough power when Wi-Fi starts. Use a short data cable, a USB port directly on the laptop (not a hub), or a 5 V 2 A charger. |
| Log shows garbage characters | Wrong speed: use 115200. |
| Arduino Serial Monitor shows nothing | Tools > USB CDC On Boot must be **Disabled**, and the cable in the COM port. Press RST. |
| `The Wi-Fi network "..." was not found` | Name is case-sensitive; the network must be 2.4 GHz; the board must be in range. |
| `The Wi-Fi network "..." refused the connection` | Wrong Wi-Fi password. |
| `The broker refused the login` | Device ID not in `MQTT_DEVICE_IDS`, or the password is not that device's `MQTT_PASSWORD_<ID>`. Fix `.env`, run `python scripts\mqtt_users.py`, then `docker compose up -d --force-recreate mosquitto`. |
| `Could not reach the broker at ...` | Wrong laptop IP (check `ipconfig`), Mosquitto not running (`docker compose ps`), `MQTT_LAN_IP` not set, or Windows Firewall (section 1, step 5). Laptop and board must be on the same Wi-Fi network (some guest networks block devices from reaching each other). |
| `docker compose up` fails with `cannot assign requested address` | `MQTT_LAN_IP` is no longer this laptop's IP. Update it from `ipconfig`. |
| `Only 0 CSI packets from the sender` | Sender off, or on another channel: compare the channel in both logs. Check the sender's network name is exactly right and both use the same sender MAC. If the network changed channel, press RST on the sender (it also rechecks every 5 minutes). |
| Packet count far below 1000 | Boards too far apart or a wall between them; move them closer. A busy network can also drop packets. |
| `The DHT22 did not answer` | DATA must be on GPIO 4, VCC on 3.3 V. Bare DHT22 sensors (not on a small board) need a 10 kΩ resistor from DATA to 3.3 V. |
| `No IR code was received in 30 s` | KY-022 OUT on GPIO 18, VCC 3.3 V; hold the remote closer. |
| `send` does nothing to the air conditioner | KY-005 range is short: aim it straight at the unit from 1 to 2 m. Record the code again closer to the receiver. |
| Build error mentioning a different source directory | The build folder came from another path: delete `build` (`Remove-Item -Recurse build`), then build again. |

## Checks run without boards

- Both ESP-IDF projects and the sketch (local and huawei mode) compile in Docker with no warnings in NADI's code:
  `docker run --rm -v ${PWD}/firmware:/fw espressif/idf:v5.4.1 sh /fw/compile_check.sh` (sender, receiver local and huawei).
- `firmware/csi_recv/test/run_host_test.sh` runs the receiver's feature and report code on a PC with simulated CSI (still room, gain change, slow and fast movement):
  `docker run --rm -v ${PWD}/firmware:/fw espressif/idf:v5.4.1 sh /fw/csi_recv/test/run_host_test.sh`
- `python sim\fake_board.py --check` publishes exactly the firmware's JSON (read from its source) to Mosquitto as the boards would, and confirms the server stored the same values.
- `firmware/climate_node/compile_check.sh` compiles the sketch in both modes with arduino-cli (instructions inside).

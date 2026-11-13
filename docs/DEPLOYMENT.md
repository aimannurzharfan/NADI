# Deploying NADI

NADI runs in one of two modes, set by `NADI_MODE` in `.env`. Local mode makes no Huawei Cloud calls at all.

## Local mode (laptop or a PC in the building)

Needs Python 3.11 or newer, Docker Desktop and, for the chat model, [Ollama](https://ollama.com).

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python scripts\mqtt_users.py        # broker logins, fills in MQTT passwords in .env
docker compose up -d --wait                         # Valkey, MySQL (port 3307), Mosquitto
ollama pull qwen2.5:3b                              # optional: without it, chat uses built-in answers
.\.venv\Scripts\python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --limit-concurrency 200 --timeout-keep-alive 5
```

Always start uvicorn with these three options: proxy headers are handled by NADI itself (`TRUSTED_PROXIES`), at most 200 requests run at once, and idle connections close after 5 s so slow clients cannot hold sockets open.

**Valkey instead of Redis.** The live store is Valkey 8 (BSD-3-Clause), a drop-in replacement for Redis with the same protocol; the Docker service is still called `redis`, so `REDIS_HOST` and `REDIS_PORT` are unchanged. Valkey cannot read a Redis 7.4 data file, so the first start after this change uses a new volume (`valkey_data`): live counts, alerts and the audit log start empty, history in MySQL is kept. The old volume can be removed with `docker volume rm nadi_redis_data` once you no longer need it.

```powershell
```

Open `http://<this computer>:8000`. Add `?lang=ms` for Malay.

The web console is already built (`web/dist` is committed), so the server computer needs no Node.js. To change the console, install Node.js 20 or newer and rebuild:

```powershell
cd web
npm install          # once
npm test             # unit tests
npm run build        # writes web/dist, which FastAPI serves
npm run dev          # live-reload preview on http://localhost:5173, using the server on port 8000
```

Before using it with real people, set these in `.env`:

| Setting | Why |
|---|---|
| `ADMIN_TOKEN` or `ADMIN_TOKENS` | Needed to start or end emergency mode, chat or label from any device other than this computer. Make one per person with `python scripts\new_token.py --admin warden1`: it adds a named token to `ADMIN_TOKENS` and prints it once. Names show who did what in the audit log, and one can be removed without changing the others. |
| `VIEWER_TOKEN` | Optional in local mode, required in huawei mode: the dashboard data is then only shown to people who enter this token (or an admin token). `python scripts\new_token.py --viewer`. |
| `LOCALHOST_ADMIN` | `on` (default in local mode): the server computer itself is admin without a token, but only for requests with no proxy headers. Set `off` when other people can use that computer. Always off in huawei mode. |
| `TRUSTED_PROXIES` | Only when a reverse proxy runs in front of NADI: its address(es). `X-Forwarded-For` is ignored from anyone else. |
| `HISTORY_RETENTION_DAYS` | History older than this is deleted once a day (default 90). |
| `LOG_FILE` | Optional: also write the server log to this file, rotated at `LOG_MAX_MB` (default 10 MB, 5 old files kept). |
| `ROOM_NAMES`, `BUILDING_NAME`, `LEVEL_NAME` | What the dashboard calls each room. |
| `DEVICE_ROOMS` | Which rooms each board may report for, for example `nadi-recv-1:room1,nadi-climate-1:room1`. |
| `MQTT_LAN_IP` | The computer's Wi-Fi address, so the ESP32 boards can reach the broker. See [firmware/README.md](../firmware/README.md). |
| `HEADCOUNT_THRESHOLDS` | From `scripts\calibrate.py` after a walk test in each room. |

Windows Firewall must allow port 8000 (dashboard) and 1883 (boards) on the building network (8883 instead of 1883 with TLS, below).

### MQTT over TLS (optional)

Encrypts the reports between the boards and the laptop. The certificates are made locally; nothing is sent anywhere.

1. `.\.venv\Scripts\python scripts\mqtt_tls.py` makes a private CA and a broker certificate for 127.0.0.1 and `MQTT_LAN_IP`, writes the 8883 listener (`deploy/mosquitto/conf.d/tls.conf`) and copies the CA into both firmware folders (all git-ignored).
2. `docker compose up -d --force-recreate mosquitto`. Port 8883 now accepts TLS with the same logins and topic limits.
3. CSI receiver: `idf.py menuconfig` > NADI CSI receiver > **MQTT over TLS**, port 8883, then build and flash. Climate node: in `secrets.h` set `MQTT_TLS 1` and `MQTT_PORT 8883`, then upload.
4. Once every board uses TLS, set `MQTT_PLAIN_IP=127.0.0.1` in `.env` and `docker compose up -d mosquitto`: plain 1883 is then reachable from this computer only.
5. The server can use TLS too (`MQTT_TLS=on`), though on the same computer plain 1883 on 127.0.0.1 is fine.

If the laptop IP changes, run the script again (the CA stays the same, so the boards keep working). If you cannot, the receiver has a menuconfig option to skip the address check; the CA is still checked.

**Stage day:** set `DEMO_SCENARIO=on` and restart the server. A fixed 3-minute story plays through the normal data path and the dashboard shows **DEMO SCENARIO** the whole time. Turn it off for real use. A backup recording: `.\.venv\Scripts\python scripts\record_demo.py`.

**Before a demo or test run**, stop anything left over and clear test data: `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1`, then `.\.venv\Scripts\python scripts\reset_demo_data.py --yes` (history, live counts, alerts and air conditioning waste totals; local mode only).

## Huawei mode (Huawei Cloud)

Only when the team has cloud resources. It creates billable services; check costs first.

1. Pick one region where IoTDA, ECS, RDS for MySQL, DCS for Redis, SMN, ModelArts and MaaS all exist.
2. IoTDA console: create a product (MQTT, JSON) with two services, then register each board as a device:
   - `csi`: `room_id` (string), `ts` (int), `motion_mean`, `motion_std`, `amp_var`, `rssi_mean` (decimal), `n_packets` (int)
   - `climate`: `room_id` (string), `ts` (int), `temp_c`, `humidity` (decimal)

   In `.env`: `IOTDA_DEVICE_ID`, `IOTDA_DEVICE_SECRET`, `IOTDA_HOST` (Overview > Access Details, MQTTS 8883). The
   simulator through IoTDA: `.\.venv\Scripts\python sim\fake_sensor.py` (prints `MQTT connect: Success`); if TLS fails,
   set `IOTDA_CA_CERT` to the IoTDA CA certificate from the console.
3. Create the SMN topic, DCS Redis, RDS MySQL and a MaaS API key. Fill `IOTDA_*`, `SMN_TOPIC_URN`, `REDIS_*`, `MYSQL_*`, `MAAS_*`, `HUAWEICLOUD_AK/SK`, `ADMIN_TOKENS`, `VIEWER_TOKEN`, `INGEST_TOKEN`, and set `NADI_MODE=huawei`. The server refuses to start in huawei mode if any secret still has its example or docker-compose value, is shorter than 16 characters, or if `VIEWER_TOKEN`, an admin token or `INGEST_TOKEN` is missing (it names the setting, never the value). Make new values with `python scripts\new_token.py`.
4. Check the keys (read-only): `.\.venv\Scripts\python deploy\huawei_preflight.py`
5. Deploy to ECS with CodeArts Repo and Pipeline: [deploy/CODEARTS.md](../deploy/CODEARTS.md). The service file is `deploy/nadi.service`.
6. IoTDA data forwarding: HTTP push to `http://<ECS address>:8000/iotda?token=<INGEST_TOKEN>`. `INGEST_TOKEN` is required in huawei mode. The server hides it in its access log.
7. If a reverse proxy is put in front of the server, set `TRUSTED_PROXIES` to its address (uvicorn keeps `--no-proxy-headers`). NADI then takes the client address from `X-Forwarded-For`, from that proxy only; otherwise every caller shares one rate limit.

In huawei mode emergency mode and chat are refused until `ADMIN_TOKEN` is set, and alerts go out by SMS and email through SMN.

## Checking it works

```powershell
.\.venv\Scripts\python -m pytest                    # no services needed
.\.venv\Scripts\python sim\fake_board.py --check    # sends what a board sends, confirms it was stored
```

`GET /api/health` shows whether Redis, MySQL and the broker are reachable. Stress tests and their results: [TESTING.md](TESTING.md).

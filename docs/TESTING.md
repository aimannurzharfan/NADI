# NADI under stress

Tested on 25 Oct 2026 on the development laptop (Windows 11, local mode: Docker Redis, later Valkey, MySQL and Mosquitto, Ollama qwen2.5:3b). "Before" is the previous commit, probed with the same inputs. Scripts are in `scripts/stress/`; raw results are in `scripts/stress/results/`.

## Load: 100 viewers, 20 chat users, 30 boards, 5 minutes

100 dashboards polling every 5 s, 20 people asking a question every 10 s (each from its own IP), and 30 boards publishing every 2 s through Mosquitto, all at the same time.

| Endpoint | Requests | p50 | p95 | Max | Errors |
|---|---|---|---|---|---|
| Live rooms (`/api/rooms`) | 5,978 | 7.9 ms | **13.6 ms** | 57 ms | 0 |
| Sparkline history (`/api/history`) | 1,000 | 9.2 ms | 35 ms | 232 ms | 0 |
| Header info (`/api/info`) | 500 | 3.0 ms | 21 ms | 74 ms | 0 |
| Chat (`/api/chat`) | 530 | 595 ms | 4.6 s | 5.1 s | 0 |

- Target met: live rooms p95 13.6 ms against a 300 ms target, zero errors.
- Board reports: 4,470 sent, 4,470 stored, none lost.
- Server memory: 75 MB at start, 88 MB after warm-up, 92 MB in the last minute (+4.6 MB, levelling off).
- Chat: 20 people at once is more than a laptop model can answer. Slow replies stop at the 5 s limit and the checked built-in answer is shown, so every question still got an answer.
- The first run found slow history (p95 1.4 s): the query scanned the whole table. Fixed with an index on time and a 5 s shared cache: p95 is now 35 ms.

## Bad input

| Scenario | Before | Fix | After |
|---|---|---|---|
| Body over the 4 KB limit | Accepted (9 KB stored) | Size cap on every POST (8 KB for IoTDA push, which adds an envelope) | 413, nothing stored |
| Malformed JSON, empty body | 422 | Kept | 422 |
| NaN in a report | Stored | Every number must be finite and in range | 422, nothing stored |
| Infinity as timestamp | 500 (crash) | Same check | 422 |
| NaN in a request body | 500 (the error reply tried to echo NaN) | Error replies never echo input | 422 |
| Temperature 500 °C, humidity 150%, negative motion | Stored | Bounds per field | 422, nothing stored |
| "people 9999" sent by a device | Ignored with 200 (headcount is worked out by the server) | Unknown report types refused; only checked fields stored; model output capped at 3+ | 422 |
| Unknown room ID | Stored as a new room | Room must be on the floor plan or in `ROOM_NAMES` | 422 |
| Timestamp 2 days old or 1 hour ahead | Stored | Must be within 1 day back, 5 minutes ahead (0 = server clock, for boards without NTP) | 422 |
| Same report sent twice | Stored twice | Duplicate check per room and timestamp | Accepted once, second marked duplicate |
| SQL injection or XSS in a room ID | Stored | Room ID: letters, digits, - and _ only | 422 |
| `room1` + newline | Stored | Full-match check (a first draft of the new check let it through; a test caught it) | 422 |
| One bad entry in a report with good ones | Good ones stored | The whole report is rejected | 422, nothing stored |
| XSS in a room display name | Already shown as text | Kept (no innerHTML anywhere) | Shown as text, script never runs (checked in a browser) |
| Chat question over 500 characters | Cut off silently | Clear refusal | 422 |
| Chat with emoji, SQL or HTML | Answered | Answers come from rules and never echo the question | Answered safely |
| `{"on": "false"}` or `{"on": NaN}` to emergency | **Started the alarm** | Must be true or false | 422, alarm not started |

## Abuse and many users

| Scenario | Before | Fix | After |
|---|---|---|---|
| Guessing the admin token | Unlimited guesses | Tokens at least 16 characters; 5 wrong tokens in 10 min refuse more guesses from that IP for 15 min | Guesses get 429; a warden on the same Wi-Fi with the right token is never locked out |
| Chat flooding | Unlimited | 10 questions per minute per IP | 11th gets 429 |
| Emergency toggle spam | Unlimited | 6 presses per minute per IP | 7th gets 429 |
| 8 wardens press start at the same moment | **8 alarm alerts sent** | Atomic start in Redis (HSETNX) | 1 alarm, 1 start time, 1 audit entry |
| 8 wardens press end at the same moment | Each one "ended" it | Atomic end | 1 end in the audit log |
| Who started or ended it | Not recorded | Audit log with token label, IP and time (admin only); the alert shows label and time | Alert: "Emergency mode started by stress at 10:03:15." |
| Device without login, or wrong password | Refused by Mosquitto | Kept | Refused |
| Device publishing on another device's topic | Dropped by Mosquitto | Kept | Dropped |
| Device reporting for another room | Stored | `DEVICE_ROOMS` lists the rooms each device may report; on the IoTDA push the device name only counts when `INGEST_TOKEN` is set | Rejected, nothing stored |

## Security and scale pass (25 Oct 2026, evening)

Run against Valkey 8.0.2, MySQL and Mosquitto with the new limits. Attack: **66/66 passed**. Chaos: **35/35 passed** (Ollama was not running, so its step was skipped). Load: **passed**.

Load (5 minutes, as above, now through the production uvicorn options and per-IP limits; every viewer and chat user has its own IP through `TRUSTED_PROXIES`, boards every 2 s with `REPORT_INTERVAL_S=3`):

| Endpoint | Requests | p50 | p95 | Max | Errors |
|---|---|---|---|---|---|
| Live rooms (`/api/rooms`, 1 s cache) | 5,973 | 8.6 ms | **21.3 ms** | 61 ms | 0 |
| History (`/api/history`) | 1,000 | 6.2 ms | 18.2 ms | 36 ms | 0 |
| Header info (`/api/info`) | 500 | 5.4 ms | 17.1 ms | 1.0 s | 0 |
| Chat (`/api/chat`, built-in answers: Ollama not running) | 598 | 6.6 ms | 11.3 ms | 28 ms | 0 |

- Board reports: 4,470 sent, 4,470 stored. Server memory 71 MB at start, +1.2 MB over the run.
- Found and fixed during this run: when the Ollama check expired (every 30 s) and Ollama was stopped, every `/api/info` request at that moment waited up to 1 s for it (p95 1.0 s). The check now refreshes in the background, one at a time; only the very first check after start-up waits (the 1.0 s maximum above).
- Two early runs had 1 and 2 errors: a request sent on a keep-alive connection the server was just closing (uvicorn closes idle connections after 5 s and the dashboard polls every 5 s). Browsers repeat a GET in that case; the load client now drops idle connections after 4 s, as a client should, and would repeat a GET once (it needed to 0 times in the final run).

| Scenario | Before | Fix | After |
|---|---|---|---|
| `X-Forwarded-For: 127.0.0.1` (or `X-Real-IP`, `Forwarded`) sent to look like the server computer | Not tried; uvicorn trusted proxy headers when started with `--proxy-headers` | uvicorn runs with `--no-proxy-headers`; NADI reads `X-Forwarded-For` only from `TRUSTED_PROXIES`; localhost admin needs no proxy header at all | 401 |
| 260 reads of `/api/rooms` in a minute from one IP | All served | 240 reads a minute per IP, kept in Valkey | 240 served, then 429 with `Retry-After`; other IPs unaffected |
| Security headers | None | CSP without inline scripts, X-Frame-Options DENY, nosniff, no referrer, Permissions-Policy | Present on every response |
| Headcount 5000, 2.5 or negative (`count` service) | Service did not exist | 0 to 1000 whole people | 422 |
| A board sends 5 reports in a few seconds | All stored | One report per room per half report interval per board | 1 stored, 4 dropped and logged |
| A count jumps from 5 to 95 in one report | Would be shown | Held back as a suspicious reading, alert once an hour per room | Not shown; alert sent; the next agreeing report (96) is accepted |
| Guessing tokens through `/api/me` (the sign-in check) | Counted (it went through the admin check) | The rewrite first lost this; found in review and fixed: wrong tokens count, and `/api/me` is rate limited | 5 wrong tokens, then status 429; the right token still works |
| MQTT packet over 4 KB | Received, then dropped by the server | Broker `max_packet_size 4096` | Broker disconnects the client |
| 60 open sockets to the broker | Accepted | `max_connections 50` per listener | New logins refused at the limit, fine again after |
| Viewer token set | Not available | `VIEWER_TOKEN` on every read | No token 401, viewer token 200, and it never works as an admin token |
| Huawei mode with docker-compose passwords and no tokens | Started | Refuses to start, names the settings, never the values | Exit with "Refusing to start in huawei mode" |
| Valkey stopped mid-emergency (chaos) | Limits were in memory anyway | Limits in Valkey, falling back to memory | Chat still limited to 10 a minute per IP during the outage |
| Sensors stopped mid-emergency (chaos) | Rooms showed their last count as if live, in amber | Unknown, never empty | "?" with "Unknown now, last known N", total reads "At least N" and names the unknown rooms |

Dependency audit (`pip-audit -r requirements.txt`, `npm audit`):

| Finding | Fix |
|---|---|
| Starlette 0.46.2 (via FastAPI): Range header slow-down, Host header and path checks, StaticFiles on Windows, form limits | FastAPI 0.162.0 with Starlette 1.10.0 |
| cryptography 44.0.0: bundled OpenSSL and certificate checks | 50.0.2 |
| python-dotenv 1.0.1: `set_key` follows symbolic links | 1.2.4 |
| react-router-dom 6.28.0 (bundled): open redirect (high) | 6.30.6 |
| Vite 5.4.11 (high), Vitest 2.1.8 with Tinypool (critical), PostCSS 8.4.49 (high): build and test tools only, not in the shipped page | Vite 8.3.5, Vitest 5.0.5, @vitejs/plugin-react 6.1.2, PostCSS 8.5.31; build, unit and browser tests pass |
| **Not fixed:** pyasn1 0.6.3 (decoder slow-downs on crafted input) | Pulled in by `huaweicloudsdkcore` 3.1.219 (the latest), which requires pyasn1 0.6.3 or older. Used only in huawei mode, to talk to Huawei's own API. Upgrade when Huawei releases a new SDK |
| **Not fixed:** pyasn1 0.6.3, four more decoder slow-downs on crafted input (CVE-2026-119194, -119195, -119196, -119197, 2026-11-02; fixed in 0.6.5) | `huaweicloudsdkcore` 3.1.220 (the latest) still requires pyasn1 0.6.3 or older. NADI never decodes untrusted ASN.1. Upgrade when Huawei releases a new SDK |
| **Not fixed:** pymongo 4.18.2 (crash on crafted BSON read from mmap or array buffers, CVE-2026-106435, 2026-10-28) | `huaweicloudsdkcore` 3.1.219 requires exactly 4.18.2; the fix is 4.18.3. NADI never decodes BSON. Upgrade when Huawei releases a new SDK |
| **Not fixed (moderate):** Tailwind CSS 3 uses an old postcss-selector-parser; react-router 6 has a moderate advisory | Both need a major upgrade (Tailwind 4, React Router 7); build-time or low impact |

## Incident features and security review (26 Oct 2026)

A security review of the two commits that had none (the web console, and the scale and security pass), then drill
mode, warden marks, incident reports, automatic snapshots, sensor-stopped alerts, data deletion and Malaysia time.
Attack: **86/86 passed**. Chaos: **41/41 passed** (Ollama was not running, so its step was skipped). Load: **passed**
on the second run (see below). 393 pytest, 17 console unit tests, 8 browser tests in Edge.

Security review findings, each fixed and pinned by a test (`tests/test_security.py`, and `attack.py` against a live server):

| Finding | Risk | Fix | After |
|---|---|---|---|
| Admin POSTs with no body (`/api/devices/clear`, `/api/labels/undo`, alert acknowledge, demo restart) could be sent by any website open in a browser on the server laptop, which counts as admin there | A web page clears the device list or acknowledges alerts behind the warden's back; the new "delete all data" would have been exposed the same way | POST, PUT, PATCH and DELETE that a browser marks as cross-site (`Origin` or `Sec-Fetch-Site`) are refused before any endpoint | 403 |
| DNS rebinding: a site whose own name resolves to 127.0.0.1 is treated as "this computer" | Full admin from a web page | Localhost admin also needs the Host header to be `localhost`, `127.0.0.1` or `[::1]` | No admin, 401 or 403 |
| `/iotda` without `INGEST_TOKEN` accepted reports from anyone; huawei mode did not require the token | Made-up counts for any room, from the network or the internet | Huawei mode refuses to start without `INGEST_TOKEN`; in local mode without it, only this computer may post | 401 from anywhere else |
| The IoTDA push URL carries `?token=`, and uvicorn's access log (on in `deploy/nadi.service`) printed it, also to `LOG_FILE` | Token in log files | The access log shows `token=***` | Redacted |
| `scripts/mqtt_tls.py` kept the CA private key in `deploy/mosquitto/certs`, which is mounted into the broker container | A broken broker leaks the key that can sign certificates the boards trust | Key moved to `deploy/mqtt_ca/` (git-ignored, not mounted); the script moves an existing key on its next run | Broker only sees `ca.crt`, `server.crt`, `server.key` |
| The 4 KB body cap covered POST, PUT and PATCH only | Unlimited body on other methods | Every method except GET, HEAD and OPTIONS | 413 |
| `/docs`, `/redoc`, `/openapi.json` open to everyone | The whole API mapped out for an attacker | 404 in huawei mode, admin only in local mode | 401, 403 or 404 |

Checked and found sound: token comparison (constant time), lockout counting, proxy header handling, rate-limit
buckets, security headers on refused replies, no `dangerouslySetInnerHTML` or `innerHTML` in `web/src`, no secrets
in `web/dist` or in any tracked file (every value in `.env` was searched for), TLS settings (TLS 1.2 or later,
certificate names checked by the boards).

New behaviour, tested:

| Scenario | Result |
|---|---|
| Drill started | Same screens under a yellow DRILL banner; every alert of the drill starts with [DRILL] / [LATIHAN] and says it is a drill (console and SMN alike), is never critical, and is kept apart: alert type "Drill", its own table of reports, "drill" in the audit log |
| Warden marks a room "searched, clear" or "need help" | Needs the admin token; shown on every screen and on the export with who and when; audit-logged; gone when the emergency or drill ends |
| Emergency or drill ends | Report written: start and end, who, people inside at the start, how long each room took to reach zero (cleared again if people come back), marks, rooms offline with times, every alert raised and who acknowledged it (also acknowledgements made later) |
| Emergency starts, then the server is killed and restarted (chaos) | Snapshot on disk at once (JSON and printable HTML in English and Malay, opens with no server), and every minute again after the restart |
| A full disk while saving a snapshot | Logged; the alarm still starts (a first version re-raised the error: found by a test and fixed) |
| Sensors stop mid-emergency (chaos) | One "sensor stopped" alert, critical during a real emergency (a warning otherwise and during a drill), no repeats, one "back online" when they return. A device that sends two services (the simulator) is judged by the faster one |
| A simulator reporting for 33 rooms stops | Found live: one alert listing all 33 rooms and "14957 seconds". Now "Lab 2, Hall A, ... and 28 more" and minutes after two minutes |
| Delete all stored data | Admin only, typed phrase, refused during an emergency or drill (attack.py checks all three refusals; the deletion itself is tested in pytest only, never against the real database) |
| Server clock more than 60 s off NTP | Banner on every screen; offline: no check, no banner (tested with a local fake NTP server) |
| Times | Stored as Unix time, shown in Malaysia time whatever the computer's time zone, 24-hour in both languages (the Malay page said "01:41 PG" before) |

Load (5 minutes, same as the previous pass):

| Run | `/api/rooms` p95 | Errors | Board reports |
|---|---|---|---|
| First | 34.3 ms | 0 | 4,470 sent, **4,275 stored**: 195 dropped by the per-board limit |
| Second | 23.5 ms | 0 | 4,470 sent, 4,470 stored |

The 195 drops in the first run were the per-board rate limit ("faster than one every 1.5 s"): the test sends every
2 s, so half a second of delay inside the server makes two reports arrive too close together. During that run Ollama
was half up (65 chat calls failed or timed out while it held the CPU). Real boards report every 20 s against a 10 s
limit, so the margin there is 10 s, not 0.5 s.

Found while checking the screens in Edge (Playwright) and fixed: the "searched, clear" badge was pale green on
pale green in the dark emergency view; the floor plan said "1 people"; the report and export pages scrolled sideways
on a phone; the top bar was 2 px too wide on a phone; the report showed "3" where the sensor meant "3 or more".

Continuous checks: `.github/workflows/ci.yml` runs on every push with no secrets: pytest, the console unit tests,
`pip-audit --strict` (only the seven pyasn1 IDs and the one pymongo ID described in SECURITY.md are ignored), `npm audit --audit-level=high`
and gitleaks over the whole history. Local `pip-audit` and `npm audit` (no high or critical, 5 moderate) give the
same results. The CI itself runs on GitHub; see the Actions tab for the latest run.

## Broken dependencies (during an emergency, simulator running, dashboard open)

| Stopped | Before | After | Banner on the dashboard | Recovery |
|---|---|---|---|---|
| Redis | Live rooms 500; dashboard kept old numbers with only a footer note | Last known data served, every room marked "last known count", emergency view stays up, chat answers from last known data | "Database offline, showing last known data at 10:03." | 1 s after Redis is back |
| MySQL | Every report raised an error; its history row was lost | Live counts keep updating; history rows wait in memory and are written when MySQL is back (checked: rows from the outage are in MySQL) | "History database offline since 10:03. Live counts still update; history is saved when it is back." | 4 s |
| Mosquitto | Silent; up to 2 minutes to reconnect | Reported at once; reconnects within 10 s | "Sensor link offline since 10:04. Counts are not updating." | 7 s, new reports arrive |
| Ollama | Chat waited up to 90 s, then 2 s per question while down | Down: built-in checked answer at once. Slow: 5 s limit, then the checked answer | (footer shows built-in answers) | Next question |
| NADI server | Old numbers with only a small footer note | Dashboard says so | "Server unreachable, showing last known data at 10:05." | On its own when the server is back |

The server process never stopped during any outage.

## Emergency resilience

| Scenario | Result |
|---|---|
| Server killed and restarted mid-emergency | Emergency still on, same start time (kept in Redis) |
| Redis restarted mid-emergency | Emergency still on, same start time (Redis now writes an append-only file to a volume) |
| Sensors go offline mid-emergency | Rooms show "?" (unknown), with "Unknown now, last known N (36 s ago)"; they stay in the rescue list, ranked by their last known count, and the total reads "At least N" with the unknown rooms named |

## Long run: dashboard open 30 minutes (28 Oct 2026, web console)

Headless Chromium at 1366x768, simulator running, the chat panel open with a question every 20 s, and emergency mode
switched on and off every 2 minutes (90 questions, 15 switches). Both capped lists were filled before measuring.
Result: **PASS** (`scripts/stress/results/longrun.json`).

| Measure | Minutes 3 to 10 | Last 8 minutes | Result |
|---|---|---|---|
| Browser memory (JS heap, after garbage collection) | 8.49 MB | 9.09 MB | +7%, limit 20% |
| Page elements, dashboard | 538 | 538 | Stable |
| Page elements, emergency screen up | 721.5 | 722 | Stable |
| Alerts on the overview | 6 | 6 | Capped at 6 |
| Chat messages kept | 40 | 40 | Capped at 40 |
| Console errors | | | None |

- The emergency screen adds about 180 elements while it is up. The earlier check compared the median of minutes 4 to
  8 (mostly dashboard) with the last 5 samples (mostly emergency screen), so it failed on which screen happened to be
  showing, not on growth: the test was wrong, not the console. Each sample now records whether the emergency screen
  was up, and elements are compared screen by screen.
- The chat count now counts messages only (the log also holds an empty scroll anchor and a "waiting" bubble), and the
  script switches emergency mode off before it starts, in case a demo or a crash left it on.
- The dashboard keeps only what is on screen (6 alerts on the overview, the last 40 chat messages); requests time out
  after 6 s and the same request never runs twice at once, so a hung server cannot pile them up.

## How to run

```powershell
.\.venv\Scripts\python -m pytest                    # 393 tests, no services needed (each test gets its own in-memory Redis)
.\.venv\Scripts\python -m pytest tests_e2e          # 8 browser tests in Edge, needs the Docker services
cd web; npm test; cd ..                             # 17 console unit tests
.\.venv\Scripts\python scripts\stress\load.py       # 5 min
.\.venv\Scripts\python scripts\stress\attack.py     # 2 min
.\.venv\Scripts\python scripts\stress\chaos.py      # 6 min, stops and starts Docker services
.\.venv\Scripts\python scripts\stress\longrun.py    # 30 min
.\.venv\Scripts\pip-audit -r requirements.txt       # known vulnerabilities in Python packages
cd web; npm audit; cd ..                            # and in the console's packages
gitleaks git --config .gitleaks.toml .              # secrets anywhere in the git history
```

## Known limits

- Rate limits and lockouts are kept in Valkey; while it is down they fall back to memory in each server process.
- Behind a reverse proxy on ECS, set `TRUSTED_PROXIES` to its address, otherwise every caller looks like the proxy and shares one limit.
- On Windows, Python's asyncio logs a harmless traceback when a client resets a finished connection (`_call_connection_lost`, WinError 10054); the attack script leaves those out when it checks the server log.
- Starting an emergency needs Valkey. If Redis is down at that moment the warden gets a clear "live data store offline" error instead of a silent failure.
- History waiting for MySQL is kept in memory (up to 5,000 rows, about 14 hours for one room); a server restart during a MySQL outage loses it.
- MQTT on the LAN is plain until `scripts/mqtt_tls.py` is run and the boards are switched to TLS (port 8883). Tested with the server and a paho client: login, round trip, wrong CA refused, plain MQTT on 8883 refused. Not tested on a real board yet.
- A right admin token is accepted even while its IP is locked out, so an attacker can keep guessing at network speed. This is deliberate (a lockout must never keep a warden out during a fire); the defence is a long random token (`.env.example` shows how to make one). A configured token that is too short switches emergency and chat off instead of falling back.
- Public alerts show only who (token label) and when. The IP address is kept in the audit log, which needs the admin token (`GET /api/audit`), or the server computer when no token is set.

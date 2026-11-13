# Security policy

## Supported versions

NADI is a competition prototype.

| Version | Supported |
|---|---|
| v1.0 (and the latest commit on `main`) | Yes |
| Anything earlier | No |

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting: on this repository, open **Security**, then **Report a vulnerability**. This reaches the maintainers without making the problem public. Do not open a public issue for a security problem.

Include what you found, how to reproduce it, and what an attacker could do with it. We will reply as soon as we can.

## Local mode: what to know before you rely on it

Local mode (`NADI_MODE=local`, the default and what the Docker demo runs) is built for one laptop on a network you
trust.

- **The server computer is the admin.** With `LOCALHOST_ADMIN=on` (the default) a browser on the computer running
  the server needs no token. Set `ADMIN_TOKEN` (16 characters or more, `python scripts/new_token.py`) before other
  people open the console from their own devices, and `LOCALHOST_ADMIN=off` if others use that computer.
- **The Docker demo listens on `127.0.0.1` only.** Nothing on the network can reach it. Do not change the port
  mapping in `docker-compose.yml` to expose it: inside the container every caller looks like the computer itself.
- **Reading is open by default.** Anyone who can reach the server can read the dashboard until `VIEWER_TOKEN` is set.
- **The example passwords are public.** The MySQL password in `.env.example` and `docker-compose.yml` is fine for a
  laptop demo (those ports are published on `127.0.0.1` only); the server warns about it at start-up in local mode
  and refuses to start with it in huawei mode.
- **Plain MQTT on the LAN.** Boards send over port 1883 without encryption unless you set up TLS
  (`scripts/mqtt_tls.py`). Use a network of your own, such as a phone hotspot, not a shared one.
- **Not a life-safety system.** Counts are estimates; a room whose sensor is silent is shown as unknown, never as
  empty. Wardens still sweep the building.

## Protections in place

Tested in [docs/TESTING.md](docs/TESTING.md):

- **Sensor input:** every report is checked before it is stored (room ID format and known rooms, finite numbers within bounds, timestamps within one day back and 5 minutes ahead, duplicates). A bad report is rejected whole with a clear error.
- **Devices:** each board logs in to the broker with its own password and may use only its own topics; `DEVICE_ROOMS` limits which rooms each board may report for.
- **Board flooding and forged readings:** each board may send at most one report per room every half report interval; faster ones are dropped and logged. A count that jumps by more than `JUMP_LIMIT` (20) people within one report is held back as a "suspicious reading" (with an alert, at most once an hour per room) and shown only if the next report agrees.
- **Broker:** messages over 4 KB disconnect the sender (`max_packet_size`), and each listener takes at most 50 connections. Optional MQTT over TLS on port 8883 with a locally made CA (`scripts/mqtt_tls.py`). The CA's private key is kept in `deploy/mqtt_ca/`, outside the folder mounted into the broker container, which never needs it.
- **Request size:** 4 KB per request with a body, whatever the method (8 KB for the IoTDA push), and chat questions up to 500 characters.
- **Admin actions** (emergency mode and drills, room marks, chat, labelling, audit log, board list and board address, deleting data, API docs): need an admin token of at least 16 characters, or the server computer itself in local mode when `LOCALHOST_ADMIN` is on, the request carries no proxy header at all, and the Host header is `localhost`, `127.0.0.1` or `[::1]` (a web page whose own domain is made to resolve to 127.0.0.1, "DNS rebinding", gets no admin rights). Tokens are compared in constant time. Named tokens (`scripts/new_token.py --admin <name>`) are kept for the browser tab only (sessionStorage) and the console has a visible Sign out.
- **Cross-site requests:** a POST, PUT, PATCH or DELETE that a browser marks as coming from another site (an `Origin` that is not this server, or `Sec-Fetch-Site: cross-site`) is refused with 403 before it reaches an endpoint. Without this, any website open in a browser on the server computer could press admin buttons as "localhost". No path is exempt, `/iotda` included (IoTDA's push and the boards send no browser headers, so they are not affected). Every path check (cross-site, body size, rate-limit bucket) compares the path after normalising it (one slash between parts, no trailing slash, lower case), so `/iotda/`, `//iotda` and `/IOTDA` cannot slip past a rule written for `/iotda`; the server never redirects `/iotda/` to `/iotda`.
- **Sensor input over HTTP (`/iotda`):** needs `INGEST_TOKEN`. Huawei mode refuses to start without it, and refuses every push if it is somehow empty. In local mode with an empty `INGEST_TOKEN`, every request is refused (401) except one from the server computer itself, by its own loopback name, with no proxy header (for `sim/fake_sensor.py --local`); a token in the URL does not help, and a browser page cannot do it either (cross-site rule above). A board that does hold the token and suddenly reports a room as empty during an emergency is held back by the jump check above. The token travels in the IoTDA push URL, so the server hides `token=...` in uvicorn's access log.
- **API docs:** `/docs`, `/redoc` and `/openapi.json` do not exist in huawei mode (404) and are admin only in local mode.
- **Read access:** optional `VIEWER_TOKEN` (required in huawei mode) for every dashboard read.
- **Client address:** the TCP peer; `X-Forwarded-For` is used only from `TRUSTED_PROXIES`, and then the right-most address that is not a proxy.
- **Brute force and flooding:** 5 wrong admin or viewer tokens in 10 minutes refuse further guesses from that IP for 15 minutes. Per IP and minute: 240 reads, 60 history, energy or summary requests, 30 admin actions, 10 chat questions and 6 emergency presses; over the limit gives 429 with `Retry-After`. Limits are kept in Valkey, so they hold across restarts and server workers (in memory while Valkey is down). `/api/rooms` is cached for 1 second, history is capped at 7 days and 5,000 points, and alerts, audit log and labels are paginated.
- **Browser:** Content-Security-Policy (no inline scripts, no framing), X-Frame-Options DENY, nosniff, no referrer, a restrictive Permissions-Policy. The console never inserts server text as HTML (no `dangerouslySetInnerHTML` or `innerHTML` anywhere in `web/src`).
- **Secrets at start-up:** in huawei mode the server refuses to start while a secret still has its example or docker-compose value or is shorter than 16 characters, or while `VIEWER_TOKEN`, an admin token or `INGEST_TOKEN` is missing; in local mode it warns.
- **Emergency mode:** start and end are atomic, so two wardens pressing at once give one alarm; who did it is kept in an admin-only audit log.
- **Output:** error replies never echo the input.
- **Outages:** if Valkey, MySQL, the broker or the chat model stops, the server keeps running and says what is offline. A room whose sensor stops reporting is shown as unknown, never as empty.
- **Dependencies:** on every push, GitHub Actions (`.github/workflows/ci.yml`, no secrets needed) runs the Python and web tests, `pip-audit` and `npm audit` (fails on high or critical). One known finding is accepted on purpose: pyasn1 0.6.3 (PYSEC-2026-3455, -3456 and -3457), which `huaweicloudsdkcore` 3.1.219 pins below the fixed 0.6.4. It is used only inside the Huawei SDK in huawei mode, and NADI never decodes untrusted ASN.1 with it; CI ignores exactly those three IDs until the SDK allows 0.6.4. A second one, accepted on 2026-10-28: pymongo 4.18.2 (CVE-2026-106435, GHSA-98qm-wvgf-w4cf), which the same SDK pins exactly while the fix is 4.18.3. The flaw crashes a program that decodes untrusted BSON from memory-mapped or array buffers; NADI never decodes BSON, and the SDK only uses it inside huawei mode. CI ignores that ID until the SDK allows 4.18.3. Accepted on 2026-11-02: four more pyasn1 0.6.3 findings (CVE-2026-119194, -119195, -119196 and -119197; GHSA-fm9c-5rcf-2q5p, GHSA-9m75-vc3g-4x39, GHSA-2qm8-x737-gmw5, GHSA-mm57-4v3p-rchx), CPU slow-downs when decoding crafted ASN.1, fixed in 0.6.5. `huaweicloudsdkcore` 3.1.220 (the latest) still pins pyasn1 0.6.3 or older. Same reasoning as above: NADI never decodes untrusted ASN.1. CI ignores those four IDs until the SDK allows 0.6.5.
- **Software bill of materials:** CycloneDX files for the Python server and the web console in [docs/sbom/](docs/sbom/), written by `python scripts/sbom.py`.
- **Secrets:** keys and passwords live in `.env`, which is never committed. gitleaks scans the whole git history on every push, and a pre-commit hook (`git config core.hooksPath scripts/hooks`) scans each commit before it is made ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Boards (firmware)

- **Secrets in flash are not encrypted.** Each board keeps its Wi-Fi password and its MQTT password or IoTDA device secret in flash (NVS, or Preferences on the climate node). Anyone holding a board can read them out over USB.
- **The production fix**, for boards installed in a building: NVS encryption, flash encryption and secure boot (ESP-IDF). These burn one-time eFuses on the ESP32-S3: once on, they cannot be switched off, and a mistake can leave a board unusable. They are **not** enabled on the demo boards, which are reflashed often.
- **Until then:** every board has its own MQTT password (`MQTT_PASSWORD_<ID>`), so a lost board is cut off by removing its user (`scripts/mqtt_users.py`) without changing the others. Keep boards where people cannot take them.
- **Roadmap:** over-the-air updates with signed firmware (ESP-IDF secure OTA with app signing), so a fix reaches every board without opening it and a board accepts only firmware signed by the team.
- Details: [firmware/README.md](firmware/README.md#security).

## Known limits

- MQTT over TLS is optional in local mode; until it is set up, reports cross the Wi-Fi network in plain text (IoTDA mode always uses TLS).
- HTTPS and HSTS belong on the reverse proxy in front of NADI in a real deployment; the server itself speaks plain HTTP.
- The API docs page (local mode, admin) loads Swagger UI from cdn.jsdelivr.net, so it needs internet; `/openapi.json` works offline.
- While Valkey is down, rate limits fall back to memory in each server process.
- Behind a reverse proxy, `TRUSTED_PROXIES` must name it, or every caller shares one limit.
- A board can still send wrong numbers that change slowly; the plausibility check only catches sudden jumps.
- A right admin token is accepted even while its IP is locked out, so a lockout can never keep a warden out during a fire. The defence is a long random token.
- Starting an emergency needs Valkey; if it is down the warden gets a clear error.
- History waiting for MySQL is kept in memory (up to 5,000 rows) and is lost if the server restarts during a MySQL outage.

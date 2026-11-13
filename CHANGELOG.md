# Changelog

Milestones so far, newest first. Dates are the days the work was done.

## 1.0, 2026-11-13

The console as it was reviewed page by page before release (`docs/design/FINAL_REVIEW.md`).

- Overview: building status by group with air conditioning waste today as the highlight, the live floor plan, what
  needs attention, live activity, today's summary, what is counting, and a **People** card for the selected room:
  the count now and since when, and the highest count per step over 1 hour, 24 hours, 7 days or 30 days, with gaps
  where the sensor was offline.
- Optional room capacity, set in the floor plan editor, drawn as a dashed line on the people chart. Not an alert.
- Room panel in reading order: count and nearest exit, people, signal (last 5 minutes against the calibrated
  threshold), temperature and humidity, sensor health.
- Energy: one chart of the building's waste over today, 7 days or 30 days, and the rooms ranked under it (RM, kWh,
  hours); a room in the list filters the chart. Energy settings are changed in the console by an admin and every
  change is kept.
- Buildings and floors with a searchable switcher, a floor plan editor with versions, and Ask NADI answering for the
  floor in view or the whole building.
- Try it without boards: `docker compose --profile demo up --build` runs the server with the demo story in Docker
  (README, "Try it in 5 minutes").
- Emergency view without the drawn route: the rescue order, numbered on the plan, and each room's nearest exit in
  words.
- One rule set for every chart (even ticks, labels clear of the plot, readable legends), one short status label per
  state in both languages, and nothing under 14 px.

## 2026-11-11: Overview redesign

- The Overview is one screen: a CALM / WATCH / ACT status bar with a plain sentence, a large live floor plan, a
  "needs attention" queue (what, where, how bad, what to do), a live activity feed, a live signal chart with the
  "occupied above" threshold, and today's figures. Light theme with the NADI brand colours on the logo, the active
  menu item, headings and the signal chart; status colours unchanged, always with a word or an icon.
- A line between each room's sender and receiver (positions in `dashboard/plan.json`): grey and dashed when the
  sensor is offline, thin when the room is steady, thicker above the threshold. A flat dash travels from sender to
  receiver once per new report; counts roll, a tile's ring fades once and the "Live" dot beats once. Nothing loops,
  nothing moves otherwise, nothing at all during an emergency or drill or with "reduce motion" on.
- One new read-only endpoint, `GET /api/rooms/{id}/signal?minutes=5` (1 to 60): stored CSI reports only, simulator
  rows left out unless the demo scenario is on, the threshold only while the threshold rule is counting.
- One new bundled package, Motion 14.6.0 (MIT); Magic UI's Animated Beam and Number Ticker are copied in and adapted.
- Screenshots from test fixtures in `docs/screenshots/redesign/` (`python scripts/redesign_screenshots.py`).
- A room with no entry in `ROOM_NAMES` goes by the name written on the floor plan (`name` in `dashboard/plan.json`),
  on the plan, in alerts and in chat answers; the room ID shows only for a room that is not on the plan either.
- The 1 h / 24 h / 7 d buttons are not offered on the Overview, which is live and "today so far".
- The tests no longer read the developer's `.env`: `pytest` gives the same result with a calibrated laptop
  `.env` as on a clean checkout.
- Review fixes. With no sensor online the status bar shows a grey "No live data", never a green "Live". The status
  sentence starts with a capital letter in both languages. While its sensor is offline the live signal chart is grey,
  without the band above the threshold, and says "No data since HH:MM".
- "Sensor uptime today" now drops whenever a sensor has been offline. A second read-only endpoint, `GET /api/uptime`,
  works it out from the stored reports: offline time is every gap between two reports longer than three report
  intervals (the rule that shows "offline" on the dashboard), and a sensor that has not reported at all today counts
  from midnight. Shown to one decimal, rounded down, so 100% means nothing was missed.
- The NADI logo replaces the pulse icon in the sidebar (one drawing for the light theme, one for dark, both SVG),
  with the tagline as text under it; the console has a favicon and a touch icon, served by the NADI server.
- The screenshot fixtures are read off one made-up day, so the card, the feed, the chart, the history and the uptime
  agree with each other (`tests/test_fixtures.py` checks it in both languages).
- Design pass. Section headings in sentence case; no text under 14 px anywhere on the page, the sidebar and top
  bar included (the sidebar is one step wider so Malay labels fit). The signal chart has one accent: the teal
  line; the band above the threshold is a neutral step and nothing is filled under the line, so the threshold
  label is sharp in the dark theme. Today's figures are a label, a number and what it counts, without icons.
  No gradient is left on the page.

## 2026-10-28: Realistic demo

- The demo story uses only what one sensor pair can tell: every room on Wi-Fi sensing (0, 1, 2 or 3+), so totals
  stay small ("at least 5 people, in 2 rooms"). The hall that passes 100 people is behind `DEMO_BIG_HALL=on`.
- A count from the "count" service is labelled "Simulated counter (phase 2)" / "Pembilang simulasi (fasa 2)" on the
  floor plan, the Rooms page, the room drawer, the emergency list, the export and the saved snapshots.

## 2026-10-28: Final check before the semi-final

- No path is exempt from the cross-site check any more, `/iotda` included, and every path check compares the
  normalised path (`/iotda/`, `//iotda`, `/IOTDA`); no automatic trailing-slash redirects.
- A fresh copy set up exactly as the README says crashed on every sensor report: `DEVICE_MIN_GAP_S=` (empty, as in
  `.env.example`) now means the default.
- After one failed call to the local chat model, the next questions get the checked answer at once instead of
  waiting for the time limit again.
- Stress scripts: re-runnable within 15 minutes (attack clears its own lockouts), not dependent on the chat model's
  speed, and the long run counts chat messages only.
- Demo runbook rewritten: exact reset, demo and drill steps, and a fallback for everything that can fail on stage.

## 2026-10-26: Drills, incident reports and a security review

- Drill mode: the same emergency screens under a DRILL banner; its alerts say [DRILL] on the dashboard, the console
  and SMN, and its reports are kept apart from real incidents.
- Wardens mark rooms "searched, clear" or "people still inside, need help" during an emergency or drill; shown on
  every screen and the export, audit-logged, cleared when it ends.
- A report for every emergency and drill: start and end, people inside at the start, time for each room to reach
  zero, marks, sensors offline, alerts and acknowledgements. Listed and printable from the Alerts page.
- The export snapshot is saved on the server when the alarm starts and every minute after, as pages that open
  without NADI.
- "Export for Bomba" is now "Export for emergency services", with the number to call (`EMERGENCY_NUMBER`).
- Sensor stopped / back online alerts, critical during a real emergency.
- Delete all stored data (admin action and `scripts/delete_all_data.py`) for PDPA requests.
- Times stored as Unix time and shown in Malaysia time everywhere; a banner when the server clock is more than a
  minute off NTP.
- Security review fixes: cross-site POSTs refused, no localhost admin for a foreign Host name (DNS rebinding),
  `/iotda` needs `INGEST_TOKEN` except from the server computer (always in huawei mode), the token hidden in access
  logs, the MQTT CA key kept out of the broker's folder, the body limit on every method, API docs off in huawei mode
  and admin only in local mode.
- GitHub Actions on every push (tests, pip-audit, npm audit, gitleaks), a gitleaks pre-commit hook, CycloneDX SBOMs
  in `docs/sbom/`, and firmware security notes.

## 2026-10-25: Scale, unknown rooms and security

- Counts from 0 to 1000: a `count` service for exact counters in large rooms; the dashboard shows up to 100, then "100+".
  CSI's "3 or more" is kept as a lower bound and totals say "at least N".
- A room whose sensor stops reporting shows "?" with its last known count, never 0; emergency view, export and
  chat name the unknown rooms. Safety note on the emergency view and the export.
- Charts scale to 5, 25 or 100 people and show the highest count per bucket (1 min, 15 min, 1 h).
- Labelling page: 0 to 5 buttons plus a number field up to 100; the sensor count is hidden while a label runs.
- Header shows rooms reporting; Sensors page hides devices not seen for 24 hours and can clear test devices; the room
  drawer lists every device that reports for the room, the simulator included.
- `scripts/reset_demo_data.py` clears history, alerts and waste totals before a demo; the demo hall counts up past 100.
- Valkey replaces Redis (open source, same protocol).
- Security: localhost admin only without proxy headers (`LOCALHOST_ADMIN`), `TRUSTED_PROXIES`, optional
  `VIEWER_TOKEN` (required in huawei mode), per-IP limits on every request kept in Valkey with `Retry-After`,
  per-board message limits, a plausibility check on counts, broker packet and connection limits, optional MQTT over
  TLS, security headers, named tokens with `scripts/new_token.py`, huawei mode refuses default secrets, 90-day
  history retention, log rotation, and dependency updates from `pip-audit` and `npm audit`.

## 2026-10-25: Enterprise web console

- New web console in `web/` (React, TypeScript, Tailwind, shadcn/ui, Recharts), served by FastAPI from the committed build:
  Overview, Floor plan with room drawer, Rooms, Sensors, Energy, Alerts with shared acknowledge and the admin-only audit
  log, the emergency takeover with a printable export, Ask NADI and the phone labelling page.
- Light and dark themes, time ranges up to 7 days, English and Malay, WCAG AA colours, keyboard navigation.
- New API: long-range history, room climate history, energy (RM, kWh, CO2 estimate), period comparison, alert
  acknowledgement and `GET /api/me`.
- The old vanilla dashboard is removed; demo videos are no longer committed.

## 2026-10-25: Documentation and open-source readiness

- Apache-2.0 licence, notice and third-party licence list.
- User guide, deployment guide, architecture, security, privacy and contributing guides.
- Labelling page for phones (`/label`), calibration helper, one-command retraining that only switches to a model trained on real data that beats the threshold rule.
- Demo scenario mode (`DEMO_SCENARIO=on`) and a recorded 3-minute demo video.

## 2026-10-25: Hardening

- Every sensor report checked before storing; bad reports rejected with clear errors.
- Rate limits, admin token lockout, named admin tokens and an admin-only audit log.
- Emergency start and end made atomic; emergency state survives server and Redis restarts.
- Keeps running when Redis, MySQL, the broker or the chat model stops, with an offline banner on the dashboard.
- Load, attack, outage and 30-minute browser tests ([docs/TESTING.md](docs/TESTING.md)).
- Malformed report fixes and `GET /api/health`, found and fixed with Huawei CodeArts.

## 2026-10-25: Firmware

- ESP32 firmware for the CSI sender, CSI receiver and climate node, compiled in Docker (not yet flashed).
- Mosquitto login with one password per device, and per-device topic limits.

## 2026-10-24: Dashboard and language

- Dashboard rebuilt as an operations console: floor plan, room cards with sparklines, emergency view with rescue order and routes, alerts, chat.
- All wording in English and Malay from one file, with a generated glossary.
- Chat answers only from checked rules; the language model may only rephrase them.

## 2026-10-24: Pipeline

- Simulated sensors to server to Redis and MySQL to dashboard, end to end on one laptop.
- Emergency mode, air conditioning waste flag, alerts and chat.
- Local and Huawei Cloud modes in one codebase; MindSpore-trained model (synthetic data) with a threshold-rule fallback; CodeArts and ModelArts deployment preparation.

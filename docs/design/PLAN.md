# NADI console: build plan, parts 11 to 19

Branch `redesign-overview`. `main` is not touched until the lead says "approved".

**Whoever continues this work reads this file and `docs/design/DIRECTION.md` first and builds to them.** Resume from
the first part not ticked in "Build order". Any deviation from this plan goes into the "Decision log" at the end
(date, what changed, why) *before* the code that does it.

## 0. Ground rules (they bind every part)

- No firmware changes. No change to ingest, MQTT, calibration or headcount logic. Local mode only: no Huawei Cloud
  calls, no runtime CDN.
- Never print `.env` values; never commit `.env` or keys. No material from the lead's employer.
- Every string in English and Bahasa Melayu, in `dashboard/strings.json`; then `python scripts/glossary.py`. Malay
  wording that is unsure gets `"check": "<reason>"`.
- Dark mode works. Status colours are fixed and never the only cue: green occupied/OK, amber A/C waste, red
  emergency, grey dashed offline/no sensor. Purple is interaction, teal is the live signal only.
- Movement is data-driven only; none in emergency/drill or with reduced motion.
- Nothing under 14 px. Works at 1920x1080 and 1366x768. No emoji.
- After each part: pytest, vitest (and e2e when a flow changed), rebuild `web/dist`, commit (plain message, no
  trailers), push, tick the part here, one line in the project brief's Status section.

## 1. Goals and non-goals

Goals
1. The Overview answers three questions without a click: is money being wasted (A/C highlight), where are people
   (plan), and what is each room's sensor seeing (per-room live signal).
2. Lists never grow a card: one rule for the whole console.
3. An admin changes the energy figures from the console, with history, and old figures keep the old rate.
4. More than one building and floor, a switcher that scales, and a floor plan editor an admin can use without
   editing JSON.
5. README and docs a judge can trust; a user-view review; screenshots; a clean trace check.

Non-goals
- No new sensing features, no change to how people are counted.
- No user accounts or roles beyond the existing admin/viewer tokens.
- No polygons in the editor unless rectangles are done and solid first (see part 16).
- No live sensors for the example building: it exists to show the switcher.
- No GIF or video work.

## 2. What exists now (so nobody re-reads the app)

- Server: `server/main.py` (FastAPI, all endpoints), `store.py` (Valkey live state + MySQL history), `logic.py`
  (rules, waste maths, chat rules), `plan.py` (reads `dashboard/plan.json`), `validate.py` (known rooms = plan
  rooms + `ROOM_NAMES`), `security.py` (`SameOrigin` refuses cross-site POST/PUT/PATCH/DELETE), `guard.py` (per-IP
  limits; buckets `read` 240, `history` 60, `admin` 30 per minute; every non-GET `/api/*` except chat is `admin`).
  `BodyLimit` caps every body at 4096 bytes (8192 for `/iotda`). Admin = `Depends(require_admin)`, returns who.
  Audit = `store.audit({...})` (Valkey list, last 200).
- Web: `web/src/pages/*` (overview, floor, rooms, sensors, energy, alerts, calibration, export, report),
  `components/overview/*` (building-status, live-plan, signal-chart, today-card, detection-card, attention,
  activity, section), `components/shell.tsx` (header, sidebar, `BuildingChip`), `lib/api.ts` (TanStack Query hooks),
  `lib/overview.ts` (pure rules), `lib/plan.ts` (static import of `dashboard/plan.json` as `PLAN`).
- Tests: `tests/` (pytest, fakeredis, no MySQL), `web/src/test/` (vitest), `tests_e2e/` (Edge, throwaway
  containers), fixtures for screenshots in `scripts/redesign_screenshots.py`.

Shared pieces added in this round (used by several parts):

| Piece | File | Used by |
|---|---|---|
| `useShowMore`, `ShowMore`, `ViewAll`, `useWholeRows` | `web/src/components/list-limit.tsx` | 13, 14, 15, 16 |
| `GET /api/signals` | `server/main.py`, `store.signals_history` | 13, 14 |
| `server/energy.py` (settings, history, cost maths) | new | 13 (kWh), 15 |
| `server/site.py` (buildings, floors, plan versions) | new | 16 |
| `usePlan()`, `useSite()` | `web/src/lib/site.tsx` | 16 |

---

## PART 12. Final checks from review

**Problem.** Two CI runs were still queued; the Ask NADI footer says "Answers by built-in answers"; the Calibration
screenshot shows 26 empty and 0 occupied labelled reports.

**Decisions**
1. CI: read the runs of the last two pushes with `gh run list`. Queued for long = rerun; failed = fix, push,
   confirm green.
2. Footer wording names where the *numbers* come from, and who *worded* the reply:
   - no model wording the reply (source `fallback`): "Answered from live sensor data."
   - a model worded it (source `ollama` or `maas`): "Worded by {model}. Numbers from live sensor data."
     `{model}` is the server's label ("qwen2.5:3b via Ollama (local)"), so Ollama is never passed off as MaaS.
   - before the first answer the footer follows `GET /api/info` → new field `chat_source` (`"rules" | "ollama" |
     "maas"`, what would answer now). After an answer it follows that answer's `source`.
   - Rejected: "Answers by {model}" with a nicer label (still unclear that numbers are never the model's).
3. Labelled reports: the server query has no bug (reasoned from `main.labelled_points` and
   `store.clear_demo_data`); the fixture's second label segment fell on an "empty" stretch of its made-up day.
   Fix the fixture (second segment is occupied, and `count_at` agrees for those two minutes) and prove the server
   side with a real SQL engine: sqlite3 in memory standing in for MySQL (`%s` → `?`).

**Files.** `web/src/components/chat-panel.tsx`, `server/main.py` (`api_info`), `web/src/lib/types.ts`,
`dashboard/strings.json`, `scripts/redesign_screenshots.py`, `tests/test_fixtures.py`, new `tests/test_reset.py`,
`web/src/test/shell.test.tsx`.

**Strings**

| Key | English | Malay |
|---|---|---|
| `chat.foot_rules` | Answered from live sensor data. | Dijawab daripada data sensor langsung. |
| `chat.foot_model` | Worded by {model}. Numbers from live sensor data. | Ayat disusun oleh {model}. Angka daripada data sensor langsung. |

Remove `chat.answers_by`, `chat.answered_by`.

**Acceptance**
- Both CI runs green (or rerun green).
- Footer never shows "built-in answers"; with Ollama stopped it reads "Answered from live sensor data."; with a
  model reply it names the model and says the numbers are from sensor data; Malay equivalents under `?lang=ms`.
- `tests/test_reset.py`: after `clear_demo_data(keep=labels)` rows inside a 0-label and inside a >0-label segment
  both remain, rows outside are gone, and `labelled_points` returns both kinds.
- Calibration fixture shows empty and occupied dots; `tests/test_fixtures.py` asserts both.

**Risk / cut.** None; each item is independent.

---

## PART 13. Overview: status, today's summary, per-room live signal

### 13.1 Building status card

**Problem.** Money wasted today is the daily reason to open NADI, and it sits as one small pill among four groups.
"Emergency: Normal" takes a quarter of the card to say nothing.

**Decision.** Three groups. The first, twice as wide, is the highlight: "Air conditioning waste today" with the RM
figure at Figure size (24 px, amber when above 0), kWh beside it, then the pill ("1 empty with A/C on" amber /
"No waste" green / "No live data" grey dashed). Rooms and Sensors keep their pills. The overall pill stays at the
top right. Emergency leaves the card (header button + takeover cover it); its normal-day line moves to Today's
summary. The highlight is made by size and position only: no tint, no stripe, no card in a card.

Rejected: a separate KPI tile row (one more band, pushes the plan down); a coloured banner (decoration).

```
1920 and 1366 (same grid, 2fr 1.5fr 1fr; below 640 px the groups stack)
+ Building status -------------------------------------------- ( o 1 needs attention ) +
| Air conditioning waste today        | Rooms                      | Sensors          |
| RM 1.10   3.7 kWh  (! 1 empty with  | (o 1 occupied) (- 2 no     | (o 1 online)     |
|                      A/C on)        |  sensor)                   |                  |
+-------------------------------------------------------------------------------------+
```

kWh comes from the server: `GET /api/rooms` gains `waste_today_kwh` (part 13: RM / tariff; part 15: stored kWh, so
it stays right across a tariff change).

### 13.2 Today's summary

**Decision.** Card title "Today's summary", link "View full summary" with an arrow in the title row (same pattern
as "Open room signal"). Rows: Peak people, Hours occupied, Sensor uptime, Emergency and drills. The A/C waste row
leaves (it is the highlight above). The emergency row: value "Normal" (or "Drill" / "Emergency" while one runs),
hint "No drill today" / "1 drill today, last at 10:42" / "Last drill: 3 Nov". Data: existing `GET /api/incidents`.

The link opens a new page `/summary` ("Today's summary"): the day's people chart (existing `OccupancyChart`, all
rooms), a per-room table (peak, hours occupied, sensor uptime, A/C waste RM today) and today's emergencies and
drills with links to their reports. Built only from existing endpoints (`/api/history`, `/api/uptime`,
`/api/energy`, `/api/incidents`); no new API. Not in the sidebar: it is a detail of the Overview, with a "Building
summary" back link in its title row.

Rejected: Energy page (covers one of the four rows); a printable daily report (new server work, a later feature).

### 13.3 Per-room live signal

**Decision: click selects, the card follows, a link opens.**
- On the Overview plan a click, tap, Enter or Space on a room **selects** it: the tile gets a 3 px purple ring and a
  small purple corner tab with a tick (shape, not only colour), `aria-pressed="true"`.
- The Live signal card shows the selected room. Its title row has a room `<select>` (every room on the plan plus
  reporting rooms not on it) that does the same.
- **Opening the full room panel:** the "Open room signal" link in the card (always visible, keyboard reachable),
  or a double-click on a tile. Both go to `/floor?room=ID&section=signal`.
- Rejected: click opens the panel as before (then nothing can select); a button inside each tile (a button inside
  a button is invalid, and the tiles are small at 1366).

Selection state
1. `?room=ID` in the address, when ID is a room on the plan or a reporting room.
2. else the viewer's last choice (`localStorage` key `nadiOverviewRoom`, in try/catch), when still a known room.
3. else the default, worked out once when room data first arrives and then kept for the life of the page (it must
   not jump between rooms by itself): the live sensing room that is occupied now with the newest report ("most
   recent movement" from the data the console has), else the first live sensing room (one with its boards on the
   plan first), else the first room with a sensor pair on the plan, else the first room on the plan.
An explicit choice writes `?room=` (replace, other parameters such as `lang` kept) and `localStorage`. The default
is not written to the address.

States of the card for the selected room
| Room | Card shows |
|---|---|
| live Wi-Fi sensing room | the chart (as now) |
| sensor offline | the existing grey chart with "No data since HH:MM" |
| on the plan, never reported, no sensor pair drawn | dashed circle icon + "No sensor in this room". No chart, no request. |
| on the plan, never reported, pair drawn | "No report from this room yet" |
| counted by the "count" service | "This room is counted by a people counter, so there is no Wi-Fi signal to show." |
| history database down | existing amber line |

Request load. Today every live tile asks `GET /api/rooms/{id}/signal` every 5 s: N requests per poll. New
`GET /api/signals` returns the last minutes of every sensing room in one answer; the Overview makes **one** signal
request per 5 s whatever the number of rooms, and the tiles' sparklines, the lines between the boards and the
Live signal card all read from it. The room panel keeps the per-room endpoint (one room). Polling stops while the
tab is hidden (TanStack Query default) and when the Overview is not mounted.

```
GET /api/signals?minutes=5          viewer; "read" bucket; minutes 1..10
200 {"now": 1793700000, "minutes": 5, "threshold": 1.301 | null,
     "rooms": {"room1": {"now":..., "room_id":"room1", "minutes":5, "threshold":..., "last_report_ts":...,
                         "points":[{"ts":..., "motion_std":0.41, "headcount":0}, ...]}},
     "truncated": false}
503 while MySQL is offline (same wording as /api/rooms/{id}/signal)
```
Server: `store.signals_history(since, skip_sources, limit)` is ONE query for all rooms
(`WHERE ts >= %s AND motion_std IS NOT NULL ... ORDER BY ts DESC LIMIT 6000`), cached 2 s behind a lock like
`signal_rows` (10-minute window kept, the minutes asked for are cut from it). At most `SIGNALS_MAX_ROOMS = 64`
rooms, `truncated` says so. Simulator rows skipped unless the demo scenario is on (same rule as the per-room
endpoint). No table or index change (`occupancy_ts` covers it).

```
1920x1080                                                1366x768 (same, page scrolls about 190 px)
+ Building status (13.1) ----------------------------+
+ Live floor plan (65%) -------+ + Needs attention --+   plan keeps its height; the bottom row keeps 250 px
| [Hall A]  [[Lab 2 v]]        | | ...  View all 12 >|
| [Room 3]   ^ selected ring   | + Live activity ----+
| legend + "Select a room..."  | | ...  View all 14 >|
+------------------------------+ +-------------------+
+ Live signal [Lab 2 v] Open room signal > --+ + Today's summary  View full summary > + + Detection +
| chart of the selected room                 | | Peak people ... Emergency and drills | |           |
+--------------------------------------------+ +--------------------------------------+ +-----------+
```

**Files.** `web/src/pages/overview.tsx`, `components/overview/{building-status,today-card,signal-chart,live-plan}.tsx`,
`lib/overview.ts` (`buildingStatus` without the emergency group, `defaultRoom`, `pickRoom`, `drillLine`),
`lib/api.ts` (`useSignals`), `lib/types.ts`, new `pages/summary.tsx`, `App.tsx` (route), `server/main.py`
(`api_signals`, `waste_today_kwh`), `server/store.py` (`signals_history`), `scripts/redesign_screenshots.py`
(fixture answers for `/api/signals`).

**Strings**

| Key | English | Malay |
|---|---|---|
| `bs.ac_today` | Air conditioning waste today | Pembaziran penghawa dingin hari ini |
| `bs.kwh` | {kwh} kWh | {kwh} kWj |
| `ov.today_label` (changed) | Today's summary | Ringkasan hari ini |
| `ov.today_full` | View full summary | Lihat ringkasan penuh |
| `ov.today_incidents` | Emergency and drills | Kecemasan dan latihan |
| `ov.today_normal` | Normal | Biasa |
| `ov.today_no_drill` | No drill today | Tiada latihan hari ini |
| `ov.today_drills_one` | 1 drill today, last at {time} | 1 latihan hari ini, terakhir pada {time} |
| `ov.today_drills_many` | {n} drills today, last at {time} | {n} latihan hari ini, terakhir pada {time} |
| `ov.today_last_drill` | Last drill: {date} | Latihan terakhir: {date} |
| `ov.today_emergencies` | {n} emergency today | {n} kecemasan hari ini |
| `sig.room` | Room shown | Bilik dipaparkan |
| `sig.none_here` | No sensor in this room | Tiada sensor di bilik ini |
| `sig.none_here_hint` | Choose a room with a sensor pair to see its signal. | Pilih bilik yang mempunyai pasangan sensor untuk melihat isyaratnya. |
| `sig.not_yet` | No report from this room yet | Belum ada laporan dari bilik ini |
| `sig.counter` | This room is counted by a people counter, so there is no Wi-Fi signal to show. | Bilik ini dikira oleh pembilang orang, jadi tiada isyarat Wi-Fi untuk dipaparkan. |
| `plan.selected` | selected | dipilih |
| `plan.select_hint` | Select a room to see its live signal. Double-click to open the room. | Pilih bilik untuk melihat isyarat langsungnya. Klik dua kali untuk membuka bilik. |
| `sum.title` | Today's summary | Ringkasan hari ini |
| `sum.description` | People, sensors and air conditioning waste since midnight. | Orang, sensor dan pembaziran penghawa dingin sejak tengah malam. |
| `sum.back` | Building summary | Ringkasan bangunan |
| `sum.people` | People today | Orang hari ini |
| `sum.by_room` | By room | Mengikut bilik |
| `sum.col_peak` / `sum.col_hours` / `sum.col_uptime` / `sum.col_waste` | Peak people / Hours occupied / Sensor uptime / A/C waste | Orang paling ramai / Jam berpenghuni / Masa operasi sensor / Pembaziran penghawa dingin |
| `sum.incidents` | Emergencies and drills today | Kecemasan dan latihan hari ini |
| `sum.incidents_none` | None today. | Tiada hari ini. |

(kWh in Malay: check whether "kWj" or "kWh" is used on TNB bills; flag `bs.kwh` [CHECK].)

**States.** Loading: skeleton lines (existing). Server lost: groups show the grey "Not live" pill, the highlight
figure shows "–". MySQL down: signal card amber line, tiles draw no sparkline, the plan still works (it reads
`/api/rooms`). No rooms at all: card says "No sensor in this room" for the default plan room.

**Acceptance**
- Building status has three groups; the first shows RM (24 px), kWh and one pill; no Emergency group.
- "Today's summary" has four rows incl. the emergency/drill line; "View full summary" opens `/summary`.
- Clicking Hall A on the plan rings it, the card title row names Hall A and the card says "No sensor in this
  room"; the address has `?room=room2`; a refresh keeps it; the dropdown shows the same room.
- With the address cleared, the last choice comes back from the browser; with storage blocked the default is used
  and nothing throws.
- Double-click on a tile and "Open room signal" both open that room's panel at its Signal section.
- Keyboard: Tab reaches each tile, Enter selects, focus ring visible.
- Network: with 13 sensing rooms the Overview sends one `/api/signals` request per poll and no
  `/api/rooms/{id}/signal`.
- No movement in emergency/drill or reduced motion (unchanged rule).

**Tests.** vitest: `defaultRoom` / `pickRoom` order (URL, storage, default, unknown IDs ignored), URL written on
select, storage failure tolerated, the five card states, building status groups, drill line wording, 13-room
request count (fetch spy). pytest: `/api/signals` (shape, viewer token, read bucket, one MySQL query per 2 s for
any number of rooms, simulator rows skipped, 503 when MySQL is down, 64-room cap). e2e: select a room, refresh,
open its panel.

**Risk / cut.** If `/api/signals` is not solid: keep per-room requests but only for the selected room and tiles
(as now) and log it. `/summary` can be cut by pointing the link at `/energy` (log it).

---

## PART 14. Calibration layout and list limits everywhere

### 14.1 Calibration

```
1920 (two columns, stretched to the same height)        1366 (same; below 1280 px one column)
+ Label headcount ---------------+ + Model training · Huawei MindSpore +
| room, 0..5, number, Stop       | | status + facts table              |
|                                | +-----------------------------------+
| Recent labels (10, Show more)  | + Labelled reports      [Lab 2 v]   |
|                                | | dots chart of ONE room            |
+--------------------------------+ +-----------------------------------+
+ Live detector ---------------------------------------------------------------------+
| Room      | Counting by            | Threshold or model      | Last reading         |
| Lab 2     | Calibrated rule        | 1.30 dB                 | 0.41 dB at 10:42:10  |
| Hall A    | No sensor              | –                       | –                    |
| (10 rows, then "Show 3 more")                                                       |
+------------------------------------------------------------------------------------+
```

**Decisions**
- Grid `items-stretch`; the left card and the right column are both `h-full`; "Labelled reports" takes the space
  left in the right column. Labelled reports shows **one room at a time** (it follows the room chosen in the
  labeller, and has its own select), so the right column's height does not depend on how many rooms are labelled.
- "Live detector" moves below both, full width, as a table with one row per room (plan rooms + reporting rooms):
  room, what counts it (Calibrated rule / MindSpore model / People counter / No sensor), threshold or model name,
  last reading (motion figure and time from `GET /api/signals`; "No report yet" / "–").
- Rejected: equal heights by a scroll box in the left card (hides the controls on small screens).

API: `GET /api/labels` returns the last 50 labels instead of 5 (`labels.recent(50)`); nothing else changes.

### 14.2 The list rule (one rule, whole console)

| Kind | Rule | Component |
|---|---|---|
| Long feed (alerts, live activity, needs attention) | At most 10 rows, fewer when the card is shorter: only whole rows are drawn, never half a row and never a scroll box. When anything is hidden, a "View all N" link with an arrow sits at the bottom of the card and opens the full page. | `useWholeRows` + `ViewAll` |
| Short secondary list (recent labels, live detector, settings history, audit log, incident reports, room devices, energy by room, summary by room, building switcher) | 10 rows, then a "Show N more" button. Expanded: the list scrolls inside the card at a fixed maximum height (`max-h-[26rem]`), and the button reads "Show fewer". | `useShowMore` + `ShowMore` |
| The page's own main table (Rooms, Sensors, Alerts with paging, Summary) | It is the full list: the page scrolls. Alerts keeps its filters and 50-per-page paging. | – |
| Safety lists (emergency "Utamakan bilik ini", export, incident report) | Exempt: every room with people must be visible or printed. | – |

`web/src/components/list-limit.tsx`
```ts
export const LIST_LIMIT = 10;
useShowMore<T>(items: T[], limit = LIST_LIMIT): { shown: T[]; hidden: number; expanded: boolean; toggle(): void }
<ShowMore hidden expanded onToggle controls=id />      // button, aria-expanded, aria-controls
<ViewAll to="/alerts" count={n} label? />              // link with ArrowRight, "View all 14"
useWholeRows(ref): number | null   // how many direct children fit whole in the box; null before layout / in tests
```

Audit and what changes

| Place | Now | Change |
|---|---|---|
| Overview, Live activity | scroll box, up to 20 | whole rows up to 10, "View all N" → `/alerts` |
| Overview, Needs attention | scroll box | whole cards up to 10, "View all N" → `/alerts#attention` |
| Overview, rooms not on the plan | all names in a sentence | first 10, then "and N more" → `/rooms` |
| Alerts page | table, 50 per page | unchanged (full page); new first panel "Needs attention now" (`id="attention"`) listing every item |
| Alerts page, audit log | 100 rows in a 420 px scroll box | Show more rule |
| Alerts page, incident reports (two tables) | all rows | Show more rule, each table |
| Rooms, Sensors | main tables | unchanged (full page) |
| Room panel, devices | all | Show more rule |
| Energy, by room | chart grows 46 px per room | top 10 by RM this week, Show more expands (scroll) |
| Calibration, recent labels / live detector | 5 / n.a. | Show more rule |
| Energy settings history (15), switcher (16), plan versions (16) | n.a. | Show more rule |

**Strings**

| Key | English | Malay |
|---|---|---|
| `list.view_all` | View all {n} | Lihat semua {n} |
| `list.show_more` | Show {n} more | Papar {n} lagi |
| `list.show_fewer` | Show fewer | Papar kurang |
| `list.and_more` | and {n} more | dan {n} lagi |
| `alerts.attention_now` | Needs attention now | Perlu perhatian sekarang |
| `cal.live_title` | Live detector | Pengesan semasa |
| `cal.col_counting` | Counting by | Dikira oleh |
| `cal.col_threshold` | Threshold or model | Ambang atau model |
| `cal.col_last` | Last reading | Bacaan terakhir |
| `cal.by_rule` | Calibrated rule | Peraturan terkalibrasi |
| `cal.by_model` | MindSpore model | Model MindSpore |
| `cal.by_counter` | People counter | Pembilang orang |
| `cal.last_at` | {x} dB at {time} | {x} dB pada {time} |
| `cal.dots_room` | Room shown | Bilik dipaparkan |

**Acceptance**
- Calibration at 1920 and 1366: the bottoms of "Label headcount" and "Labelled reports" line up (within 1 px);
  "Live detector" spans the full width below and lists every room.
- With 13 alerts the Overview's Live activity shows whole rows only and "View all 13"; no scroll bar inside the
  card; the link opens Alerts.
- With 13 labels: 10 rows and "Show 3 more"; expanded, the card does not grow past its maximum height and scrolls
  inside; "Show fewer" restores.
- No card on any page changes the position of its neighbours when a list gets longer (checked with 13-item fixtures).

**Tests.** vitest: `useShowMore` (10 / expand / collapse / fewer than 10 shows no button), `ViewAll` count and
target, Live activity with 13 alerts, recent labels with 13, detector table rows and wording per kind, energy by
room with 13 rooms. pytest: `/api/labels` returns up to 50. Browser check (screenshot script `--measure`): column
bottoms on Calibration.

**Risk / cut.** `useWholeRows` depends on layout measurement; if it flickers, fall back to a fixed count per
breakpoint (5 at 1366, 8 at 1920) and log it.

---

## PART 15. Admin energy settings

**Problem.** Tariff, A/C power, the "A/C counts as on" temperature, the waste delay and the CO2 factor live in
`.env` or in code; changing one means editing a file and restarting, and a change would silently restate the past.

### Data and maths

Settings (one versioned record; every save stores all values):

| Field | Unit | Default | Allowed |
|---|---|---|---|
| `tariff_rm_per_kwh` | RM per kWh | `TARIFF_RM_PER_KWH` (0.2983) | 0.01 to 5 |
| `ac_kw` | kW | `AC_KW` (10) | 0.1 to 500 |
| `ac_kw_rooms` | kW per room ID | none | each 0.1 to 500; room must be known; at most 100 rooms |
| `ac_on_below_c` | °C | 26.0 | 16 to 35 |
| `waste_after_min` | minutes | `WASTE_MINUTES` (10) | 1 to 240 |
| `co2_kg_per_kwh` | kg per kWh | `CO2_KG_PER_KWH` (0.75) | 0.01 to 2 |

Storage: MySQL table (created in `store.init` with the others; no migration of existing tables).
```sql
CREATE TABLE IF NOT EXISTS energy_settings (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  effective_from INT NOT NULL,
  changed_by VARCHAR(64) NOT NULL,
  tariff_rm_per_kwh DOUBLE NOT NULL, ac_kw DOUBLE NOT NULL, ac_kw_rooms TEXT NOT NULL,   -- JSON object
  ac_on_below_c DOUBLE NOT NULL, waste_after_min DOUBLE NOT NULL, co2_kg_per_kwh DOUBLE NOT NULL,
  INDEX (effective_from)
)
```
- No rows = the `.env` values apply ("defaults", effective from the beginning). The first save writes the first
  row. Once a row exists the database wins over `.env`.
- `server/energy.py` keeps the versions in memory: loaded at start-up, after every save, and re-read every 30 s
  and when MySQL comes back. MySQL down: the versions in memory stay in force (`source: "last_known"`); cold
  start with MySQL down: `.env` defaults (`source: "defaults"`, `database: false`) until it is back. The console
  says which.
- **Effective-from maths.** The cost of a waste stretch is integrated piecewise over the versions:
  `energy.cost(since, until, room_id) -> {"kwh", "rm", "co2_kg"}` = sum over each version period overlapping
  [since, until] of `kW(room) x hours x (1, tariff, co2)`. So a new rate applies from the second it is saved, and
  the part of a running stretch before the save keeps the old rate.
- Finished stretches are added to the day totals when they end (as now), now in three units: Valkey
  `waste_rm:{day}[:room]` (exists), new `waste_kwh:{day}[:room]`, `waste_co2:{day}[:room]`. Past days therefore
  keep the rate in force then. Days stored before this change have RM only: kWh = RM / tariff in force at the end
  of that day, CO2 = kWh x factor in force then.
- The waste rule reads the live settings: "empty and colder than `ac_on_below_c`" starts the timer, the flag shows
  after `waste_after_min`. The demo scenario's own 60 s delay keeps working (it overrides the delay while it runs).
- `logic.py` keeps `AC_KW`, `TARIFF_RM_PER_KWH`, `WASTE_AFTER_S`, `AC_ON_BELOW_C` as the defaults;
  `update_empty_cold_since` and `waste_info` take the live values as arguments. No headcount code is touched.

### API

```
GET /api/energy/settings                      viewer; "read" bucket
200 {"now":..., "settings": {"tariff_rm_per_kwh":0.2983,"ac_kw":10,"ac_kw_rooms":{"room1":3.5},
                              "ac_on_below_c":26,"waste_after_min":10,"co2_kg_per_kwh":0.75},
     "effective_from": 1793700000 | null, "changed_by": "admin" | null,
     "source": "database" | "defaults" | "last_known",
     "limits": {"tariff_rm_per_kwh":[0.01,5], ...},
     "history": [{"id":7,"effective_from":...,"changed_by":"admin","settings":{...}}, ...],   // newest first, up to 50
     "history_total": 7}

PUT /api/energy/settings?lang=en|ms           admin (require_admin); "admin" bucket (30/min); SameOrigin; 4 KB body
body: the six settings fields, all required, numbers only (strict)
200 {"ok": true, "changed": true, ...same as GET}        changed:false when nothing differs (no row, no audit)
422 {"detail": "<all messages joined>", "errors": {"tariff_rm_per_kwh": "<message in lang>", ...}}
503 while MySQL is offline (a change that cannot be stored is refused)
```
Audit: `{"ts","action":"energy_settings","by","ip","changes":{"tariff_rm_per_kwh":[0.2983,0.35],...}}`; the audit
table on the Alerts page shows it as "Energy settings changed" with "old → new" per field.

`GET /api/energy` gains `rate_changes: [{"ts","by"}]` (saves in the last 14 days) and reads its amounts from the
stored kWh/CO2; `GET /api/rooms` → `waste_today_kwh` from the same; each room's `waste` gains `kwh`;
`GET /api/info` → `waste_minutes` from the live settings.

### UI (Energy page)

```
+ KPI strip (as now) ----------------------------------------------------------------+
+ "Rate changed on 12 Nov 2026. Figures before then use the earlier values."  (only when a save falls in the period)
+ Waste by room -----------------+ + Waste by day ---------------------+
+ Energy settings ------------------------------- [Edit] + + How the figures are worked out +
| Electricity tariff           RM 0.2983 per kWh         | | (existing notes, now with the  |
| Air conditioner power        10 kW                     | |  live values)                  |
|   Lab 2                      3.5 kW                    | |                                |
| A/C counts as on below       26.0 °C                   | |                                |
| Waste flagged after          10 minutes                | |                                |
| CO2 factor                   0.75 kg per kWh           | |                                |
| Last changed by admin on 12 Nov 2026, 14:02            | |                                |
| Change history (10 rows, Show more)                    | |                                |
+--------------------------------------------------------+ +--------------------------------+
```
- Viewer: read-only values with units and "Last changed by X on Y" (or "Default values from the server
  configuration"). Source `last_known` / `defaults` while the database is down: an amber line says so.
- Admin: "Edit" turns the values into labelled number inputs with the unit after each, a per-room table with "Add
  room" (select of known rooms) and remove; "Save" opens a confirmation that lists every change ("Electricity
  tariff: RM 0.2983 → RM 0.3500 per kWh") and says "Applies from now. Earlier figures keep the earlier values.";
  "Cancel" restores. Client-side validation mirrors the server's limits; server errors land under their field
  (`aria-describedby`, `role="alert"`).
- Change history: date, who, and what changed against the version before; Show more rule.
- Rooms page: "On (below N °C)" uses the live value (the hard-coded 26 in `rooms.tsx` goes).

**Files.** New `server/energy.py`; `server/main.py` (endpoints, `check_waste`, `room_views`, `api_energy`,
`api_info`), `server/store.py` (table, `add_waste_today` in three units, demo/privacy key patterns),
`server/logic.py` (arguments), `server/demo.py` (delay override), `server/privacy.py` (patterns + table);
web: new `components/energy-settings.tsx`, `pages/energy.tsx`, `pages/rooms.tsx`, `pages/alerts.tsx` (audit row),
`lib/api.ts` (`useEnergySettings`, `putJSON`), `lib/types.ts`; `docs/DEMO_RUNBOOK.md`; `.env.example` (comment:
these are first-start defaults).

**Strings** (main ones; field errors follow one pattern)

| Key | English | Malay |
|---|---|---|
| `es.title` | Energy settings | Tetapan tenaga |
| `es.tariff` | Electricity tariff | Tarif elektrik |
| `es.ac_kw` | Air conditioner power | Kuasa penghawa dingin |
| `es.ac_kw_room` | Power for one room | Kuasa untuk satu bilik |
| `es.ac_on_below` | Air conditioning counts as on below | Penghawa dingin dikira hidup di bawah |
| `es.waste_after` | Waste flagged after | Pembaziran ditanda selepas |
| `es.co2` | CO2 factor | Faktor CO2 |
| `es.unit_tariff` / `es.unit_kw` / `es.unit_c` / `es.unit_min` / `es.unit_co2` | RM per kWh / kW / °C / minutes / kg per kWh | RM setiap kWj / kW / °C / minit / kg setiap kWj |
| `es.edit` / `es.save` / `es.cancel` | Edit / Save / Cancel | Sunting / Simpan / Batal |
| `es.add_room` / `es.remove_room` | Add a room / Remove {name} | Tambah bilik / Buang {name} |
| `es.changed_by` | Last changed by {who} on {date} | Kali terakhir diubah oleh {who} pada {date} |
| `es.defaults` | Default values from the server configuration | Nilai lalai daripada konfigurasi pelayan |
| `es.last_known` | The database is offline: these are the last known values. | Pangkalan data di luar talian: ini nilai terakhir yang diketahui. |
| `es.cold_defaults` | The database is offline: default values are in use until it is back. | Pangkalan data di luar talian: nilai lalai digunakan sehingga ia pulih. |
| `es.confirm_title` | Save these changes? | Simpan perubahan ini? |
| `es.confirm_note` | Applies from now. Earlier figures keep the earlier values. | Berkuat kuasa mulai sekarang. Angka terdahulu mengekalkan nilai terdahulu. |
| `es.change` | {label}: {old} → {new} | {label}: {old} → {new} |
| `es.saved` | Saved. The new values apply from {time}. | Disimpan. Nilai baharu berkuat kuasa mulai {time}. |
| `es.nothing` | Nothing was changed. | Tiada perubahan. |
| `es.history` | Change history | Sejarah perubahan |
| `es.rate_changed` | Rate changed on {date}. Figures before then use the earlier values. | Kadar diubah pada {date}. Angka sebelum itu menggunakan nilai terdahulu. |
| `es.err_range` | {label} must be between {min} and {max} {unit}. | {label} mesti antara {min} dan {max} {unit}. |
| `es.err_number` | {label} must be a number. | {label} mesti berupa nombor. |
| `es.err_room` | {room} is not a known room. | {room} bukan bilik yang dikenali. |
| `es.err_offline` | The database is offline, so the change cannot be saved. | Pangkalan data di luar talian, jadi perubahan tidak dapat disimpan. |
| `alerts.audit_energy` | Energy settings changed | Tetapan tenaga diubah |

**Acceptance**
- A viewer sees the values and who changed them last; no Edit button.
- An admin edits, sees the list of changes, saves; the card shows the new values at once; the audit log has the
  entry with old → new; a second identical save says "Nothing was changed".
- Tariff −1, kW 0, 60 °C, text in a number field: refused in the form and by the API (422) with the message in the
  page's language.
- A running waste stretch that spans a tariff change costs old-rate x time-before + new-rate x time-after
  (pytest with fixed times). Yesterday's RM/kWh/CO2 are the same before and after the save.
- "Rate changed on <date>" shows on the Energy page when a save falls inside the last 14 days.
- Waste delay 1 minute can be set and takes effect on the next report; `docs/DEMO_RUNBOOK.md` says how to set it
  back.
- MySQL stopped: GET still answers with `source` saying so; PUT answers 503 with the message; the waste flag keeps
  working.
- Cross-site PUT refused (403), no token from another machine refused (401/403), 31st change in a minute 429.

**Tests.** pytest `tests/test_energy_settings.py`: auth (viewer GET, admin PUT, wrong token, cross-site), each
validation error in both languages, history order and `changed_by`, no-op save, piecewise cost across one and two
changes and with a per-room override, day totals in three units, legacy RM-only days, DB-down fallback (last
known and cold start), audit entry, rate limit, `/api/energy` `rate_changes`, `/api/info` waste minutes, waste
rule with a changed temperature and delay. vitest: read-only vs edit, validation messages, confirmation list,
error from the server under its field, history Show more.

**Stage-safe.** When this part is green: `git tag stage-safe && git push origin stage-safe`. Everything the stage
demo needs is in that tag. Later parts must not change what it does.

**Risk / cut.** If the three-unit day totals are not solid, keep RM stored and derive kWh from the tariff in force
at the end of each day (already the legacy path) and log it. The per-room override can be cut from the UI (API
keeps accepting `{}`), logged.

---

## PART 16. Buildings, floors and floor plans

The most expensive part. It is built in five steps; each step leaves the console working, and the editor
(steps 3 to 5) sits behind `PLAN_EDITOR` (`.env`, default `on` once solid; `off` hides the editor and refuses its
write endpoints with 404). If a step is not solid by its checks, stop there, set the flag off or revert the step,
write it in the Decision log, and go to part 17.

### Data model

Stored as files, not in MySQL: the emergency view must draw its plan when the history database is down, and a
plan is a document with versions. `SITE_DIR` (default `data/site`, already git-ignored under `data/`), written
atomically (`os.replace`), same approach as the incident reports.

```
data/site/site.json                         buildings and floors (below)
data/site/plans/<floor_id>/v000001.json     {"version":1,"saved_ts":...,"saved_by":"admin","note":"...","plan":{...}}
data/site/images/<sha256>.<png|jpg>         uploaded backgrounds, named by content hash
```
```json
{"buildings": [
  {"id": "b1", "name": "Demo Building", "code": "DEMO",
   "floors": [{"id": "f1", "name": "Level 4", "level": 4}]}]}
```
- Built in, never stored: building `b1` / floor `f1` take their names from `BUILDING_NAME` / `LEVEL_NAME` until an
  admin renames them, and `f1`'s plan is `dashboard/plan.json` until a version is saved for it (that file is
  "version 0" and can always be restored).
- Example building, built in and read-only: id `example`, name "Example Tower (example data)", code `EX-01`,
  12 floors made from the corridor template with rooms `ex-l01-a` ..., `"example": true`. No sensors: every room
  reads "No sensor". Its rooms are **not** known rooms (no board can report for them). Hidden with
  `EXAMPLE_BUILDING=off`.
- IDs: building `b` + number, floor `f` + number (server-assigned). Room IDs: `[a-z0-9][a-z0-9_-]{0,31}`, unique
  across every floor of every building. Existing room IDs (`room1` ...) are untouched.
- Known rooms (`validate.known_rooms`) = rooms of every non-example floor's current plan + `ROOM_NAMES`. So MQTT
  room IDs that work today keep working, and a room an admin draws becomes reportable.
- Plan document: today's format plus optional fields. Everything is in the 1000 x 560 box.
```json
{"viewBox":[0,0,1000,560], "outline":{"x","y","w","h"}, "corridor":{...} | null,
 "rooms": {"room1": {"name":"Lab 2","x","y","w","h","door":{"x","side":"n|s"},"exit":"stairB",
                     "link":{"send":{"x","y"},"recv":{"x","y"}}, "area_m2": 48}},
 "exits": {"stairA": {"label":"plan.stair_a" | "name":"Stair A", "kind":"stair|exit", "x","y","w","h","door":{...}}},
 "other": [{"label":"plan.toilets" | "name":"Store", "x","y","w","h"}],
 "background": {"image":"<sha256>.png","opacity":0.5} | null}
```
  `label` is a strings key (the built-in plan); `name` is free text typed by an admin, shown as written in both
  languages (like room names). A room's A/C power is **not** stored on the plan: it is the per-room override in
  Energy settings (one source, with history); the editor shows it and links there.

### Server (`server/site.py`, `server/plan.py`)

- `site.load()`, `site.floors()`, `site.plan(floor_id)`, `site.save_plan(floor_id, plan, by, note)`,
  `site.versions(floor_id)`, `site.restore(floor_id, version, by)`, `site.add_building`, `site.add_floor`,
  `site.rename`, `site.validate_plan(plan, floor_id) -> [error keys with values]`.
- `server/plan.py` keeps its API (`PLAN`, `exit_name`, `room_names`) as a merged, current view over all
  non-example floors, refreshed after every save, so chat answers ("which room first", stair names), room names
  and known rooms follow the saved plans. Exit names: `label` key or `name`.
- Validation before any save (all errors returned at once, nothing written on error):
  rectangles inside the box and at least 40 x 40; rooms must not overlap each other or the exits (touching edges
  is fine); at least one exit on the floor; every room names an exit that exists; room IDs well formed, unique on
  the floor and not used on another floor; names 1 to 40 characters; sender and receiver inside their room and at
  least 30 units apart; at most 60 rooms; **a room with a reporting sensor may not be removed or renamed by ID**
  (so a save cannot make a live board's reports "unknown room"); background image must exist; document at most
  64 KB. A plan that fails stays out: the current plan stays live.
- Versions: every save is a new version (kept: last 30 per floor). Restore = a new version with the content of an
  old one (history stays linear), validated again against the current state.

```
GET  /api/site                                viewer, read
     {"buildings":[{"id","name","code","example":false,"floors":[{"id","name","level","rooms":3,"version":2}]}],
      "default_floor":"f1","editor":true}
GET  /api/floors/{floor_id}/plan              viewer, read      {"floor_id","version","saved_ts","saved_by","plan":{...}}
GET  /api/floors/{floor_id}/versions          admin, read       {"versions":[{"version","saved_ts","saved_by","note","rooms"}]}
PUT  /api/floors/{floor_id}/plan              admin  body {"plan":{...},"note":"","base_version":2}
     200 {"ok":true,"version":3}   409 when base_version is not the current one (someone else saved)
     422 {"detail":"...","errors":[{"key":"site.err_overlap","values":{...},"message":"..."}]}
POST /api/floors/{floor_id}/restore           admin  body {"version":1}
POST /api/site/buildings                      admin  body {"name","code"}            → building with one floor
POST /api/site/buildings/{id}/floors          admin  body {"name","level"}
PUT  /api/site/buildings/{id} , PUT /api/site/floors/{id}        admin  rename
POST /api/floors/{floor_id}/image             admin  raw body image/png or image/jpeg
     200 {"image":"<sha256>.png","width":1600,"height":900}
GET  /api/site/images/{name}                  viewer; name must match ^[0-9a-f]{64}\.(png|jpg)$
```
- Every write: `require_admin`, `SameOrigin`, the `admin` bucket, an audit entry (`plan_save`, `plan_restore`,
  `site_add`, `site_rename`, `plan_image`) with floor and version. Example building: every write 409.
- Plan bodies need more than 4 KB: `BodyLimit` allows 64 KB on `PUT /api/floors/*/plan` and 2 MB on
  `POST /api/floors/*/image` (exact, normalised path patterns; every other path keeps 4 KB).
- **Upload safety.** PNG or JPEG only, decided by the bytes: PNG signature + a well-formed chunk walk (IHDR first,
  CRCs checked, IEND last); JPEG SOI + a segment walk to a SOF marker. Width and height from the header, each 64
  to 4096 px. At most 2 MB. Metadata is dropped while re-writing the file (PNG: only IHDR, PLTE, tRNS, IDAT, IEND
  kept; JPEG: APP1..APP15 and COM segments removed), which also removes anything appended after the image. The
  extension and the client's content type are ignored; the stored name is the SHA-256 of the cleaned bytes. SVG,
  GIF, WebP, a renamed HTML file, a PNG with trailing data and an oversize file are all refused (422 / 413).
  Served with the right `Content-Type`, `X-Content-Type-Options: nosniff` and `Content-Security-Policy:
  default-src 'none'`. No image library is added.

### Web

`web/src/lib/site.tsx`: `SiteProvider` (in `App.tsx`), `useSite()` → buildings, current floor, `setFloor(id)`;
`usePlan()` → the current floor's plan (query `["plan", floorId]`; the bundled `PLAN` is the first paint and the
fallback for `f1`, so a server error never blanks the plan). Current floor: `?floor=` in the address, else
`localStorage` `nadiFloor`, else `default_floor`. Components that import the static `PLAN` take the plan from
`usePlan()` instead (live-plan, floor-plan, building-status, calibration, floor page, room select lists);
the emergency takeover and the export use the selected floor when it has a reporting room, else the first floor
that has one (never an example floor while a real room reports).
Rooms belong to the floor whose plan lists them; reporting rooms on no plan belong to the default floor.

**Switcher** (`components/site-switcher.tsx`): the chip at the top of the sidebar becomes a button with a chevron
(`aria-haspopup="dialog"`); in the rail the building icon opens the same panel. The panel (Popover, 360 px):

```
+---------------------------------------------+
| [ Search building, code or floor        ]   |
| Demo Building                 DEMO          |
|   (o) Level 4          3 rooms   current    |
| Example Tower (example data)  EX-01  Example|
|   Level 1 ... Level 10                      |
|   Show 2 more                               |
+---------------------------------------------+
```
Type to filter (name, code, floor name, case-insensitive; matches in a building name keep all its floors). Arrow
keys move through the floors, Enter switches and closes, Escape closes and returns focus to the chip. Each
building lists 10 floors then "Show N more"; the panel itself scrolls at a fixed maximum height. Switching changes
the floor on Overview (the per-room signal selection resets to that floor's default), Floor plan and Rooms.
An example floor shows a grey "Example data: this building has no sensors" line on those pages.

**Editor** (`pages/plan-editor.tsx`, route `/floor/edit?floor=ID`, admin only, opened by "Edit plan" on the Floor
plan page; `components/plan-editor/*`).

```
+ Edit plan: Demo Building, Level 4 (version 2)          [Preview] [Save...] [Cancel]  +
+ Tools: (Select) (Room) (Stairs or exit) (Other space) | Background [Upload] opacity  +
+ canvas 1000 x 560, grid 10 --------------------------+ + Selected: Lab 2 ----------+
|  rectangles with 8 handles, sender/receiver dots,    | | Room ID  [room1]          |
|  background image under them                         | | Name     [Lab 2]          |
|                                                      | | Nearest exit [Stair B v]  |
|                                                      | | Door side (N/S), position |
|                                                      | | Size  [48] m2  or W x L   |
|                                                      | | Guideline only: suggested |
|                                                      | | sensor pairs: 3 (one pair |
|                                                      | | covers about 3-5 m ...)   |
|                                                      | | Sensor pair [Place] [Clear]|
|                                                      | | A/C power: 3.5 kW (Energy)|
+------------------------------------------------------+ + Checks: 2 problems -------+
+ Versions (10, Show more): v2 12 Nov 14:02 admin [Restore]                           +
```
- Start: the floor's current plan; or "Start from" a template (corridor with rooms on both sides, open hall,
  blank grid) or an uploaded image as background (opacity slider; the image is a guide, the rooms are still drawn).
- Rooms are rectangles: drag on the canvas to draw, drag to move, handles to resize, snap to 10. Arrow keys move
  the selected shape by 10 (Shift: 1), Delete removes it, every field is also editable as a number in the side
  panel (so the editor works without a mouse). Polygons: not in this round (rectangles first; log if added).
- Stairs and exits: same rectangles with a kind and a name. Sender/receiver: "Place" then two clicks inside the
  room, or drag the dots.
- Size: m2, or width x length in metres (the product is stored). Guideline: `max(1, ceil(area / 16))` pairs,
  worded "Guideline only: suggested sensor pairs: N (one pair covers about 3 to 5 m between boards, from our
  test)".
- Checks run on every change (same rules as the server, in `lib/plan-validate.ts`), listed with a click-to-select;
  Save is disabled while there are problems; the server validates again.
- Preview: the read-only live plan drawn from the draft (all rooms "No sensor" unless they report).
- Save: a note field and a summary ("2 rooms added, 1 moved"); 409 if someone saved meanwhile (offer reload).
  Restore: confirmation, then a new version.
- Unsaved changes: leaving asks first.

**Strings.** Prefix `site.` (switcher, example tag, errors) and `ed.` (editor). Main ones:

| Key | English | Malay |
|---|---|---|
| `site.switch` | Change building or floor | Tukar bangunan atau tingkat |
| `site.search` | Search building, code or floor | Cari bangunan, kod atau tingkat |
| `site.current` | current | semasa |
| `site.example` | Example | Contoh |
| `site.example_note` | Example data: this building has no sensors. | Data contoh: bangunan ini tiada sensor. |
| `site.none_found` | No building or floor matches. | Tiada bangunan atau tingkat yang sepadan. |
| `site.rooms_count` | {n} rooms | {n} bilik |
| `ed.title` | Edit plan: {building}, {floor} | Sunting pelan: {building}, {floor} |
| `ed.open` | Edit plan | Sunting pelan |
| `ed.tool_select` / `ed.tool_room` / `ed.tool_exit` / `ed.tool_other` | Select / Room / Stairs or exit / Other space | Pilih / Bilik / Tangga atau pintu keluar / Ruang lain |
| `ed.template` | Start from | Mula daripada |
| `ed.tpl_corridor` / `ed.tpl_hall` / `ed.tpl_blank` | Corridor with rooms on both sides / Open hall / Blank grid | Koridor dengan bilik di kedua-dua belah / Dewan terbuka / Grid kosong |
| `ed.upload` | Upload a floor plan image (PNG or JPG, up to 2 MB) | Muat naik imej pelan lantai (PNG atau JPG, sehingga 2 MB) |
| `ed.guideline` | Guideline only: suggested sensor pairs: {n} (one pair covers about 3 to 5 m between boards, from our test) | Panduan sahaja: cadangan pasangan sensor: {n} (satu pasangan meliputi kira-kira 3 hingga 5 m antara papan, daripada ujian kami) |
| `ed.checks` / `ed.checks_ok` | Checks / No problems found | Semakan / Tiada masalah ditemui |
| `ed.save` / `ed.preview` / `ed.restore` | Save / Preview / Restore this version | Simpan / Pratonton / Pulihkan versi ini |
| `ed.versions` | Versions | Versi |
| `ed.saved` | Saved as version {n}. | Disimpan sebagai versi {n}. |
| `ed.conflict` | Someone else saved this plan. Reload to see their version. | Orang lain telah menyimpan pelan ini. Muat semula untuk melihat versi mereka. |
| `site.err_overlap` | {a} and {b} overlap. | {a} dan {b} bertindih. |
| `site.err_no_exit` | The floor needs at least one exit or staircase. | Tingkat ini memerlukan sekurang-kurangnya satu pintu keluar atau tangga. |
| `site.err_duplicate` | Room ID {id} is used more than once. | ID bilik {id} digunakan lebih daripada sekali. |
| `site.err_taken` | Room ID {id} is already used on {floor}. | ID bilik {id} sudah digunakan di {floor}. |
| `site.err_live` | {name} ({id}) has a sensor reporting, so it cannot be removed. | {name} ({id}) mempunyai sensor yang sedang melapor, jadi ia tidak boleh dibuang. |
| `site.err_image` | The file is not a PNG or JPG image this page can use. | Fail ini bukan imej PNG atau JPG yang boleh digunakan. |
| `site.err_image_size` | The image must be at most 2 MB and between 64 and 4096 pixels on each side. | Imej mesti tidak melebihi 2 MB dan antara 64 hingga 4096 piksel pada setiap sisi. |

**Acceptance**
- Today's plan and room IDs work with an empty `data/site` (first run after the update needs no step).
- The chip opens the panel; typing "ex" or "level 7" filters; Enter switches; Overview, Floor plan and Rooms show
  that floor; refresh keeps it; the rail opens the same panel.
- The example building is marked "Example" in the switcher and on its pages; its rooms read "No sensor".
- An admin draws a room, names it, sets its ID and exit, places the pair, sees the guideline, saves; the Overview
  shows it; a second version restores the first. The audit log has both entries.
- Overlapping rooms, a floor with no exit, a duplicate ID, removing a reporting room: refused in the editor and by
  the API; the live plan is unchanged.
- A `.png` that is HTML, an SVG, a 3 MB file, a 5000 px image: refused. An accepted JPEG is stored without EXIF.
- A viewer cannot reach the editor or any write endpoint; cross-site writes 403.
- During an emergency the takeover shows a floor with reporting rooms, never the example building.

**Tests.** pytest `tests/test_site.py` (store, built-ins, validation rules one by one, versions, restore, 409,
known rooms follow a save, chat exit names follow a save, example read-only), `tests/test_site_api.py` (auth on
every write, body limits, rate bucket, audit), `tests/test_upload.py` (fake types, truncated, trailing data,
oversize bytes and pixels, metadata removed, served headers). vitest: switcher search and keys, floor state
(URL/storage), `plan-validate` parity cases, editor basics (add room by keyboard, field edit, checks list,
guideline). e2e: switch floor and back; draw, save, restore.

**Cut lines** (each leaves a working console)
1. After step 2: switcher + read-only floors + example building, no editing. Flag `PLAN_EDITOR=off`.
2. After step 3: write API present, no editor UI (flag off).
3. Editor without image upload (templates only): remove the upload button, keep the endpoint refused.

---

## PART 17. README and docs

**Decision.** One README a judge can read in three minutes, every claim backed by a file in the repo.

Structure
1. Logo banner (`<picture>` with the light and dark SVG from `web/src/assets`, relative paths).
2. One-line pitch and three sentences on what NADI does.
3. Screenshot gallery (table of images from `docs/screenshots/redesign/`, light and dark).
4. How it works: a small mermaid flowchart (boards → Wi-Fi signal → receiver → MQTT → server → console).
5. Features (emergency, everyday, console), short bullets.
6. Real test results: the numbers from `docs/REAL_TEST_RESULTS.md`, exactly as recorded, with what was *not* tested.
7. Huawei stack: a table "in use now" vs "ready, not run" (honest: local mode is the baseline).
8. Hardware list and cost (from the project brief and firmware README; only prices that are recorded).
9. Quick start, tests, security summary (links to `docs/`).
10. Roadmap, team (Aiman, Mukhlis, Praveen; UTM; supervisor Dr Asri), licence.

No claim beyond the repo's evidence, no secrets, relative image paths only. `docs/screenshots/overview.png` is
replaced by the new Overview. `docs/DEMO_RUNBOOK.md` and the board-day checklist (`docs/BOARD_DAY.md`,
`docs/FLASH_TOMORROW.md` where they name screens) are updated: page names (Calibration), where Ask NADI is,
selecting a room for its live signal, the room's Signal panel, Energy settings (incl. setting the waste delay back
after a demo), the building switcher, and the demo order: Overview → walk in/out → select Demo Room and its signal
→ Calibration → Ask NADI.

**Acceptance.** Every relative link and image resolves (script check); numbers match `REAL_TEST_RESULTS.md`;
`tests/test_strings.py` and the trace words are clean; mermaid renders on GitHub.

---

## PART 18. User-view review

Walk the running console with fixtures as four people: a first-time facility manager, a fire warden during a
drill, a competition judge with five minutes, an admin setting up a new floor. For each: what is confusing, slow,
ugly, inconsistent or missing, with the page and a screenshot reference. Prioritise: must fix before the final /
nice to have / later. Fix only small, safe must-fix items (no new features), re-test, and write everything in
`docs/design/USER_REVIEW.md` (findings table, what was fixed, what is left).

---

## PART 19. Finish

1. Screenshots into `docs/screenshots/redesign/` (script: `scripts/redesign_screenshots.py`, fixtures only):
   Overview with a selected room (light, dark) and with a no-sensor room; Calibration with both dot kinds and the
   full-width detector; a short list at 10 and expanded; a long feed with "View all" and its page; Energy settings
   (viewer, admin edit); the switcher with search; the editor (if shipped); Ask NADI with the new footer.
2. pytest, vitest, e2e, accessibility measurements (text size, names, focus, one h1), rebuild `web/dist`, push,
   CI green.
3. Code review of the branch diff against `main`: bugs, auth and CSRF on every new PUT/POST, upload safety, input
   validation, XSS in SVG/HTML text, polling load with many rooms, timer and animation leaks, error states, i18n
   gaps, dark-mode contrast, focus handling. Fix, re-test.
4. Trace check on every tracked file and every branch commit (case-insensitive word list from the brief), embedded
   metadata in every image, SVG and JSON added on the branch, and authorship of every commit.
5. Report table. Stop. Do not merge.

---

## Build order

- [x] **11** Plan (this file) and direction update
- [x] **12** Final checks from review
- [x] **13** Overview: status highlight, Today's summary, per-room live signal
- [x] **14** Calibration layout and the list rule everywhere
- [x] **15** Admin energy settings → **tag `stage-safe` here** (everything the stage demo needs)
- [x] **16.1** Site store, built-ins, read API, validation (server)
- [x] **16.2** `usePlan` / `useSite`, switcher, pages follow the floor
- [x] **16.3** Write API, versions, restore, upload
- [x] **16.4** Editor
- [x] **16.5** e2e for switch, edit, restore
- [x] **17** README and docs
- [x] **18** User-view review
- [x] **19** Finish
- [x] **20** Review fixes (A/C pill wording, "–" for no-sensor rooms, editor keeps live names, even ticks, arrow, Malay kWj)
- [x] **21** Energy settings as one full-width card
- [x] **22** Site switcher as a wide two-column panel
- [x] **23** One-line page descriptions
- [x] **24** Ask NADI scope (cut first if time runs short)
- [x] **25** Time range on the Overview live signal card (cut second)
- [x] **27** Energy ranges (Today / 7 days / 30 days)
- [x] **28** Final visual and copy audit
- [x] **26** README screenshots and gallery (last, after 28)

## Decision log

Date, what changed against this plan, why. Written before the code that does it.

- 2026-11-12, part 13, wording. Drill hints start in lower case ("no drill today", "last drill: 3 Nov") like the
  other hints in the same table. `ov.today_emergencies` is "emergencies today: {n}" so 1 and 2 both read right.
  `plan.selected` is not added: the tile says it with `aria-pressed`, a second word would be read twice.
  Added `sum.col_room`, `sum.no_rooms`, `sum.open_report` (the table needs them). Removed with the emergency
  group: `bs.emergency`, `bs.ac`, `bs.normal`, `ov.waste_today`, `ov.today_waste_hint`.
- 2026-11-12, part 13, counter rooms. The people-counter state of the Live signal card shows its one sentence with
  no second line (the sentence already says why there is no chart).
- 2026-11-12, part 14, Calibration. The heading "Live detector: Calibrated rule (threshold 1.30 dB)" is gone with
  its card: the table says the same per room, so `cal.detector_rule` and `cal.detector_model` are removed. Added
  `cal.dots_none_room` for a room that has no labelled reports while another room has.
- 2026-11-12, part 14, list rule. `useWholeRows(box, list, watch)` takes the limited box and the list separately
  (the card body is the limited element, the rows are children of the list inside it), and `wholeRows()` turns its
  answer into a row count. The Summary page's by-room table is the page's main table: it stays the full list (the
  rule table named it in both rows). Live activity keeps its "All alerts" link in the title row while nothing is
  hidden, and swaps it for "View all N" at the foot when rows are hidden, so there is one link to Alerts at a time;
  when the feed is at the server's cap of 20 the foot link reads "All alerts" (the true total is not known there).
- 2026-11-12, Part 14: the column check runs in the browser tests, not in the screenshot script. Plan said a
  `--measure` option on `scripts/redesign_screenshots.py`; `tests_e2e/test_console.py::test_calibration_page`
  measures the same thing (the two Calibration columns end within 1 px at 1366x768 and 1920x1080, the live detector
  lies below them at the same width), and it runs with every e2e run where a script option would be run by hand.
  The thirteen labels of that test are twelve rows written into the test server's labels file plus one tap:
  thirteen taps hit the limit of 30 admin requests a minute when the whole file runs.
- 2026-11-12, Part 15: the demo scenario's 60 s delay is `energy.delay_override_s`, set by `demo.start()`, instead
  of overwriting `logic.WASTE_AFTER_S`: the configured default and any saved value stay untouched, and the
  Energy settings card shows the real saved delay while the story runs.
- 2026-11-12, Part 15: `GET /api/info` also gives `ac_on_below_c` (the live temperature rule), so the Rooms page's
  "On (below N °C)" needs no extra request. `waste` on each room carries `kwh` as planned.
- 2026-11-12, Part 15: a save whose audit line cannot be written (Valkey offline) is still kept: the stored version
  records who and when itself, and refusing after the row is in MySQL would leave the two disagreeing.
- 2026-11-12, Part 15: "Delete all data" also deletes the saved settings (they name who changed them) and the new
  `waste_kwh:*` / `waste_co2:*` totals; the demo reset keeps the settings (they are configuration, not data).
- 2026-11-12, Part 15: extra strings beyond the plan's table: `es.hint`, `es.val_*` (value with unit), `es.rooms_own`,
  `es.rooms_none`, `es.add_room_pick`, `es.room_kw_label`, `es.not_set`, `es.history_none`, `es.col_*`,
  `es.err_too_many`, `es.err_save`. `rooms.ac_on` and `energy.method_rule` take the temperature (and the delay) as
  values; `energy.method_*` no longer name the `.env` keys, since a saved value replaces them.
- 2026-11-12, Part 15: `logic.waste_info` and `logic.ended_waste_rm` stay for their unit tests but the server uses
  `energy.waste` / `energy.ended` (piecewise over the versions). Days stored before this part (RM only) get their kWh
  and CO2 from the values in force at the end of that day; today's RM-only total is given its kWh and CO2 once, before
  the first new stretch is added, so the three units stay in step.
- 2026-11-12, Part 16.1: `server/plan.py` keeps `PLAN` as one merged dict refreshed in place (`refresh()`), so every
  `from server.plan import PLAN` sees saved plans without a restart. Exit keys that repeat on another floor are
  kept as `<floor>:<key>`. A site folder that cannot be read falls back to the built-in plan instead of stopping the
  server. `main.PLAN_ROOMS` became `plan_rooms()`. The demo story plays on the default floor's rooms only.
- 2026-11-12, Part 16.2: `GET /api/info` also gives `room_floors` and `room_exits` (page language), so the console
  knows each room's floor and nearest exit on every floor without fetching every plan. The site context carries
  them, so the plan drawings need no data client of their own.
- 2026-11-12, Part 16.2: the switcher panel is a small panel of our own, rendered over the page (a portal, so the
  sidebar's scroll box cannot clip it), not a Popover dependency. It follows the combobox pattern: focus stays in
  the search box, the arrow keys move the highlighted option (`aria-activedescendant`), Enter picks it, and the
  "Show N more" line of a building is an option too. Moving DOM focus to each floor lost the first key press on
  the real server in the browser test.
- 2026-11-12, Part 16.2: the Overview's building status counts the rooms of the floor on screen (an example floor
  says "No live data", never "All clear"); the waste figure, needs attention and live activity stay building-wide.
  Rooms and Floor plan list the floor on screen. Calibration lists the rooms of every floor; its live detector
  table uses the floor on screen. The Summary page stays building-wide.
- 2026-11-12, Part 16.3: a plan may carry only drawing fields (a whitelist per object: plan, rectangle, room, exit,
  other space, door, sensor pair, background); anything else is refused, so nothing but drawing data is stored and
  served to viewers. Level, version and base version in request bodies are strict integers ("2" as text is refused).
- 2026-11-12, Part 16.3: a restore is stored with `restored_from` and an empty note; the editor words it. A new
  building gets one empty floor named "Level 1" (names are free text, shown as written in both languages). Audit
  lines of site writes are written quietly: Valkey offline never turns a stored change into an error.
- 2026-11-12, Part 16.4: editor files are `pages/plan-editor.tsx`, `components/plan-editor/canvas.tsx` and
  `inspector.tsx`, and `lib/plan-validate.ts`. The server's and the editor's checks are held to one shared list of
  cases (`tests/fixtures/plan_cases.json`, read by pytest and vitest). The side panel lists every shape as a button
  and has "Add a room / stairs or an exit / another space" buttons that place a shape on the first free spot, so
  the editor works without a mouse. Leaving with unsaved changes asks first for links inside the console and for
  closing or reloading the tab (the app uses BrowserRouter, which has no navigation blocker). The upload has a
  labelled button of our own: the browser's file button cannot be translated. Rectangles only.
- 2026-11-13, Part 16.5: the check that the emergency view never draws the example building is part of the existing
  drill browser test (it now starts the drill from an example floor). A test of its own pressed the alarm twice more,
  and the suite then made seven presses a minute against the limit of six, counted per address in the shared
  Valkey. The editor's side panel scrolls inside itself on wide screens, so a button in it never scrolls the
  drawing away (found by the browser test: the sensor pair clicks landed off screen). Part 16 passed its checks, so
  `PLAN_EDITOR` stays on by default; no cut line was needed.
- 2026-11-13, Part 17: the README's long reference sections (two modes table, layout, Huawei tools on the laptop,
  model training, labelling) were dropped in favour of the docs that already hold them; the IoTDA product steps that
  only the README had moved into `docs/DEPLOYMENT.md`. Hardware prices are the rough planned Shopee prices from
  `docs/NADI_Equipment_Checklist.pdf`, quoted as estimates (no receipts are in the repo). Links were checked with a
  script (23 Markdown files); the mermaid diagram is plain flowchart syntax and is checked on GitHub after the push.
- 2026-11-13, Part 19: code review fixes. The example building's names, its floors and rooms, a new building's first
  floor and the editor's template names came from code; they are strings now (`site.example_name`, `site.level_n`,
  `site.example_room`, `ed.tpl_hall_name`, `ed.tpl_exit_name`) and `/api/site` and `/api/floors/{id}/plan` take
  `lang`. A damaged `site.json` or plan version falls back (built-in floor, newest readable version) instead of a
  500. The editor shows the error when a floor's plan cannot be fetched instead of loading for ever. Labels from an
  earlier day show their date. The e2e server sets `READ_PER_MIN=5000`: every page of every test comes from one
  address within minutes and ran out the shared read limit late in the suite (one open Overview makes about 34 reads
  a minute, measured, so the real default of 240 stays). Fixture states W to Z and Q2 (lists at 10 and expanded,
  a long feed and its page, Energy settings as a viewer).
- 2026-11-13, Part 20: the signal scale steps in even whole numbers (0, 2, 4, ...; larger even steps for large
  values) everywhere it is used (live signal, calibration dots, the tile trace), so the axis never shows 1 and 3 next
  to a threshold label. `GET /api/floors/{id}/plan` returns each room with the name the live view shows
  (`ROOM_NAMES` over the name on the plan), so the editor opens with those names and a save without changes keeps
  every room's name; the example building is left as it is.
- 2026-11-13, Part 20 item 7 (added by Aiman): the Overview's plan tiles no longer draw the sender/receiver line, its
  two dots or the "Sender"/"Receiver" labels, and the legend drops "Signal line, brighter with movement". A tile
  shows the room name, the count, the status and the small trace. The sensor pair stays in the room panel's Signal
  section and in the floor plan editor. The animated beam component and its state helper had no other user and are
  removed; a new report still rolls the count and rings the tile once.
- 2026-11-13, Part 20 item 8 (added by Aiman): the live signal chart (Overview card and the room panel, one
  component) loses the text on the threshold line and the sentence under the chart. The threshold is its own
  y-axis tick ("1.3", the live value) in the dashed line's colour, beside the even ticks (an even tick closer than a
  quarter step to it is left out so the two never overlap). Hovering or focusing the line shows "Threshold 1.30 dB";
  the line is a keyboard stop with a visible focus mark. The axis title is "dB" above the axis. The chart is a
  figure with an aria-label holding the room, the latest value and the threshold (or that a trained model is
  counting, or since when there is no data). Only the history-database warning stays under the chart.
- 2026-11-13, Part 20 item 9 (added by Aiman): the live signal card header is one row: "Live signal", the room
  select and "Now 2.31 dB" as plain text on the left; "Open room signal" on the right. The "Above/Below the
  threshold" pill and the "last 5 minutes" text go; the chart's aria-label says whether the value is above or below
  the threshold. The room panel's chart uses the same header. The range toggle of Part 25 takes its place on the
  right of this row when Part 25 is built (with the compact select at 1366 px and narrower, and "Now" showing the
  count on the people ranges); item 9 lays out the row without it so Part 20 can be finished first.
- 2026-11-13, Part 21: Energy settings is one full-width card and the "How these figures are worked out" card goes.
  Five equal tiles like the KPI row (label, value, unit beside it): 5 across from 1536 px, 3 + 2 below (1366 with the
  sidebar open). Edit turns the tiles into inputs in place; Save and Cancel sit in the card header beside "History"
  (a side panel with the change history, 10-row rule) and "Last changed by X on Y". "Per room (N)" under the A/C
  power tile opens the per-room row inside the card. One line at the foot states the rule with the live values.
  The confirmation dialog that lists old → new stays.
- 2026-11-13, Part 22: the switcher panel opens to the right of the sidebar, anchored to the chip (and to the rail's
  icon), about 640 px wide, over the page. The search box spans the top. With no search: a buildings column (the
  example building tagged Example) and a floors column for the highlighted building, with room counts and the
  current floor marked; 10 floors, then "Show N more". With a search: one list of "Building > Floor" rows. Keys: the
  focus stays in the search box (combobox); Up and Down move in the column, Right or Enter on a building moves to
  its floors, Left goes back, Enter on a floor switches, Escape closes and returns to the chip; typing filters.
- 2026-11-13, Part 22: the panel is placed when the chip is pressed, before it opens. Its first render used to be
  hidden until a layout effect placed it, and a hidden search box cannot take the focus, so the first key went to
  the chip. That was also the real cause of the "first key lost" seen in Part 16.2 (logged then as a focus race).
- 2026-11-13, Part 23: every page description is at most 75 characters in both languages
  (`tests/test_strings.py::test_page_descriptions_fit_on_one_line`), which keeps it on one line at 1366 px with the
  sidebar open (checked in the browser). Details the old sentences carried ("Select a row for details", who started
  emergency mode) are said where they apply: the rows themselves are buttons and the audit log has its own title.
- 2026-11-13, Part 24: chat scope lives in `server/scope.py` and wraps the existing rules without changing them.
  The question's scope is worked out first (emergency or drill: whole building, locked; a floor named in the
  question: that floor of the chip's building; else the chip's floor, or the whole building). The rules then run on
  that scope's rooms only, a model may only reword that checked body and is checked against the same scoped rooms,
  and the scope prefix ("Level 4: ", "Whole building: ") and, in an emergency or drill, the per-floor breakdown are
  added after the check, so a model can never drop or change them. A floor without sensors answers "No sensors on
  this floor." and an example floor says it is example data; neither ever says 0 people. `POST /api/chat` takes
  `floor` (the chip; empty means the whole building) and answers with `scope`. `CHAT_SCOPE=off` turns it all off
  (the chat answers for the whole building with no prefix, as before).
- 2026-11-13, Part 25: `GET /api/history` (and the climate history) reach 30 days; beyond 7 days a point is one
  Malaysian calendar day (buckets aligned to midnight Malaysia time, not UTC). With `room=` the answer also lists
  `waste`: the buckets in which the room was empty throughout and its lowest temperature was below the "counts as
  on" temperature in force then; the chart shades those amber. This is the history's own resolution (a bucket, not
  the exact waste stretch, which is not stored). Buckets with no report are left out by the server and drawn as gaps.
  The live signal card's range is a toggle from 1536 px wide and a compact select below that, beside "Open room
  signal"; the buttons also give way to the select when they do not fit the card's header (the card is only ~740 px
  wide at 1920). On the people ranges the card is titled "People" ("Penghuni"; the room select beside it already
  names the room, and "People in <room>" pushed the link off the card) and "Now" shows the count. The Malay link is
  "Isyarat bilik" (was "Buka isyarat bilik", cut at 1366); the room select carries the room name as a tooltip when
  it has to shrink. The global range
  (room panel) gains 30 days. The people chart refreshes no faster than its bucket (at least every minute).
- 2026-11-13, Part 27: the Energy page has its own period, Today / 7 days / 30 days (default 7 days), in `?range=` and
  localStorage `nadiEnergyRange`, separate from the room panel's time range. Three figures (wasted RM with the change
  against the period of the same length before, energy kWh, CO2 estimate), each label naming the period; "No earlier
  data to compare" when nothing was reported in the period before. Waste by room is one bar per room for the period,
  highest first (10-row rule); waste over time is per hour today (24 bars, hours still to come empty) and per day on
  7 and 30 days. `GET /api/energy?range=` adds a `range` block and keeps every older field (Rooms and the summary
  read them). Day totals are now kept for the history retention (at least 61 days, was 15), so the 30 days can be set
  against the 30 before; existing installs only have the last 15 days stored, earlier days show 0. Days before the
  first report (MySQL MIN(ts), read once a minute) are empty; none are left out while MySQL is offline. Today's hours
  come from new Valkey keys `waste_rm_h:<day>:<hour>` (2 days): an ended stretch is cut at each whole hour and each
  part costed at the values in force then. A stretch still counts in full on the day it ended (as before), so on a
  day after a stretch that crossed midnight the hour bars add up to slightly less than the day's total. Money axes
  use even steps (0, 0.5, 1, 1.5).
- 2026-11-13, Part 28: final audit in `docs/design/POLISH_AUDIT.md` (before/after shots in `docs/design/audit/`). New
  shared rules: chart labels 8 px from the axis, time ticks on whole local steps, money ticks on even steps, legend text
  in the text colour, unit titles clear of the top tick, drawn plan text never under 14 px on screen (the plan measures
  its drawn size; `web/src/lib/svg-scale.ts`), table first and last columns at the card padding, the first chart series
  in the theme's signal teal. Amounts are written "RM 0.50" and temperatures "23.6 °C" everywhere (alerts and chat
  answers included).
- 2026-11-13, Part 26: screenshots renamed for what they show (`overview-all-clear.png`, `energy.png`, ...) and all
  retaken from sample data at 1920 x 1080 (one at 1366 x 768, one at phone width); the sample building is "Demo building
  (sample data)". Old lettered screenshots, the beam GIF and the old console's screenshots are deleted (20 MB to
  4 MB); the user guide points at the new ones. The script writes PNGs with image chunks only and answers history
  requests with 503 for the database-offline shot, as the server does. README: Overview hero, a light and dark pair
  of the room panel, eight captioned screenshots, links to the rest. Amounts and temperatures use a non-breaking
  space ("RM 0.50", "24.1 °C") so they never break across lines.
- 2026-11-13, final review (docs/design/FINAL_REVIEW.md holds the list and its ticks; the decisions are here):
  - U1: the Overview legend and its hint share one row, the hint on the right: "Click a room for its chart,
    double-click for details".
  - U2: a room's status is one short label everywhere it is a label (plan tile, legend, the Rooms table, the status
    pill): "Empty, A/C on" / "Kosong, A/C hidup". Sentences (alerts, descriptions, chat answers) keep "air
    conditioning" / "penghawa dingin". One fact had three wordings before ("Empty, air conditioning on", "A/C on,
    empty", "Bilik kosong, penghawa dingin masih hidup").
  - U3: the Overview's chart card is People; the live signal lives in the room panel only. Ranges 1 h, 24 h, 7 d,
    30 d; the default is 1 h (per minute), because a new install and a live demonstration have minutes of data, not
    days, and a walk in or out shows within a minute. A stored "5m" falls back to the default. The points come from
    `GET /api/history?room=ID&view=people` (read only): buckets of 1 min, 30 min, 3 h and a Malaysian day, each with
    the peak count and the minutes with someone inside (distinct minutes with a report above 0, so the report
    interval does not matter), and `since`: when the room last changed between empty and occupied (looked for in the
    last 30 days). "since" is shown only while the live state agrees with the state the history saw, so it can never
    sit beside the wrong count. The line is monotone with a light fill; a lone point between two gaps is drawn as a
    dot (a line needs two points, and it would otherwise vanish). No waste shading here: waste is the Energy page's.
  - U4: a room may carry `capacity` (whole number, 1 to 1000) on the plan, set in the editor's room details. It is
    drawn as a dashed line on the people chart with "Capacity N" on hover or focus, and the tooltip reads "peak 1 of
    30". The scale always reaches the capacity when one is set: a line that hides when counts are low would look
    like a setting that did not save. Saved with the plan, so it is versioned and restorable; the audit line of a
    plan save lists capacity changes. No alert is raised from it. The detection threshold stays a calibration result
    and has no field anywhere.
  - U5: room panel order: name, status, count with "since", nearest exit; People (the Overview's card, same ranges);
    Signal (picture, then the live signal: last 5 minutes, no range control); Temperature and humidity (follows the
    People range, current values in its heading); facts; sensor health. Gone: the legend that repeated the room's
    name, "Illustration driven by the live reading" (the caption beside it already gives the live reading), the
    three-figure strip (its figures moved into the header and the climate heading).
  - U6: editor toolbar in three labelled groups on one baseline: Draw, Start from, Background image; the file note
    ("PNG or JPG, up to 2 MB") is helper text under the button.
  - U7: no route line in the emergency view, the export or the saved snapshot. "Nearest exit: Stair B" is written
    on the room and in the priority list (it was "via Stair B").
  - U8: Energy: one chart of the building's waste over the period, then the rooms as a ranked list (room, RM, kWh,
    hours, a thin bar). A row is a button: it filters the chart to that room and a chip with a remove button says
    so; the choice is kept in `?room=`. Hours are the room's kWh divided by its air conditioner power in force that
    day. For the filter to work on Today, an ended stretch's hour parts are now also stored per room
    (`waste_rm_h:<day>:<hour>:<room>`, 2 days); stretches that ended before this change have building hours only.
  - U9: a chart whose range is longer than its data starts at the first bucket or day with data and says "Data from
    20 Oct" (people chart, Energy per day). Today's 24 hours stay a whole day.
  - U10: one chart rule set in `web/src/components/charts.tsx`: tick labels 8 px from the plot, even ticks on both
    axes (the humidity axis takes the temperature axis's number of ticks, so both sit on the grid lines), one legend
    component (a swatch, then the label in the normal text colour), no legend for a single series, and time labels
    thinned so they never touch.
  - Found while building U1 to U10 and the review's own items:
    - The "Data from 20 Oct" note of the People card sits on a line of its own under the header, right-aligned. In
      the header it pushed the one row past the card at 1366 px and, with the range buttons, at 1920 px.
    - The save dialog of the plan editor lists each capacity change ("Capacity of Lab 9: not set → 12"), the same
      line the audit log keeps.
    - The bar in the Energy room list is decoration: it repeats the "Wasted" figure as a length, has no column
      heading and is not read out.
    - A room drawn on the plan that has never reported is listed last in the Energy room list with "No sensor" and
      dashes, and is not a button. "RM 0.00" there read as "measured, nothing wasted".
    - A room counted by a people counter gets the same People chart; only its Signal section is replaced by the
      sentence that says so.
    - The saved incident snapshot is a table without a drawing, so U7 had nothing to remove there.
    - B10: on a short window the legend stays and the hint goes. The two do not fit one row beside the narrow plan,
      and the hint is the less needed of the two (the tiles are buttons with their own names).
    - The plan editor's side panel is as tall as the drawing beside it and scrolls inside itself. It used to stop
      at a fixed height, which cut the "Nearest exit" field in half once the capacity field was added.
    - The count badges on the bell and the sidebar and the "Start" button of the emergency dialog use one fixed
      dark red with white text in both themes. With the theme's red they measured 3.0:1 in dark mode.
    - Sample data (`scripts/redesign_screenshots.py`): the Demo Room has a capacity of 2, the sensor list shows a
      CSI receiver and a climate board, "Sensor back online" is information, and only the room with a sensor ever
      shows waste. The two rooms without a sensor used to carry made-up waste figures.

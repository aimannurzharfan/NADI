# Final review before v1.0

Every page of the console was opened with the sample data (`scripts/redesign_screenshots.py`, the building is named
"Demo building (sample data)"), in English and Bahasa Melayu, light and dark, at 1920 x 1080 and 1366 x 768, and read
four times: as a facility manager looking for waste, as a fire warden in a drill, as a first-time visitor trying the
project, and as the admin who sets it up. The checks used: the house rules in `docs/design/DIRECTION.md`, a web
interface checklist (names for every control, focus, one h1, no text under 14 px, no sideways scroll), and a copy
pass (one fact has one wording, labels name things, nothing is said twice).

Tick an item when it is built, tested and pushed. Work resumes from the first unticked item.
The decisions and their reasons are in the Decision log of `docs/design/PLAN.md`.

## A. Fixes asked for (U1 to U10)

| # | Decision | Why |
|---|---|---|
| U1 | Do as asked | The hint was a second row under the legend; one row gives the plan the height back. |
| U2 | Do, and wider: one short status label everywhere it is a label | The tile wrapped in Malay at 1366, and the same fact had three wordings (tile, Rooms table, legend). Sentences keep the full words. |
| U3 | Do, with three additions | Default range 1 h (a new install has minutes of data); "since" is hidden while the live count and the history disagree; a lone point between gaps is drawn as a dot. |
| U4 | Do; the scale always reaches the capacity | A line that disappears when counts are low reads as a setting that did not save. Versioned with the plan, audit-logged, never an alert. |
| U5 | Do as asked | The panel opened on a signal chart; a visitor wants the count first. The strip of three figures goes into the header and the climate heading. |
| U6 | Do as asked | The draw tools had no label and the upload label ran the file limits into the title. |
| U7 | Do, also in the export and the saved snapshot | The line was an L-shaped guess along the corridor, not a surveyed route; the exit's name is the fact. |
| U8 | Do; per-room hours are stored from now on | Two charts said the same thing two ways. The ranked list reads faster and the filter answers "when does this room waste". |
| U9 | Do for day ranges; Today keeps 24 hours | Six empty days before the first report looked like six days without waste. |
| U10 | Do as one shared rule set | Fixing charts one by one is how they drifted apart. |

- [x] U1 Overview legend and hint on one row
- [x] U2 One-line status labels in both languages
- [x] U3 People card on the Overview
- [x] U4 Room capacity
- [x] U5 Room panel order
- [x] U6 Editor toolbar groups
- [x] U7 No route line in emergency mode
- [x] U8 Energy: one chart and a ranked room list
- [x] U9 Charts start at the first data
- [x] U10 Chart rules

## B. Findings of this review

Before-screenshots are in `docs/design/final-review/before/`.

| # | Page | Problem | Fix | Before | Priority |
|---|---|---|---|---|---|
| B1 | Floor plan | An occupied room is told by its green fill alone; the tile shows the count and the temperature but no status word | The status word under the count, as on the Overview's tiles | `floor-plan.png` | must |
| B2 | Rooms, Overview | "A/C on, empty" in the table, "Empty, air conditioning on" on the tile and in the legend | One label (with U2) | `rooms.png`, `overview.png` | must |
| B3 | Sensors (sample data) | The sample receiver is listed as "Climate node", with no room and no packet count | Correct the sample data: a CSI receiver in the Demo Room with its packets, and the climate board as a second row | `sensors.png` | must |
| B4 | Alerts, Overview (sample data) | "Sensor back online" is shown as a Warning; the server sends it as information | Correct the sample data | `alerts.png` | must |
| B5 | Room panel | The humidity axis reads 0, 25, 50, 100 and its ticks miss the grid lines | With U10 | `room-panel.png` | must |
| B6 | Today's summary | A step line with vertical spikes and a one-entry legend that repeats the table below | The people line of U3 (smooth, no legend for one room) | `summary.png` | should |
| B7 | Floor plan editor | The list of shapes ends in half a row ("Toilets" is cut through) | The list's box holds whole rows | `plan-editor.png` | should |
| B8 | Rooms | Rooms drawn on the plan without a sensor are missing, so the page says "1 of 1 rooms" under a plan of three | List them with "No sensor" and dashes, after the sensing rooms | `rooms.png` | should |
| B9 | Emergency view | The priority list says "via Stair B, live, 8 s ago": three facts in one grey line | "Nearest exit: Stair B" on its own, then the count's age (with U7) | `emergency.png` | should |
| B10 | Overview at 1366 x 768 | The legend is hidden on a short window | Show the one-row legend of U1 when it fits; measure after U1 | `overview-malay-1366.png` | should |
| B11 | Calibration | The labelled-reports chart writes "threshold 1.30 dB" on its line while the signal chart shows the threshold as an axis tick | Leave: on this page the threshold is the subject and the label is the point of the chart | | skip |
| B12 | Emergency view | Ask NADI cannot be opened from the takeover | Leave: the takeover is deliberately one list and one plan; the chat stays one click away after the alarm ends | | skip |
| B13 | Site | No screen to add or rename a building or a floor (API only) | Leave: a new feature, not polish | | skip |
| B14 | Alerts | The bell and the sidebar both carry the count | Leave: the rail hides the sidebar's badge, the bell is always there | | skip |

- [x] B1 Status word on Floor plan tiles
- [x] B2 One status label (with U2)
- [x] B3 Sample sensors corrected
- [x] B4 Sample alert severity corrected
- [x] B5 Humidity axis (with U10)
- [x] B6 Today's summary line
- [x] B7 Editor shapes list in whole rows
- [x] B8 Rooms lists no-sensor rooms
- [x] B9 Priority list wording (with U7)
- [x] B10 Legend at 1366 x 768

## Final pass

- [x] Every page read again after the build, small leftovers fixed
  (found and fixed: the People card's header ran past the card on 30 days; the count badges failed contrast in dark
  mode; the editor's side panel cut a field in half; rooms without a sensor showed "RM 0.00" in the Energy list)
- Left as it is: at 1366 px in Bahasa Melayu the label "Tangga A" touches the wall of the narrow stair on the
  Overview's plan. The text cannot go under 14 px and the stair is drawn to scale.
- [x] pytest (830), vitest (266), browser tests (21), and a browser measurement of 19 views in both languages, both
  themes and both sizes (152 page loads): no text under 14 px, no contrast under AA, every control named, one h1,
  no sideways scroll, status labels and the People card's header on one line
- [x] `web/dist` rebuilt, pushed, CI green

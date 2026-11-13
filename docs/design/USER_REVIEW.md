# User-view review, 13 November 2026

The console was walked with the screenshot fixture (`scripts/redesign_screenshots.py`, every screen labelled TEST
FIXTURE) at 1920x1080 and 1366x768, light and dark, English and Malay, as four people. Screenshot references are the
files in `docs/screenshots/redesign/` (letters A to V); pages the script does not cover (Rooms, Alerts, Summary,
Sensors, Floor plan at 1366) were captured the same way for this review only and are not committed.

Who walked it:

- **Facility manager, first time:** Overview, Energy, Rooms, Summary.
- **Fire warden during a drill:** start the drill, the full-screen view, marks, export, end.
- **Competition judge with five minutes:** README, Overview, a room's signal, Calibration, Ask NADI.
- **Admin setting up a new floor:** switcher, Floor plan, the editor, versions, Energy settings.

## Findings

| # | Who | Page | What | Priority | Done |
|---|---|---|---|---|---|
| 1 | Admin | Alerts, audit log | The card was titled "Emergency mode audit log" and said it records emergency mode, drills, marks and deletions, but it also lists energy settings and floor plan changes. | Must fix | Fixed: "Audit log", and the description names energy settings and floor plans (EN and BM). |
| 2 | Facility manager | Energy, KPI strip (Q) | With no change from yesterday the line read "−+RM 0.00 vs yesterday" (a no-change mark followed by a plus). | Must fix | Fixed: "Same as yesterday" / "Same as the week before"; vitest checks it. |
| 3 | Facility manager | Energy, waste per day (Q) | The daily chart cut the "R" off "RM" on its axis ("M 1.2"). | Must fix | Fixed: the axis is wider; screenshot retaken. |
| 4 | Judge | Summary, people today | The 24-hour people chart drew smooth curves between counts, so it passed through half a person. | Must fix | Fixed: people charts always step from one whole count to the next. |
| 5 | Judge | Energy (Q), Summary | The fixture reported RM 1.10 wasted today while "Waste by room" said there was no waste: the fixture answered the totals but not the rooms or days. Fixture only (the server's answers agree), but the image is in the README. | Must fix | Fixed in the fixture; Q and R retaken. |
| 6 | Admin | Switcher, editor | There is no screen to add a building or a floor, or to rename one: the API has it (`POST /api/site/buildings`, `.../floors`, `PUT` to rename) but the console does not. A new floor today means an API call, then the editor. | Before the final | Not done (a new feature, out of scope for this review). |
| 7 | Facility manager | Rooms | Rooms lists only rooms that have reported; the floor's rooms with no sensor (Hall A, Room 3 in the fixture) are not in the table, although the plan draws them. | Nice to have | Not done. |
| 8 | Admin | Editor | "Add a room" on a full floor (the built-in plan has no free space) places the room at the top left corner on top of the stairs; the checks list says so, but a hint "no free space, draw it or move another first" would be kinder. | Nice to have | Not done. |
| 9 | Admin | Editor at 1366x768 (U) | The canvas starts below the toolbar and ends below the fold; the side panel scrolls inside itself, the page scrolls about 200 px. Usable, not ideal on a small laptop. | Nice to have | Not done. |
| 10 | Facility manager | Floor plan page | The plan's room tiles show the count and the temperature but no status word ("Occupied"), unlike the Overview tiles. Count and colour still say it. | Nice to have | Not done. |
| 11 | Judge | Sensors | The fixture's device row reads "Climate node" with no room, and the broker address card says this computer has no network address: fixture gaps (the fixture does not answer the board-setup endpoint). The page is not in the README. | Later | Not done. |
| 12 | Warden | Emergency view at 1366x768 | Clear: count, "Go here first" with the stairs, marks, routes on the plan, disclaimer. Starting a drill from the example building draws the real floor (e2e). No finding. | — | — |
| 13 | Everyone, Malay | Overview (F) | "3.7 kWj" uses the Malay abbreviation still marked [CHECK] (`bs.kwh`). | Later (Aiman) | Open: needs a native speaker's choice. |
| 14 | Judge | Ask NADI | The suggested question "Bilik mana ada orang?" is answered with the total, not a list of rooms (known since Part 10). | Later | Not done. |

## What was fixed

Items 1 to 5: wording in `dashboard/strings.json` (`alerts.audit_title`, `alerts.audit_hint`, `energy.same_yesterday`,
`energy.same_week`), `web/src/pages/energy.tsx`, `web/src/components/charts.tsx` (step lines, axis width), and the
fixture in `scripts/redesign_screenshots.py`. Re-tested: 782 pytest, 215 vitest, screenshots A, E, F, Q and R retaken
and checked by eye.

## What is left

Item 6 is the one gap that matters before the final: an admin cannot add a floor without the API. Items 7 to 10 are
polish. Items 11, 13 and 14 need fixture work, a Malay decision, or a new chat rule.

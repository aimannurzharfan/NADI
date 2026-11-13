# Final visual and copy audit (Part 28)

Walked every page of the console in English and Malay, light and dark, at 1920 x 1080 and 1366 x 768 (16 views x 6
variants, sample data). Each view was also measured in the browser: text under 14 px on screen (SVG text at its drawn
size), labels cut without a tooltip, sideways scroll, chart labels closer than 8 px to their axis, overlapping or cut
axis labels, and legend text colour. After the fixes all 96 measured views come back clean.

Screenshots: one variant per page, before and after, in `docs/design/audit/` (sample data, image chunks only).

| Page | Change | Before | After |
|---|---|---|---|
| Overview | "dB" and "people" axis titles sat on the top tick ("dB" touching "4"); now 8 px clear. Time labels 8 px under the axis (were 4). Waste card reads "RM 0.70" like every other amount (was "RM0.70"). | [before](audit/before/overview-en-light-1920.png) | [after](audit/after/overview-en-light-1920.png) |
| Emergency view | Plan labels were drawn at 11 to 13 px once the plan shrank to its box (Koridor, Stor, Tangga B, the KELUAR sign, the route numbers). The plan now measures its drawn size and keeps every label at 14 px or more; the exit sign and route numbers grow with their text. | [before](audit/before/overview-emergency-ms-dark-1366.png) | [after](audit/after/overview-emergency-ms-dark-1366.png) |
| Floor plan | Same plan labels (13 px) fixed. | [before](audit/before/floor-en-light-1920.png) | [after](audit/after/floor-en-light-1920.png) |
| Room panel | Signal and people charts: labels 8 px from the axis, unit titles clear of the top tick. People chart: every count tick shown (0 was dropped, "5, 3, 1"), last time label no longer cut at the right edge, legend text in the normal text colour (was teal, hard to read in dark). Temperature and humidity: a legend says which line is which, time labels on whole steps with room under them, chart 30 px taller. "Room ID room1" (was "Sensor room ID room1"; "ID bilik room1"). | [before](audit/before/room-panel-ms-dark-1366.png) | [after](audit/after/room-panel-ms-dark-1366.png) |
| Rooms | Table cells started 7 px from the card edge while the card title starts at 14 px; every table's first and last column now line up with the card padding. | [before](audit/before/rooms-ms-dark-1366.png) | [after](audit/after/rooms-ms-dark-1366.png) |
| Sensors | Table padding as above. "Where the boards connect": the Port label sat lower than the Broker address label and showed nothing without a port; both align to the top and an unknown port shows "–". | [before](audit/before/sensors-en-light-1920.png) | [after](audit/after/sensors-en-light-1920.png) |
| Energy | Money axes on even steps (0, 0.5, 1, 1.5; were 0, 0.35, 0.7, 1.05), labels 8 px from the axis, the last by-room tick no longer cut. First chart series uses the theme's signal teal, so bars and lines stay visible in dark. | [before](audit/before/energy-en-light-1920.png) | [after](audit/after/energy-en-light-1920.png) |
| Alerts | The audit log description was cut at 1366 in Malay; now one short line: "Every warden and admin action: who, what, from which address and when." Table padding as above. Waste alerts read "(23.6 °C)" and "RM 0.50". | [before](audit/before/alerts-ms-dark-1366.png) | [after](audit/after/alerts-ms-dark-1366.png) |
| Calibration | "Labelled empty / occupied" labels 8 px under the axis (were 4). Model card: "Not active: trained on simulated data. Goes live once it beats the rule on real labelled data." Labelling line: "Tap the number of people in the room now. Tap again when it changes, and Stop when you finish." | [before](audit/before/calibration-en-light-1920.png) | [after](audit/after/calibration-en-light-1920.png) |
| Today's summary | Time labels on whole hours (were 00:30, 02:01, 03:33, 06:30), 8 px under the axis; legend text readable in dark; table padding as above. | [before](audit/before/summary-ms-dark-1366.png) | [after](audit/after/summary-ms-dark-1366.png) |
| Export for emergency services | Plan labels were drawn at about 10 px on the printed page; now 14 px or more. | [before](audit/before/export-en-light-1920.png) | [after](audit/after/export-en-light-1920.png) |
| Plan editor | Shape labels and room IDs drawn at 13 px at 1366; now 14 px or more. Help line shortened: "Drag to draw or move a shape, or drag a handle to make it larger or smaller. Arrow keys move it by 10 (Shift: 1); Delete removes it." | [before](audit/before/editor-ms-dark-1366.png) | [after](audit/after/editor-ms-dark-1366.png) |

Copy changed without a picture: the room panel and plan hints for a room with no sensor ("Drawn on the plan for
orientation only. NADI does not count people in this room.") and with no report yet ("A sensor pair is drawn here, but
no report has arrived yet. The count is unknown until one does."), the empty Needs attention line ("Air conditioning
waste, silent sensors and suspicious readings appear here."), and "RM {amount}" / "{temp} °C" with a space everywhere
(alerts, chat answers, the room panel). Emergency, drill and safety wording, and every number, are unchanged. Malay was
rewritten alongside each English change, in standard Malay.

Rules now applied everywhere:

- Chart labels 8 px from their axis (`tickMargin={8}`), time ticks on whole local steps (`timeTicks`), money ticks on
  even steps (`moneyTicks`), count ticks all shown (`interval={0}`), legend text in the text colour with the line or
  swatch carrying the series colour, unit titles 16 px above the plot.
- Drawn plan text never under 14 px on screen (`web/src/lib/svg-scale.ts`, used by the floor plan and the editor).
- Table first and last columns at the card padding (`first:pl-4 last:pr-4` in `ui/table.tsx`).

Looked at and left as is: sentence case throughout (house style), panel headings at 14 px semibold, the calibration
chart's rotated "Motion (dB)" title (it has the room to spare and labels a scatter, not a time line), the editor's shape
list scrolling inside its box. No item was put off as "later".

# NADI console: design direction

Written before the shell and page redesign, and the rule book for it. If a screen and this page disagree, one of
them is wrong: fix it.

## What the console is for

A warden or facilities officer looks at it for a few seconds and must know: is the building all right, where are
people, and is anything wrong. So the page is quiet when the building is quiet, and the one thing that needs a
person stands out. Nothing decorates.

## What was studied, and what was taken

| Product | What it does well | Taken for NADI |
|---|---|---|
| Gmail / Google Workspace | One header over everything: hamburger, logo, a wide central box, a few icons. A sidebar that folds to an icon rail and keeps its place. | The header and the folding sidebar. The central box is "Ask NADI", because asking is this product's search. |
| Cisco Meraki dashboard | A "device status" card: a few named groups, each a count and labelled pills, one health word at the top right. | The Building status card. Pills carry a word and a mark, never colour alone. |
| Linear, Vercel | Calm density: one font, two weights doing most of the work, hairline borders in place of shadows, no ornament. | Type scale, card style, restraint with colour. |
| Stripe dashboard | Numbers set as numbers: tabular figures, label above, unit beside, small key-value tables. | The Today table, the model training table, figures everywhere. |
| Grafana, Datadog | Live time series: one line per series, a labelled threshold, readable axes, no fill for the sake of it. | The live signal chart and the labelled-reports chart. |
| Google Home / Nest | A room is a tile: name, one big state, one small detail. | The room tiles on the live floor plan (already built this way). |

## Colour roles

Each colour has one job. A colour is never the only cue: every status has a word, and usually a mark.

| Role | Light | Dark | Used for |
|---|---|---|---|
| Brand purple | `#423864` | lavender `hsl(254 50% 78%)` | Identity and interaction: the logo, headings, the active navigation pill (as a light tint), primary buttons, selected controls, links, the focus ring. |
| Signal teal | `#0097A7` | the same | Only what the sensors measure, drawn live: the signal line, the sensor pair in the room panel and the editor, the labelled dots. Never a button or a heading. |
| Green | `--ok` | | Occupied, online, all clear. |
| Amber | `--warn` | | Air conditioning on in an empty room. |
| Red | `--crit` | | Emergency and drill, and the button that starts one. |
| Grey, dashed | `--off` | | Sensor offline, no sensor, no live data. |
| Neutral | canvas `#F4F5F7`, white cards, hairline borders | dark slate | Everything else. |

How the purple-only logo fits: the logo used to carry a teal dot, and teal was also the accent of the frame. The
new logo is purple only, so purple becomes the colour of the frame and of everything a person can press, and teal is
kept for the live signal alone. Status colours are untouched. In dark mode the logo is its white variant and the
purple role is carried by a light lavender that passes AA on the dark cards.

## Type

Inter Variable, bundled. Tabular figures everywhere.

| Step | Size | Weight | Used for |
|---|---|---|---|
| Body | 14 px | 400 / 500 | The minimum. Nothing in the console is smaller, including tooltips, axis labels and table cells. |
| Section title | 15 px | 600 | Card titles, in the heading colour, sentence case. |
| Lead | 17 px | 600 | Panel titles, key lines. |
| Page title | 20 px | 600 | One per page. |
| Figure | 24 px | 600 | Numbers that are the point of a card. |
| Plan count | 22 to 52 px | 600 | The headcount in a room tile; follows the plan's width. |

No uppercase labels, no letter-spacing tricks, no italics. Sentence case. No emoji; icons come from one set (lucide,
2 px stroke), and only where they help find something.

## Spacing and layout

- One scale: 4, 8, 12, 16, 24 (Tailwind 1, 2, 3, 4, 6). Cards are 12 apart; a card's padding is 16; the page gutter is 16 to 20.
- Header 64 px, full width. Sidebar 224 px open, 72 px as an icon rail. It opens by default from 1440 px wide, is a rail below that, and the choice is remembered in the browser.
- Each page: a title row (title, a "Live" chip that says how fresh the data is, page controls on the right), then cards.
- The Overview fills the window from 1280 px wide; the live floor plan takes the space that is left, so it is always the largest thing.

## Cards

White (dark: slate) surface, 1 px border, 10 px radius, the faintest shadow. A 40 px title row with the title on the
left and at most one action or a short note on the right. No card inside a card: inside a card, groups are separated
by a hairline or by space. No coloured side stripes, no gradient, no glow.

## Pills

Fully rounded, a soft tint of the status colour, the status colour for the text, and a dot or icon in front of the
word. "No sensor" and "offline" pills have a dashed outline as well as the grey.

## Lists

A list never makes its card taller than its neighbours expect, and never pushes another card.

- Long feeds (alerts, live activity, needs attention): at most 10 rows, fewer when the card is shorter, whole rows only, no scroll box. When rows are hidden, a "View all N" link with an arrow at the foot of the card opens the full page, which has its own filters and paging.
- Short secondary lists (recent labels, live detector, change history, audit log, the building switcher): 10 rows, then a "Show N more" button. Expanded, the list scrolls inside the card at a fixed maximum height and the button reads "Show fewer".
- A page's own main table is the full list: the page scrolls.
- Lists a person's safety depends on (the emergency order, the export, incident reports) show everything.

## Selection

A selected room on the Overview plan carries a 3 px purple ring and a small purple corner tab with a tick: purple
because it is something the viewer did, a shape as well as a colour. Click selects; a link, or a double-click,
opens. Selection lives in the address so it survives a refresh and can be shared.

## The highlight figure

One figure per screen may be set at Figure size as the first thing in its card: on the Overview it is the air
conditioning waste today (RM, with kWh beside it and one status pill). It is made by size and position, never by a
tint, a stripe or a card inside a card. It is amber only while it is above zero.

## Settings

Read first, edit on request: values are shown as a label, a figure and a unit; "Edit" turns them into fields with
the unit after each field; "Save" shows what will change (old → new) before it is stored; errors sit under their
field in the page's language. Who changed it last, and when, is always shown.

## Charts

- One 2 px teal line per series, no area fill. The band above the threshold is a neutral tint, the threshold is a dashed line with its value written on it.
- Axes: 14 px, muted, hairline grid, a unit on the y axis.
- Dots (labelled reports): hollow grey for "labelled empty", solid teal for "labelled occupied", so the two are told apart without colour.
- Nothing animates on a timer. A chart moves when a new report arrives.

## Motion

Data-driven only: a tile ring and a count roll per new report (the Overview tiles draw no sensor line). The sidebar and the
side panel slide once when opened. None of it during an emergency or drill, or when the viewer asked for reduced motion.

## Honesty

Screenshots from sample data name the building "Demo building (sample data)". Simulated numbers say "simulated". The live detector is named for what is really
counting; MindSpore is named as the detector only while a trained model is active. A room with no sensor says
"No sensor"; a sensor that is silent says so. "All clear" is never shown while no sensor is reporting.

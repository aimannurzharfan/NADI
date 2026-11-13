# Demo runbook (stage day)

For the semi-final at TRX and the final at PICC. Venue Wi-Fi is not to be trusted: bring our own network.
All commands are for Windows PowerShell, run in the project folder.

## The network

1. **Our own phone hotspot on 2.4 GHz.** The boards cannot use 5 GHz.
   - iPhone: Settings > Personal Hotspot > turn on **Maximize Compatibility** (forces 2.4 GHz).
   - Android: Hotspot settings > Band > **2.4 GHz**. If it offers a fixed channel, pick 1, 6 or 11 and keep it.
   - Keep the hotspot name and password the same every time, so the boards' saved settings keep working.
2. **Laptop on the same hotspot.** Not venue Wi-Fi, not a cable.
3. **Windows network profile Private:** Settings > Network & internet > Wi-Fi > the hotspot > **Private network**. The firewall rule for TCP 1883 (firmware README section 1, step 5) must allow the Private profile.
4. **Laptop address.** A hotspot hands out a new address. Run `ipconfig` and note the "IPv4 Address" of the Wi-Fi adapter.
   - Put it in `.env` as `MQTT_LAN_IP=...` **before** `docker compose up`. With an old address Docker refuses to start the broker ("ports are not available").
   - The dashboard footer > **Board address** warns if the broker still listens on an old address.
   - On the receiver and climate node, open the serial port and type `setup`; change only the Wi-Fi name and password (if different) and the broker address. No reflashing.
5. **Check:** both boards' LEDs turn green within a minute; the dashboard shows the room live.

Set this up the day before at home with the same phone, then again at the venue at least 30 minutes before the slot.

## Exact steps: reset, start, demo, drill

**1. Stop anything left over and start the services** (Docker Desktop must be running: whale icon in the taskbar).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
docker compose up -d --wait
```

**2. Clear test data** (history, live counts, alerts and air conditioning totals; keeps devices, labels, the model
and the audit log). Old incident and drill reports are kept in `data\incidents`: move that folder away if the
Alerts page should show only today's.

```powershell
.\.venv\Scripts\python scripts\reset_demo_data.py --yes
```

The reset keeps the headcount labels and the stored reports inside a label, so the labelled reports on the
Calibration page are still there. Everything else in the history, the live counts, alerts and waste totals is cleared.

**3a. Live boards: start the server** (and nothing else; the boards send the data).

```powershell
.\.venv\Scripts\python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --limit-concurrency 200 --timeout-keep-alive 5
```

**3b. No boards: the fixed demo story instead.** Set `DEMO_SCENARIO=on` in `.env`, then the same server command.
The story starts by itself and repeats every 3 minutes 20 seconds; every screen is labelled **DEMO SCENARIO**. Do not
run `sim\fake_sensor.py` at the same time. The story: rooms fill, Lab 2 empties with the air conditioning still on
(flagged a minute later), Hall A and Room 3 fill up ("at least 5 people, in 2 rooms"), the alarm sounds at 2:00 and
everyone is out by 2:45. Every room uses Wi-Fi sensing (0, 1, 2 or 3+). `DEMO_BIG_HALL=on` makes Hall A a people
counter passing 100 instead; it is labelled "Simulated counter (phase 2)" on every screen. Leave it off on stage
unless the slide talks about phase 2.

**4. Open the dashboard** on the server laptop at http://127.0.0.1:8000 (add `?lang=ms` for Malay). Use
`127.0.0.1`, not the Wi-Fi address: on this laptop that counts as admin without a token. Press F11 for full screen.

**5. Sensors page:** press **Clear test devices**, so the list shows only the real boards.

**5b. Waste delay for live boards** (so the amber "air conditioning on in an empty room" flag shows within the slot):
on the **Energy** page, in **Energy settings**, press **Edit**, set **Waste flagged after** to `1` minute, **Save**
and confirm. It applies from the next report. Set it back after the slot the same way (`10` minutes): the change and
the change back are both in the change history and the audit log. Once a value has been saved here, `WASTE_MINUTES`,
`AC_KW`, `TARIFF_RM_PER_KWH` and `CO2_KG_PER_KWH` in `.env` are no longer read. The demo scenario (3b) needs none of
this: it flags waste after its own 60 seconds whatever is saved, and leaves the saved value alone.

**5c. Demo order with live boards** (about 5 minutes; the room is called "Demo Room" in `ROOM_NAMES`):

1. **Overview.** The building chip at the top of the sidebar must read the demo building and Level 4. If it shows
   "Example Tower (example data)", press it: a panel opens beside the sidebar with the buildings on the left and the
   highlighted building's floors on the right. Type `level 4` in its search box and press Enter (or pick the
   building, then Level 4). Point at the building status (air conditioning waste today is the large figure) and the
   live floor plan.
2. **Walk in and out.** One person walks through the line between the two boards, then leaves. The room's tile goes
   from 0 to 1 and back within about one report (10 s), and the small trace on the tile jumps.
3. **Select Demo Room.** Click its tile on the plan (or pick it in the People card's list): the **People** card
   under the plan shows "Now 1 · since HH:MM" and the room's people per minute over the last hour; the walk shows
   as a step within a minute. The range buttons on the card (a list at 1366 px) switch to 24 hours, 7 days or
   30 days; a break in the line is a time the sensor sent nothing. Leave it on **1 h** for the walk.
4. **Room details** (the link on the People card, or a double-click on the tile) opens the room panel: the count
   and the nearest exit at the top, the same People chart, then **Signal**: the sensor pair picture and the live
   signal of the last 5 minutes. Have someone walk again: the line rises above the dashed threshold and falls
   back. Temperature and humidity are below it.
5. **Energy.** The **Today**, **7 days** and **30 days** buttons at the top switch the three figures (wasted RM with
   the change against the period before, kWh, CO2), the chart (per hour today, per day otherwise) and the ranked
   room list under it. Click **Demo Room** in the list: the chart shows that room only, and the chip beside the
   chart's title removes the filter. The **Energy settings** card below shows the tariff and the rule in force;
   **History** lists every change.
6. **Calibration** (bottom of the sidebar, admin): the labelled reports as dots against the threshold, the live
   detector table ("Calibrated rule", threshold in dB), and the MindSpore card saying the model is not counting.
7. **Ask NADI:** the box in the middle of the header (or press `/`). Ask "How many people are inside?" and the same in
   Malay; the side panel opens with the answer and says the numbers come from live sensor data. The chip at the top
   of the panel says what the answers cover, **This floor: Level 4** or **Whole building**; every answer starts with
   it. During the drill (step 6) it is locked to the whole building and adds a count per floor.

**6. The drill** (the safe way to show emergency mode live; every screen carries a yellow **DRILL** banner and every
alert says [DRILL], so nobody can mistake it for a real alarm):

1. Press **Start emergency mode**, then **Start drill**. Say: "This is a drill."
2. Point at the rescue order, the nearest stairs and the live count.
3. Mark one room **Clear** and one **Need help**: every screen shows it.
4. Press **Export for emergency services**: the one-page snapshot with the number to call and the warden marks.
   Mention that the server has already saved this snapshot by itself, and saves it again every minute.
5. Press **End drill**, then **End the drill on every screen**. On the Alerts page, open the new drill report: how
   long each room took to empty, the marks, the sensors offline, the alerts and who acknowledged them.

In demo-scenario mode, run the drill outside the story's own alarm (before 2:00 or after the all clear).

**7. Afterwards:** `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1`, then `docker compose stop`.

## Checklist before the slot

- [ ] Steps 1 to 5 above done; the header shows every room reporting; the sidebar chip shows the demo building.
- [ ] Live boards: Energy settings show "Waste flagged after 1 minute" (step 5b); set back to 10 afterwards.
- [ ] People card on **1 h** and the Energy page on **7 days** (both remember the last choice in this browser).
- [ ] Boards powered from chargers or always-on power banks; positions taped and not moved since labelling.
- [ ] Dashboard full screen at 1920x1080 or 1366x768; laptop on mains power, sleep and Windows Update paused.
- [ ] No clock warning at the top of the dashboard (a wrong laptop clock puts wrong times on the export and the report).
- [ ] Ollama running (Ollama icon in the taskbar) if the chat should rephrase answers; without it the chat still answers.
- [ ] Air conditioner code learnt; `send` tested at the venue distance.
- [ ] Backup video open in a second window: `docs\demo\nadi_demo.webm` (made locally with `scripts\record_demo.py`; videos are not committed). Also on a phone or USB stick.

## Showing the IR send live

Judges cannot see infrared. Hold a phone with its camera open in front of the KY-005 (front cameras usually show IR best), and either press **send** in the climate node's serial monitor or let the server send `ac_off`. The phone screen shows a purple-white flash and the LED blinks white; the air conditioner beeps or switches off. To rehearse without an air conditioner, type `irtest`: ten flashes, one a second.

## What can fail on stage, and the fallback

Do not debug in front of the judges. Each line: what you see, then what to do.

| What fails | Fallback (one line) |
|---|---|
| Docker Desktop not running (`docker compose` says it cannot connect) | Start Docker Desktop, wait for the whale icon to stop moving, run step 1 again. |
| Broker will not start: "ports are not available ... 1883" or "8883" | `MQTT_LAN_IP` in `.env` is an old address: set it to today's `ipconfig` address (or empty), run `docker compose up -d --wait`. |
| Server will not start: port 8000 already in use | `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1`, then start it again. |
| Hotspot drops or a board stops reporting | Rooms show "?" with the last count, never 0; say so, it is the safety feature. If it lasts, switch to step 3b. |
| Board LED not green (red = Wi-Fi, yellow = broker or firewall, purple = sender) | Serial `setup` and check that setting (docs/BOARD_DAY.md); if not fixed in 1 minute, step 3b. |
| Boards online but counts look wrong | Say it is uncalibrated in this room; switch to step 3b for the story. |
| Old test numbers or alerts on screen | Step 2 (reset), then restart the server. |
| Red "offline" banner (database, history or sensor link) | `docker compose up -d --wait`; the dashboard recovers by itself within about 30 seconds. |
| Dashboard says the server is unreachable | Start the server again (step 3); emergency or drill state survives a restart. |
| Admin buttons ask for a token | You opened the Wi-Fi address: open http://127.0.0.1:8000 instead, or type the admin token. |
| Chat slow or "built-in answers" shown | Ollama stopped: the checked built-in answers are correct; carry on (start Ollama after the slot). |
| Clock warning at the top | Settings > Time & language > Date & time > **Sync now**; with no internet, set `NTP_CHECK=off` and restart the server. |
| Started a real emergency instead of a drill | Press **End emergency mode** at once and say so; the report marks it, and the next start can be a drill. |
| IR does not switch the air conditioner off | Aim from 1 to 2 m straight at it; show the flash on a phone camera instead. |
| Projector cuts the edges or text is tiny | Set the laptop to 1366x768 or 1920x1080 (both tested); Ctrl and minus to zoom out. |
| Laptop fails | Play the backup video from the phone or USB stick. |

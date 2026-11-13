// What the overview says about the building: the status pills by group, the "needs attention" queue, the
// state of the sensing line and today's figures. Pure functions, so every rule is tested without a browser.
import { dateTime, hhmm, shown, totals } from "./format";
import { T } from "./i18n";
import type { Alert, Energy, History, Incidents, Room, RoomsState, Uptime } from "./types";

export type Level = "calm" | "watch" | "act";
export type AttentionKind = "connection" | "service" | "sensor" | "waste" | "suspicious";

/** One card in the queue: where, what and how bad, and what to do about it. */
export type AttentionItem = {
  id: string;
  kind: AttentionKind;
  title: string;
  detail: string;
  todo: string;
  /** set when acknowledging an alert clears the card */
  alertId?: string;
};

export const SEP = " · ";
/** A "suspicious reading" alert stays in the queue this long unless an admin acknowledges it. */
export const SUSPICIOUS_KEEP_S = 600;

/** "45 s", "14 min", "2 h": how long something has lasted. */
export function span(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return T("ov.span_s", { n: s });
  if (s < 3600) return T("ov.span_min", { n: Math.floor(s / 60) });
  return T("ov.span_h", { n: Math.floor(s / 3600) });
}

export const cleanSubject = (s: string) => s.replace(/^NADI:\s*/, "");

/** The server words this alert from the same strings file, in the language this page asked for. */
export const isSuspicious = (a: Alert, now: number) =>
  a.kind === "info" && !a.ack && now - a.ts < SUSPICIOUS_KEEP_S && a.subject === T("alert.suspicious_subject");

const SERVICES = [
  { id: "redis", title: "ov.att_redis", detail: "banner.redis" },
  { id: "mqtt", title: "ov.att_mqtt", detail: "banner.mqtt" },
  { id: "mysql", title: "ov.att_mysql", detail: "banner.mysql" },
] as const;

/** Everything that needs a person, most urgent first. `lost`: the server cannot be reached (with the time of the data
 *  still on screen, if any). */
export function attentionItems(data: RoomsState | undefined, lost?: { since: number | null } | null): AttentionItem[] {
  const out: AttentionItem[] = [];
  if (lost) {
    out.push({ id: "connection", kind: "connection", title: T("ov.att_connection"),
      detail: T("banner.server", { time: lost.since ? hhmm(lost.since) : "–" }), todo: T("ov.todo_connection") });
  }
  if (!data) return out;
  const off = data.offline ?? {};
  for (const s of SERVICES) {
    if (!(s.id in off)) continue;
    const since = s.id === "redis" ? data.stale_ts || off.redis || data.now : off[s.id] || data.now;
    out.push({ id: `service:${s.id}`, kind: "service", title: T(s.title), detail: T(s.detail, { time: hhmm(since) }), todo: T("ov.todo_service") });
  }
  // with the server, the live store or the sensor link down every room reads "not live": one card above says why
  const blind = !!lost || "redis" in off || "mqtt" in off;
  if (!blind) {
    for (const r of data.rooms) {
      if (r.live) continue;
      out.push({ id: `sensor:${r.room_id}`, kind: "sensor", title: r.name,
        detail: [r.count_ts ? T("ov.att_sensor_for", { span: span(data.now - r.count_ts) }) : T("ov.att_sensor"),
          r.headcount != null && r.count_ts ? T("ov.att_last_known", { count: shown(r.headcount, r.at_least) }) : T("ov.att_unknown")].join(SEP),
        todo: T("ov.todo_sensor") });
    }
  }
  for (const r of data.rooms) {
    if (!r.waste) continue;
    out.push({ id: `waste:${r.room_id}`, kind: "waste", title: r.name,
      detail: [T("ov.att_waste", { minutes: r.waste.minutes }), T("ov.att_rm", { rm: r.waste.rm.toFixed(2) })].join(SEP),
      todo: T("ov.todo_waste") });
  }
  for (const a of data.alerts) {
    if (!isSuspicious(a, data.now)) continue;
    out.push({ id: `alert:${a.id}`, kind: "suspicious", title: cleanSubject(a.subject), detail: a.message, todo: T("ov.todo_suspicious"), alertId: a.id });
  }
  return out;
}

export type Feed = "live" | "none" | "stopped";

/** Whether the screen is showing live readings. stopped: the server cannot be reached or its live store is down, so
 *  nothing on screen is updating. none: the server answers but no sensor is reporting. live: at least one is. */
export function feedOf(data: RoomsState | undefined, lost: boolean): Feed {
  if (lost || !data || data.stale_ts) return "stopped";
  return data.rooms.some((r) => r.live) ? "live" : "none";
}

/** ACT: an emergency or drill is on. WATCH: something is in the queue. CALM otherwise. */
export function levelOf(data: RoomsState | undefined, items: AttentionItem[]): Level {
  if (data?.emergency.on) return "act";
  return items.length ? "watch" : "calm";
}

export type PillTone = "ok" | "warn" | "crit" | "off" | "neutral";
/** One labelled pill of the building status card. dashed: grey states (offline, no sensor) also get a dashed outline. */
export type StatusPillSpec = { id: string; tone: PillTone; text: string; dashed?: boolean };
export type StatusGroup = { id: "rooms" | "ac" | "sensors"; pills: StatusPillSpec[] };

const many = (n: number, one: string, more: string) => T(n === 1 ? one : more, { n });

/** The building at a glance, as three groups of labelled pills: air conditioning, rooms, sensors (an emergency has
 *  the header button and the full-screen view; its normal-day line is in today's summary).
 *  `plan` is the rooms drawn on the floor plan (id and whether a sensor pair is drawn for it): a plan room that never
 *  reported is "no sensor", or "no report yet" when it has a pair. A room whose sensor is not reporting is unknown,
 *  never "empty", and "No waste" is only said while at least one sensor is reporting. */
export function buildingStatus(data: RoomsState, plan: { id: string; linked: boolean }[] = []): StatusGroup[] {
  const t = totals(data.rooms);
  const empty = t.live.length - t.occupied;
  const known = new Set(data.rooms.map((r) => r.room_id));
  const silent = plan.filter((r) => !known.has(r.id));
  const noSensor = silent.filter((r) => !r.linked).length, noReport = silent.length - noSensor;
  const rooms: StatusPillSpec[] = [];
  if (t.occupied) rooms.push({ id: "occupied", tone: "ok", text: T("bs.occupied", { n: t.occupied }) });
  if (empty) rooms.push({ id: "empty", tone: "neutral", text: T("bs.empty", { n: empty }) });
  if (t.unknown.length) rooms.push({ id: "unknown", tone: "off", dashed: true, text: T("bs.unknown", { n: t.unknown.length }) });
  if (noReport) rooms.push({ id: "no-report", tone: "off", dashed: true, text: T("bs.no_report", { n: noReport }) });
  if (noSensor) rooms.push({ id: "no-sensor", tone: "off", dashed: true, text: T("bs.no_sensor", { n: noSensor }) });
  if (!rooms.length) rooms.push({ id: "none", tone: "off", dashed: true, text: T("ov.no_live_data") });

  const wasting = data.rooms.filter((r) => r.waste).length;
  const ac: StatusPillSpec = wasting ? { id: "waste", tone: "warn", text: many(wasting, "bs.waste_one", "bs.waste_many") }
    // nothing wasting now: "No waste" only when today's total is nothing too
    : t.live.length ? { id: "no-waste", tone: "ok", text: T((data.waste_today_rm ?? 0) > 0 ? "bs.none_now" : "bs.no_waste") }
    : { id: "none", tone: "off", dashed: true, text: T("ov.no_live_data") };

  const total = data.rooms.length, live = data.rooms.filter((r) => r.live).length;
  const sensors: StatusPillSpec[] = [];
  if (!total) sensors.push({ id: "none", tone: "off", dashed: true, text: T("bs.none_reporting") });
  else if (live === total) sensors.push({ id: "online", tone: "ok", text: T("bs.all_online", { n: total }) });
  else {
    sensors.push({ id: "offline", tone: "off", dashed: true, text: T("bs.offline", { n: total - live }) });
    if (live) sensors.push({ id: "online", tone: "ok", text: T("bs.online", { n: live }) });
  }

  return [{ id: "ac", pills: [ac] }, { id: "rooms", pills: rooms }, { id: "sensors", pills: sensors }];
}

/** The one pill at the top right of the status card, from the same CALM / WATCH / ACT logic as before (levelOf).
 *  "All clear" is never said while nothing is reporting: then it says so, in grey. */
export function overallStatus(data: RoomsState | undefined, items: AttentionItem[], lost: boolean): StatusPillSpec & { level: Level } {
  const level = levelOf(data, items);
  if (level === "act") {
    return { id: "act", level, tone: "crit", text: T(data?.emergency.drill ? "bs.drill" : "bs.emergency_on") };
  }
  if (level === "watch") return { id: "watch", level, tone: "warn", text: many(items.length, "bs.attention_one", "bs.attention_many") };
  const feed = feedOf(data, lost);
  if (feed !== "live") return { id: "no-data", level, tone: "off", dashed: true, text: T(feed === "none" ? "ov.no_live_data" : "ov.not_live") };
  return { id: "calm", level, tone: "ok", text: T("bs.all_clear") };
}

/** Y axis of the signal chart: always tall enough to show the threshold with room above it. */
export function signalScale(values: number[], threshold: number | null) {
  const max = Math.max(0, ...values.filter((v) => isFinite(v)), threshold != null && isFinite(threshold) ? threshold * 1.6 : 0);
  // at most four steps to the top, in even whole numbers (0, 2, 4, ...), whatever the size of the numbers
  const step = [2, 4, 10, 20, 50, 100, 250, 500].find((s) => max / s <= 4) ?? 2 * 10 ** Math.ceil(Math.log10(max / 8));
  const top = Math.max(step * 2, Math.ceil(max / step - 1e-9) * step);
  const ticks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Number(v.toFixed(2)));
  return { top, step, ticks };
}

const MYT_OFFSET_S = 8 * 3600;  // Malaysia time, no daylight saving

/** Unix time of the last midnight in Malaysia. */
export const midnightBefore = (now: number) => Math.floor((now + MYT_OFFSET_S) / 86400) * 86400 - MYT_OFFSET_S;

/** How many minutes of history cover today, in 15-minute steps so the request stays the same for a while. */
export const minutesToday = (now: number) => Math.max(15, Math.ceil((now - midnightBefore(now)) / 900) * 15);

export type Today = { peak: number; occupiedHours: number };

/** Today's figures from the bucketed history: the most people at once and how long anyone was inside. (Sensor uptime
 *  comes from the server, GET /api/uptime: the buckets here are too coarse to see a short outage.) */
export function todayStats(hist: History | undefined, now: number): Today | null {
  const b = hist?.bucket_s;
  if (!hist || !b) return null;
  const start = midnightBefore(now);
  const people = new Map<number, number>();
  for (const points of Object.values(hist.rooms)) {
    for (const [ts, n] of points) {
      if (ts >= start && ts <= now) people.set(ts, (people.get(ts) ?? 0) + n);
    }
  }
  if (!people.size) return { peak: 0, occupiedHours: 0 };
  const counts = [...people.values()];
  return { peak: Math.max(...counts), occupiedHours: (counts.filter((n) => n > 0).length * b) / 3600 };
}

/** "100%" only when nothing was missed; otherwise one decimal, rounded down, so a short outage still shows. */
export function uptimeText(pct: number | null | undefined): string {
  if (pct == null || !isFinite(pct)) return "–";
  if (pct >= 100) return "100%";
  return `${(Math.floor(Math.max(0, pct) * 10) / 10).toFixed(1)}%`;
}

/** A room drawn on the floor plan, and whether a sensor pair is drawn for it. */
export type PlanRoomRef = { id: string; linked: boolean };

/** The room the live signal starts on when the viewer has not chosen one. The console knows each room's latest
 *  count, so "most recent movement" is the live sensing room that is occupied now with the newest report. Failing
 *  that: the first live sensing room (one with its boards on the plan first), then any sensing room, then a plan room
 *  with a sensor pair, then any room at all. */
export function defaultRoom(rooms: Room[], plan: PlanRoomRef[]): string | null {
  const linked = new Set(plan.filter((p) => p.linked).map((p) => p.id));
  const sensing = rooms.filter((r) => r.counter !== "count");
  const moving = sensing.filter((r) => r.live && (r.headcount ?? 0) > 0).sort((a, b) => (b.count_ts ?? 0) - (a.count_ts ?? 0))[0];
  const first = moving ?? sensing.find((r) => r.live && linked.has(r.room_id)) ?? sensing.find((r) => r.live)
    ?? sensing.find((r) => linked.has(r.room_id)) ?? sensing[0];
  return first?.room_id ?? plan.find((p) => p.linked)?.id ?? rooms[0]?.room_id ?? plan[0]?.id ?? null;
}

/** Which room is selected: the one in the address, else the viewer's last choice, else the default. A room that is
 *  not (or no longer) known is passed over, never shown. */
export function pickRoom(known: Iterable<string>, fromUrl: string | null, stored: string | null, fallback: string | null): string | null {
  const ids = new Set(known);
  for (const id of [fromUrl, stored, fallback]) if (id && ids.has(id)) return id;
  return null;
}

export const ROOM_KEY = "nadiOverviewRoom";

/** The viewer's last choice of room, kept in this browser. Storage can be blocked or full: then there is none. */
export function storedRoom(): string | null {
  try {
    return localStorage.getItem(ROOM_KEY);
  } catch {
    return null;
  }
}

export function storeRoom(id: string) {
  try {
    localStorage.setItem(ROOM_KEY, id);
  } catch {
    /* private window or blocked storage: the address still carries the choice */
  }
}

/** The "Emergency and drills" line of today's summary: what is happening now, and what happened today. */
export function drillLine(incidents: Incidents | undefined, emergency: RoomsState["emergency"] | undefined, now: number): { value: string; hint: string; tone?: "crit" } {
  const start = midnightBefore(now);
  const all = incidents?.incidents ?? [];
  const today = all.filter((i) => i.started >= start);
  const drills = today.filter((i) => i.kind === "drill"), real = today.filter((i) => i.kind === "real");
  const lastDrill = all.filter((i) => i.kind === "drill").sort((a, b) => b.started - a.started)[0];
  const value = emergency?.on ? T(emergency.drill ? "bs.drill" : "bs.emergency_on") : T("ov.today_normal");
  const parts: string[] = [];
  if (real.length) parts.push(T("ov.today_emergencies", { n: real.length }));
  if (drills.length) {
    const last = Math.max(...drills.map((d) => d.started));
    parts.push(T(drills.length === 1 ? "ov.today_drills_one" : "ov.today_drills_many", { n: drills.length, time: hhmm(last) }));
  } else if (!real.length) {
    parts.push(lastDrill ? T("ov.today_last_drill", { date: dateTime(lastDrill.started) }) : T("ov.today_no_drill"));
  }
  return { value, hint: parts.join(SEP), tone: emergency?.on ? "crit" : undefined };
}

export type SummaryRow = { id: string; peak: number | null; hours: number | null; uptimePct: number | null; wasteRm: number | null };

/** One row per room for the full summary of the day: every room that has a figure today from the history, the
 *  uptime or the energy answer. A figure a room has no data for is null (shown as a dash), never 0. */
export function summaryRows(hist: History | undefined, uptime: Uptime | undefined, energy: Pick<Energy, "by_room"> | undefined, now: number): SummaryRow[] {
  const waste = new Map((energy?.by_room ?? []).map((r) => [r.room_id, r.rm_today]));
  const ids = new Set([...Object.keys(hist?.rooms ?? {}), ...Object.keys(uptime?.rooms ?? {}),
    ...[...waste].filter(([, v]) => v > 0).map(([id]) => id)]);
  return [...ids].sort().map((id) => {
    const day = hist?.rooms[id]?.length ? todayStats({ ...hist, rooms: { [id]: hist.rooms[id] } }, now) : null;
    const up = uptime?.rooms[id];
    return {
      id, peak: day?.peak ?? null, hours: day?.occupiedHours ?? null,
      uptimePct: up && up.expected_s > 0 ? (up.up_s / up.expected_s) * 100 : null,
      wasteRm: energy ? waste.get(id) ?? 0 : null,
    };
  });
}

import { LANG, T } from "./i18n";
import type { Room } from "./types";

export const SHOWN_MAX = 100;

/** How a count is shown: "3+" when it is a minimum (CSI's "3 or more"), "100+" above 100. Without the flag, 3 is
 *  read as CSI's "3 or more" (history points carry no flag). */
export function shown(n: number | null | undefined, atLeast?: boolean): string {
  if (n == null) return "–";
  if (n > SHOWN_MAX) return `${SHOWN_MAX}+`;
  return (atLeast ?? n === 3) ? `${Math.round(n)}+` : String(Math.round(n));
}

/** A room's count: "?" when its sensor is not reporting (never shown as 0). */
export const countOf = (r: Room | undefined) => (!r ? "–" : !r.live || r.headcount == null ? "?" : shown(r.headcount, r.at_least));

/** People in the reporting rooms, whether that is a minimum, and the rooms whose count is unknown. */
export function totals(rooms: Room[]) {
  const live = rooms.filter((r) => r.live && r.headcount != null);
  const unknown = rooms.filter((r) => !(r.live && r.headcount != null));
  const people = live.reduce((s, r) => s + (r.headcount ?? 0), 0);
  const atLeast = live.some((r) => r.at_least) || unknown.length > 0;
  return { live, unknown, people, atLeast, occupied: live.filter((r) => (r.headcount ?? 0) > 0).length };
}

/** "12" or "at least 12". */
export const peopleTotal = (t: { people: number; atLeast: boolean }) => (t.atLeast ? T("count.at_least", { n: t.people }) : String(t.people));

export const unknownText = (n: number) => T(n === 1 ? "count.unknown_one" : "count.unknown_many", { n });

export const peopleWord = (n: number | null | undefined) => T(n === 1 ? "unit.person" : "unit.people");

export function ago(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return T("time.never");
  if (seconds < 5) return T("time.just_now");
  if (seconds < 60) return T("time.seconds", { n: Math.floor(seconds) });
  if (seconds < 3600) return T("time.minutes", { n: Math.floor(seconds / 60) });
  if (seconds < 86400) return T("time.hours", { n: Math.floor(seconds / 3600) });
  return T("time.days", { n: Math.floor(seconds / 86400) });
}

const locale = LANG === "ms" ? "ms-MY" : "en-GB";
/** Times are stored as Unix seconds (UTC) and always shown in Malaysia time, whatever the viewer's own time zone. */
export const TIME_ZONE = "Asia/Kuala_Lumpur";
const tz = { timeZone: TIME_ZONE, hourCycle: "h23" } as const;  // 24-hour in both languages (ms-MY would say "PG")

export const hhmm = (ts: number) => new Date(ts * 1000).toLocaleTimeString(locale, { ...tz, hour: "2-digit", minute: "2-digit" });
export const hhmmss = (ts: number) => new Date(ts * 1000).toLocaleTimeString(locale, tz);
export const dateTime = (ts: number) =>
  new Date(ts * 1000).toLocaleString(locale, { ...tz, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
/** "3 Nov 2026, 07:45:00": for reports and exports. */
export const fullDateTime = (ts: number) =>
  new Date(ts * 1000).toLocaleString(locale, { ...tz, day: "numeric", month: "short", year: "numeric", hour: "2-digit",
    minute: "2-digit", second: "2-digit" });
/** "12 Nov 2026" */
export const dateOnly = (ts: number) => new Date(ts * 1000).toLocaleDateString(locale, { ...tz, day: "numeric", month: "short", year: "numeric" });
/** "12 Nov 2026, 14:02": when a setting was changed */
export const dateTimeYear = (ts: number) =>
  new Date(ts * 1000).toLocaleString(locale, { ...tz, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
/** "20 Oct": a day on a chart or in a note */
export const dayMonth = (ts: number) => new Date(ts * 1000).toLocaleDateString(locale, { ...tz, day: "numeric", month: "short" });
/** "2026-10-20": the Malaysian day a moment falls on */
export const isoDay = (ts: number) => new Date((ts + 8 * 3600) * 1000).toISOString().slice(0, 10);
export const dayLabel = (iso: string) => new Date(`${iso}T12:00:00+08:00`).toLocaleDateString(locale, { ...tz, weekday: "short", day: "numeric" });

export function duration(s: number): string {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : String(m)) + `:${String(x).padStart(2, "0")}`;
}

export function uptime(s: number | null | undefined): string {
  if (s == null) return "–";
  const d = Math.floor(s / 86400), h = Math.floor(s / 3600) % 24, m = Math.floor(s / 60) % 60;
  return d ? `${d} d ${h} h` : h ? `${h} h ${m} min` : `${m} min`;
}

export const rm = (v: number | null | undefined) => (v == null ? "–" : `RM ${v.toFixed(2)}`);
export const temp = (c: number | null | undefined) => (c == null ? "–" : `${c.toFixed(1)} °C`);
export const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v)}%`);
export const num = (v: number | null | undefined, digits = 0) =>
  v == null ? "–" : v.toLocaleString(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits });

export type RoomStatus = "ok" | "empty" | "waste" | "off";

export const statusOf = (r: Room | undefined): RoomStatus =>
  !r || !r.live ? "off" : r.waste ? "waste" : (r.headcount ?? 0) > 0 ? "ok" : "empty";

/** Change against the previous period, or null when either side is missing. */
export function change(cur: number | null | undefined, prev: number | null | undefined): number | null {
  if (cur == null || prev == null) return null;
  return cur - prev;
}

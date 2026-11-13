// Recorded waves: per-packet signal strength saved from a real board session (web/public/recordings/*.json, written
// by scripts/record_waves.py). The files are static data, so they are checked before anything is drawn.
import type { Recording } from "./types";

export const MAX_POINTS = 6000;  // two minutes at 50 packets a second
const FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.json$/;
const KINDS = ["empty", "walk", "hand", "moved"];

export const isRecordingFile = (name: unknown): name is string => typeof name === "string" && FILE.test(name);

/** The spread of a list of numbers (population standard deviation), 0 for fewer than two. */
export function spread(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  return Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length);
}

/** A recording that can be drawn, or null: the figures under the chart are worked out from the packets themselves,
 *  never taken from the file's own summary. */
export function cleanRecording(raw: unknown, roomId: string): Recording | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (r.room_id !== roomId || !Array.isArray(r.points)) return null;
  const points: [number, number][] = [];
  for (const p of r.points.slice(0, MAX_POINTS)) {
    if (Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]) && p[0] >= 0 && p[1] <= 0 && p[1] >= -120) points.push([p[0], p[1]]);
  }
  if (points.length < 2) return null;
  points.sort((a, b) => a[0] - b[0]);
  const rssi = points.map((p) => p[1]);
  const distance = typeof r.distance_m === "number" && Number.isFinite(r.distance_m) && r.distance_m > 0 ? r.distance_m : null;
  return {
    room_id: roomId,
    name: typeof r.name === "string" ? r.name.slice(0, 60) : "",
    kind: typeof r.kind === "string" && KINDS.includes(r.kind) ? r.kind : "other",
    date: typeof r.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(r.date) ? r.date : "",
    distance_m: distance,
    packets: points.length,
    duration_ms: points[points.length - 1][0] - points[0][0],
    std_db: spread(rssi),
    mean_dbm: rssi.reduce((a, b) => a + b, 0) / rssi.length,
    points: points.map(([t, v]) => [t - points[0][0], v]),
  };
}

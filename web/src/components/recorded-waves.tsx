// Recorded waves: the signal strength of every packet between a room's two boards, saved from a real session.
// The charts are stacked on one y-axis (RSSI, dBm) and one time scale, so a still room and a disturbed one can be
// compared by eye; the measured spread under each is worked out from the packets shown. Nothing here is live.
import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { useRecordings } from "@/lib/api";
import { LANG, T, hasKey } from "@/lib/i18n";
import type { Recording } from "@/lib/types";

const axis = { fontSize: 14, fill: "hsl(var(--muted-foreground))" };

export const kindName = (kind: string) => T(hasKey(`rec.kind.${kind}`) ? `rec.kind.${kind}` : "rec.kind.other");

/** "2 November 2026" from "2026-11-02", in the language of the page. */
export function longDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (!iso || Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(LANG === "ms" ? "ms-MY" : "en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(d);
}

export function sourceLine(r: Pick<Recording, "date" | "distance_m">): string {
  return r.distance_m != null ? T("rec.source", { date: longDate(r.date), distance: r.distance_m })
    : T("rec.source_no_distance", { date: longDate(r.date) });
}

function Wave({ rec, seconds, low, high, size }: { rec: Recording; seconds: number; low: number; high: number; size?: { width: number; height: number } }) {
  const data = rec.points.map(([ms, v]) => ({ t: ms / 1000, v }));
  const step = seconds <= 20 ? 5 : seconds <= 60 ? 10 : 30;
  const ticks: number[] = [];
  for (let t = 0; t <= seconds + 1e-6; t += step) ticks.push(t);
  const yStep = high - low <= 12 ? 2 : high - low <= 30 ? 5 : 10;
  const yTicks: number[] = [];
  for (let v = Math.ceil(low / yStep) * yStep; v <= high; v += yStep) yTicks.push(v);
  const chart = (
    <LineChart data={data} width={size?.width} height={size?.height} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
      <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
      <XAxis dataKey="t" type="number" domain={[0, seconds]} ticks={ticks} tick={axis} tickLine={false} tickMargin={8} axisLine={{ stroke: "hsl(var(--border))" }} allowDataOverflow />
      <YAxis domain={[low, high]} ticks={yTicks} tick={axis} tickLine={false} axisLine={false} width={48} allowDataOverflow />
      <Line dataKey="v" type="linear" stroke="hsl(var(--brand))" strokeWidth={1.25} dot={false} isAnimationActive={false} />
    </LineChart>
  );
  return size ? chart : <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>;
}

export function RecordedWaves({ roomId, size }: { roomId: string; size?: { width: number; height: number } }) {
  const { data } = useRecordings(roomId);
  if (!data?.length) return null;
  const all = data.flatMap((r) => r.points.map((p) => p[1]));
  const low = Math.floor(Math.min(...all)) - 1, high = Math.ceil(Math.max(...all)) + 1;
  const seconds = Math.max(1, Math.ceil(Math.max(...data.map((r) => r.duration_ms)) / 1000));
  const rate = Math.round(data.reduce((a, r) => a + (r.duration_ms > 0 ? (r.packets - 1) / (r.duration_ms / 1000) : 0), 0) / data.length);
  const sources = [...new Set(data.map(sourceLine))];
  return (
    <div data-recorded-waves>
      <h4 className="text-base font-semibold">{T("rec.title")}</h4>
      <p className="text-base text-muted-foreground">{T("rec.axis")}, {T("rec.axis_time").toLowerCase()}</p>
      {data.map((r) => (
        <figure key={r.name + r.kind} className="mt-3" data-recording={r.kind}>
          <figcaption className="text-base font-medium">{kindName(r.kind)}</figcaption>
          <div className={size ? undefined : "h-[130px]"} role="img"
            aria-label={T("rec.chart_label", { what: kindName(r.kind), n: r.packets, seconds: (r.duration_ms / 1000).toFixed(0),
              min: Math.min(...r.points.map((p) => p[1])), max: Math.max(...r.points.map((p) => p[1])) })}>
            <Wave rec={r} seconds={seconds} low={low} high={high} size={size} />
          </div>
          <p className="text-base tabular-nums">{T("rec.spread", { x: r.std_db.toFixed(2), n: r.packets })}</p>
        </figure>
      ))}
      <p className="mt-3 text-base text-muted-foreground">{T("rec.caption", { rate })}</p>
      {sources.map((s) => <p key={s} className="text-base text-muted-foreground">{s}</p>)}
    </div>
  );
}

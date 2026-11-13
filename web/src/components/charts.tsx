// Charts. One rule set for every chart of the console (docs/design/PLAN.md, final review U10):
//   - tick labels sit TICK_GAP (8 px) from the plot, in 14 px muted text;
//   - ticks are even on both axes, and a second axis takes the first one's number of ticks so both sit on the grid;
//   - time labels fall on whole steps of local time and are thinned so they never touch;
//   - one legend (a swatch, then the label in the normal text colour), and none for a single series;
//   - no animation. Series use a quiet palette that never borrows the status colours (green, amber, red, grey).
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { SHOWN_MAX, dateTime, dayLabel, dayMonth, hhmm, isoDay, shown } from "@/lib/format";
import { T } from "@/lib/i18n";

export const SERIES = ["hsl(var(--brand))", "#5468A8", "#9A5C8F", "#3C7FA8", "#7A6A3A", "#4E7F5E"];

/** A card can land on a half pixel, and the drawing is then fitted to it at just under full size: a quarter pixel
 *  more keeps every word in a chart at 14 px or above on screen. */
export const CHART_TEXT_PX = 14.25;
/** The space between a tick label and the plot. */
export const TICK_GAP = 8;
export const axisText = { fontSize: CHART_TEXT_PX, fill: "hsl(var(--muted-foreground))" };
const grid = { stroke: "hsl(var(--border))", strokeDasharray: "0", vertical: false };
export const tooltipBox = { background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 14,
  color: "hsl(var(--popover-foreground))", boxShadow: "0 4px 16px -2px rgb(16 24 32 / 0.12)" };
const tooltipStyle = { contentStyle: tooltipBox, labelStyle: { color: "hsl(var(--muted-foreground))", marginBottom: 2 } };

const MYT = 8 * 3600;

/** Time ticks on whole steps of local time (10, 15 or 30 min, 1, 2, 3, 6 or 12 h, or a day), the smallest step that
 *  gives at most `most` labels between from and to: 00:00, 03:00, 06:00 rather than 00:30, 02:01, 03:33. */
export function timeTicks(from: number, to: number, most = 6): number[] {
  const steps = [600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 2 * 86400, 7 * 86400];
  const step = steps.find((s) => (to - from) / s <= most) ?? steps[steps.length - 1];
  const out: number[] = [];
  for (let t = Math.ceil((from + MYT) / step) * step - MYT; t <= to; t += step) out.push(t);
  return out;
}

/** How a time tick reads for a chart that spans `seconds`: the time within about a day, the weekday and day within
 *  about a week ("Mon 9"), else the day and month ("9 Nov"). */
export function timeLabel(seconds: number) {
  return (ts: number) => (seconds > 8 * 86400 ? dayMonth(ts) : seconds > 26 * 3600 ? dayLabel(isoDay(ts)) : hhmm(ts));
}

/** The legend of a chart with more than one series: a swatch in the series colour, then its name in the normal
 *  text colour (readable in dark mode, where coloured text was not). */
export function ChartLegend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <ul data-chart-legend className="flex flex-wrap justify-center gap-x-5 gap-y-1 pt-2 text-base text-foreground">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-2">
          <svg width="20" height="10" aria-hidden className="shrink-0">
            <line x1="0" x2="20" y1="5" y2="5" stroke={item.color} strokeWidth="2.5" strokeDasharray={item.dashed ? "5 3" : undefined} />
          </svg>
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** A dashed line across a chart with no words on it: a keyboard stop whose name ("Threshold 1.30 dB", "Capacity 30")
 *  is shown at its right end on hover or focus. */
export function HoverLine({ kind, x1, x2, y, color, width, label }: {
  kind: "threshold" | "capacity"; x1: number; x2: number; y: number; color: string; width: number; label: string;
}) {
  const [shown_, setShown] = useState(false);
  const w = label.length * 7.6 + 16;
  // the name sits above the line, or under it when the line is at the top of the plot
  const above = y - 34 >= 0;
  return (
    <g {...{ [`data-${kind}`]: true }} tabIndex={0} role="img" aria-label={label}
      className="cursor-default outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&:focus-visible>line:first-child]:[stroke-width:3.5]"
      onMouseEnter={() => setShown(true)} onMouseLeave={() => setShown(false)} onFocus={() => setShown(true)} onBlur={() => setShown(false)}>
      <line x1={x1} x2={x2} y1={y} y2={y} stroke={color} strokeWidth={width} strokeDasharray="7 5" />
      {/* a wide, invisible line to catch the pointer */}
      <line x1={x1} x2={x2} y1={y} y2={y} stroke="transparent" strokeWidth={16} />
      {shown_ && (
        <g {...{ [`data-${kind}-tip`]: true }} pointerEvents="none">
          <rect x={x2 - w - 4} y={above ? y - 34 : y + 8} width={w} height={26} rx={5} fill="hsl(var(--popover))" stroke="hsl(var(--border))" />
          <text x={x2 - 12} y={above ? y - 16 : y + 26} textAnchor="end" fontSize={CHART_TEXT_PX} fontWeight={600} fill={color}>{label}</text>
        </g>
      )}
    </g>
  );
}

/** Y axis for headcounts: 0 to 5, 0 to 25 or 0 to 100 from the highest value; anything above 100 is drawn at 100
 *  and labelled "100+". */
export function countScale(max: number) {
  if (max <= 5) return { top: 5, ticks: [0, 1, 2, 3, 4, 5] };
  if (max <= 25) return { top: 25, ticks: [0, 5, 10, 15, 20, 25] };
  return { top: 100, ticks: [0, 25, 50, 75, 100] };
}

/** Y axis for temperature: whole degrees in steps of 1, 2, 5 or 10, at least 4 °C from bottom to top (sensor noise
 *  of a tenth of a degree does not fill the chart) and always five or six ticks, so the humidity axis beside it can
 *  put 0 to 100% on the same grid lines. */
export function tempScale(values: number[]) {
  if (!values.length) return { lo: 20, hi: 30, ticks: [20, 22, 24, 26, 28, 30] };
  const min = Math.min(...values), max = Math.max(...values);
  for (const step of [1, 2, 5, 10, 20]) {
    let lo = Math.floor(min / step) * step;
    let hi = Math.ceil(max / step) * step;
    if ((hi - lo) / step > 5) continue;
    while ((hi - lo) / step < 4) { lo -= step; if ((hi - lo) / step < 4) hi += step; }
    const ticks = [];
    for (let v = lo; v <= hi; v += step) ticks.push(v);
    return { lo, hi, ticks };
  }
  return { lo: -40, hi: 60, ticks: [-40, -20, 0, 20, 40, 60] };
}

/** 0 to 100% on as many ticks as the axis beside it: 0, 25, 50, 75, 100 for five, 0, 20, ... 100 for six. */
export const percentTicks = (count: number) => (count === 6 ? [0, 20, 40, 60, 80, 100] : [0, 25, 50, 75, 100]);

/** Headcount per room over time: a smooth line through the highest count of each bucket (1 min, 15 min or 1 h).
 *  One room needs no legend: the panel's title or the table beside it already names it. */
export function OccupancyChart({ series, names, height = 240 }: {
  series: Record<string, [number, number][]>; names: Record<string, string>; height?: number;
}) {
  const ids = Object.keys(series).sort();
  const byTs = new Map<number, Record<string, number>>();
  let max = 0;
  for (const id of ids) for (const [ts, n] of series[id]) {
    const row = byTs.get(ts) ?? { ts };
    row[id] = Math.min(n, SHOWN_MAX);
    row[`${id}__raw`] = n;
    max = Math.max(max, n);
    byTs.set(ts, row);
  }
  const scale = countScale(max);
  const data = [...byTs.values()].sort((a, b) => a.ts - b.ts);
  const span = data.length ? data[data.length - 1].ts - data[0].ts : 0;
  const xTicks = data.length ? timeTicks(data[0].ts, data[data.length - 1].ts) : [];
  return (
    <div data-occupancy-chart>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="ts" type="number" domain={["dataMin", "dataMax"]} ticks={xTicks} interval="preserveStartEnd" minTickGap={16}
            tickFormatter={timeLabel(span)} tick={axisText} tickLine={false} tickMargin={TICK_GAP} axisLine={{ stroke: "hsl(var(--border))" }} />
          <YAxis domain={[0, scale.top]} ticks={scale.ticks} interval={0} allowDataOverflow tick={axisText} tickLine={false} axisLine={false} width={44}
            tickMargin={TICK_GAP} tickFormatter={(v) => (v >= SHOWN_MAX && max > SHOWN_MAX ? `${SHOWN_MAX}+` : String(v))} />
          <Tooltip {...tooltipStyle} labelFormatter={(ts) => (span > 26 * 3600 ? dateTime(Number(ts)) : hhmm(Number(ts)))}
            formatter={(v, name, item) => [shown(Number((item.payload as Record<string, number>)[`${String(name)}__raw`] ?? v)),
              names[String(name)] ?? String(name)]} />
          {ids.map((id, i) => (
            <Line key={id} dataKey={id} type="monotone" stroke={SERIES[i % SERIES.length]}
              strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} connectNulls isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {ids.length > 1 && <ChartLegend items={ids.map((id, i) => ({ label: names[id] ?? id, color: SERIES[i % SERIES.length] }))} />}
    </div>
  );
}

/** Temperature and humidity of one room: temperature on the left axis, humidity (0 to 100%) on the right, both on
 *  the same grid lines. */
export function ClimateChart({ points, height = 180 }: { points: [number, number | null, number | null][]; height?: number }) {
  const data = points.map(([ts, t, h]) => ({ ts, t, h }));
  const temps = tempScale(points.flatMap(([, t]) => (t == null ? [] : [t])));
  const span = data.length ? data[data.length - 1].ts - data[0].ts : 0;
  const xTicks = data.length ? timeTicks(data[0].ts, data[data.length - 1].ts, 5) : [];
  return (
    <div data-climate-chart>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid {...grid} />
          <XAxis dataKey="ts" type="number" domain={["dataMin", "dataMax"]} ticks={xTicks} interval="preserveStartEnd" minTickGap={16}
            tickFormatter={timeLabel(span)} tick={axisText} tickLine={false} tickMargin={TICK_GAP} axisLine={{ stroke: "hsl(var(--border))" }} />
          <YAxis yAxisId="t" domain={[temps.lo, temps.hi]} ticks={temps.ticks} interval={0} tick={axisText} tickLine={false} axisLine={false}
            width={52} tickMargin={TICK_GAP} unit="°" />
          <YAxis yAxisId="h" orientation="right" domain={[0, 100]} ticks={percentTicks(temps.ticks.length)} interval={0} tick={axisText}
            tickLine={false} axisLine={false} width={60} tickMargin={TICK_GAP} unit="%" />
          <Tooltip {...tooltipStyle} labelFormatter={(ts) => (span > 26 * 3600 ? dateTime(Number(ts)) : hhmm(Number(ts)))}
            formatter={(v, name) => [name === "t" ? `${Number(v).toFixed(1)} °C` : `${Math.round(Number(v))}%`,
              name === "t" ? T("detail.temperature") : T("detail.humidity")]} />
          <Line yAxisId="t" dataKey="t" stroke={SERIES[0]} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          <Line yAxisId="h" dataKey="h" stroke={SERIES[1]} strokeWidth={1.5} strokeDasharray="5 3" dot={false} isAnimationActive={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
      <ChartLegend items={[{ label: T("detail.temperature"), color: SERIES[0] }, { label: T("detail.humidity"), color: SERIES[1], dashed: true }]} />
    </div>
  );
}

/** Even money ticks from 0: four or five steps of 1, 2, 2.5 or 5 times a power of ten (0, 0.5, 1, 1.5 rather than
 *  0, 0.35, 0.7, 1.05). */
export function moneyTicks(max: number): number[] {
  const top = max > 0 ? max : 1;
  const raw = top / 4;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow;
  const n = Math.ceil(top / step - 1e-9);
  return Array.from({ length: n + 1 }, (_, i) => Math.round(i * step * 1000) / 1000);
}

type WasteSeries = { unit: "hour"; points: { ts: number; rm: number | null }[] } | { unit: "day"; points: { day: string; rm: number | null }[] };

/** A per-day series without the days before the first one with data (they are null: before the first report), so
 *  a new install does not show a long empty stretch. `dataFrom`: that first day when any were dropped, else null.
 *  The hours of today are left whole: a day is a day. */
export function fromFirstDay(series: WasteSeries): { series: WasteSeries; dataFrom: string | null } {
  if (series.unit !== "day") return { series, dataFrom: null };
  const first = series.points.findIndex((p) => p.rm != null);
  if (first <= 0) return { series, dataFrom: null };
  return { series: { unit: "day", points: series.points.slice(first) }, dataFrom: series.points[first].day };
}

/** RM wasted per hour of today (24 bars) or per day. A point with rm null (before the first report, or an hour
 *  still to come) has no bar. Labels every 3 hours, or thinned by day, so they never crowd. */
export function WasteOverTimeChart({ series, height = 220 }: { series: WasteSeries; height?: number }) {
  const hourly = series.unit === "hour";
  const data = series.points.map((p) => ({ key: "ts" in p ? String(p.ts) : p.day, rm: p.rm }));
  const label = (k: string) => (hourly ? hhmm(Number(k)) : dayLabel(k));
  const interval = hourly ? 2 : data.length > 20 ? 4 : data.length > 10 ? 1 : 0;
  const ticks = moneyTicks(Math.max(0, ...data.map((d) => d.rm ?? 0)));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid {...grid} />
        <XAxis dataKey="key" tickFormatter={label} interval={interval} tick={axisText} tickLine={false} tickMargin={TICK_GAP}
          axisLine={{ stroke: "hsl(var(--border))" }} />
        {/* wide enough for "RM 12.5" at 14 px: a narrower axis cut the "R" off */}
        <YAxis domain={[0, ticks[ticks.length - 1]]} ticks={ticks} interval={0} tick={axisText} tickLine={false} axisLine={false}
          tickMargin={TICK_GAP} tickFormatter={(v) => `RM ${v}`} width={72} />
        <Tooltip {...tooltipStyle} labelFormatter={(k) => label(String(k))} cursor={{ fill: "hsl(var(--muted))" }}
          formatter={(v) => [v == null ? "–" : `RM ${Number(v).toFixed(2)}`, T("energy.wasted")]} />
        <Bar dataKey="rm" fill={SERIES[0]} radius={[3, 3, 0, 0]} maxBarSize={28} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

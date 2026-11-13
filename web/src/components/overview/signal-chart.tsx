// "Live signal": the motion figure of one room's reports over the last 5 minutes against the "occupied above"
// threshold, so an audience can watch the signal rise when someone crosses the line between the boards. It lives in
// the room panel (the Overview's chart is People). One accent: the line is the brand teal; the band above the
// threshold is a neutral step of the surface, and the grid is drawn over it. 14 px text.
// While the sensor is offline nothing here is live: the line is grey, the band above the threshold is gone, and the
// chart says since when there has been no data. Minimal: no words on the threshold line and no sentence under the
// chart. The threshold is its own y-axis tick in the line's colour; hovering or focusing the line names it; the
// axis title is "dB" above the axis; the chart's aria-label carries the full meaning.
import { WifiOff } from "lucide-react";
import { Area, CartesianGrid, ComposedChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_TEXT_PX, HoverLine, TICK_GAP, axisText as axis, tooltipBox } from "@/components/charts";
import { Section } from "@/components/overview/section";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { hhmm, hhmmss } from "@/lib/format";
import { T } from "@/lib/i18n";
import { signalScale } from "@/lib/overview";
import type { Room, Signal } from "@/lib/types";

const TEXT_PX = CHART_TEXT_PX;
const HEADING = "hsl(var(--heading))";
const OFF = "hsl(var(--off))";
const BAND = "hsl(var(--muted))";

type Props = {
  room: Room | undefined;
  signal: Signal | undefined;
  loading?: boolean;
  error?: unknown;
  className?: string;
  heading?: "h2" | "h3" | "h4";
  /** fixed chart size, for tests (the chart otherwise fills its panel) */
  size?: { width: number; height: number };
};

/** The y-axis ticks: the even ticks of the scale, and the threshold as its own tick (an even tick within a quarter
 *  step of it is left out, so the two labels never overlap). */
export function signalTicks(scale: { ticks: number[]; step: number }, threshold: number | null): number[] {
  if (threshold == null || !isFinite(threshold)) return scale.ticks;
  const even = scale.ticks.filter((v) => v === 0 || Math.abs(v - threshold) >= scale.step / 4);
  return [...even, threshold].sort((a, b) => a - b);
}

function Chart({ signal, size, offline }: { signal: Signal; size?: Props["size"]; offline: boolean }) {
  const data = signal.points.map((p) => ({ ts: p.ts, v: p.motion_std }));
  const threshold = signal.threshold;
  const scale = signalScale(data.map((d) => d.v), threshold);
  const yTicks = signalTicks(scale, threshold);
  const lineColor = offline ? OFF : HEADING;
  // the threshold tick is written "1.3" in the dashed line's colour; the others are muted even numbers
  const YTick = ({ x, y, payload }: { x: number; y: number; payload: { value: number } }) => {
    const mark = threshold != null && payload.value === threshold;
    return (
      <text x={x} y={y} dy={5} textAnchor="end" fontSize={TEXT_PX} fontWeight={mark ? 600 : 400} fill={mark ? lineColor : axis.fill}
        data-threshold-tick={mark || undefined}>{mark ? payload.value.toFixed(1) : payload.value}</text>
    );
  };
  const from = signal.now - signal.minutes * 60;
  // a time label every minute on 5 minutes, every 10 minutes on an hour: never crowded
  const stepS = signal.minutes <= 5 ? 60 : 600;
  const ticks: number[] = [];
  for (let t = Math.ceil(from / stepS) * stepS; t <= signal.now; t += stepS) ticks.push(t);
  const chart = (
    <ComposedChart data={data} width={size?.width} height={size?.height} margin={{ top: 30, right: 12, bottom: 0, left: 0 }}>
      {threshold != null && !offline && <ReferenceArea y1={threshold} y2={scale.top} fill={BAND} fillOpacity={1} stroke="none" ifOverflow="hidden" />}
      <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
      <XAxis dataKey="ts" type="number" domain={[from, signal.now]} ticks={ticks} tickFormatter={hhmm} tick={axis} tickLine={false}
        tickMargin={TICK_GAP} axisLine={{ stroke: "hsl(var(--border))" }} allowDataOverflow />
      <YAxis domain={[0, scale.top]} ticks={yTicks} interval={0} tick={YTick} tickLine={false} axisLine={false} width={44} tickMargin={TICK_GAP} allowDataOverflow
        label={{ value: T("ov.signal_unit"), position: "top", offset: 16, dx: 10, style: { ...axis, textAnchor: "end" } }} />
      <Tooltip labelFormatter={(ts) => hhmmss(Number(ts))} formatter={(v) => [`${Number(v).toFixed(2)} dB`, T("ov.signal_motion")]}
        contentStyle={tooltipBox} labelStyle={{ color: "hsl(var(--muted-foreground))" }} />
      <Area dataKey="v" type="linear" stroke={offline ? OFF : "hsl(var(--brand))"} strokeWidth={offline ? 2 : 2.5}
        fill="none" fillOpacity={0}
        dot={{ r: 2.5, fill: offline ? OFF : "hsl(var(--brand))", strokeWidth: 0 }} activeDot={{ r: 4 }} isAnimationActive={false} />
      {threshold != null && (
        <ReferenceLine y={threshold} ifOverflow="hidden"
          shape={(p: { x1: number; x2: number; y1: number }) => (
            <HoverLine kind="threshold" x1={p.x1} x2={p.x2} y={p.y1} color={lineColor} width={offline ? 1.25 : 1.75}
              label={T("sig.threshold_tip", { x: threshold.toFixed(2) })} />
          )} />
      )}
    </ComposedChart>
  );
  if (size) return chart;
  return <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>;
}

export function LiveSignal({ room, signal, loading, error, className, size, heading }: Props) {
  const last = signal?.points[signal.points.length - 1];
  const threshold = signal?.threshold ?? null;
  const above = last != null && threshold != null && last.motion_std > threshold;
  const mysqlDown = error instanceof ApiError && error.status === 503;
  const offline = !!room && !room.live;
  // the last report the sensor sent: from the room's live state, or failing that the last point of the chart
  const since = offline ? room.count_ts ?? signal?.last_report_ts ?? null : null;
  // what a screen reader hears for the chart: the room, the latest value and the threshold (or why there is none)
  const chartLabel = !room ? undefined : offline && since != null
    ? T("sig.chart_offline", { name: room.name, time: hhmm(since), x: threshold != null ? threshold.toFixed(2) : "–" })
    : T(threshold == null ? "sig.chart_model" : !last ? "sig.chart_label" : above ? "sig.chart_above" : "sig.chart_below",
      { name: room.name, now: last ? last.motion_std.toFixed(2) : "–", x: threshold != null ? threshold.toFixed(2) : "–" });
  const noData = since != null && (
    <p data-signal-since className="flex items-center gap-2 text-base font-medium text-off">
      <WifiOff className="size-[1.15em] shrink-0" aria-hidden />{T("ov.signal_since", { time: hhmm(since) })}
    </p>
  );
  return (
    <Section title={T("ov.signal_title")} heading={heading} className={className} oneRow bodyClassName="flex min-h-0 flex-col px-3 pb-2 pt-1"
      action={room && (offline
        ? <span data-signal-now className="whitespace-nowrap text-off">{T("ov.signal_offline")}</span>
        : last && <span data-signal-now className="whitespace-nowrap font-semibold tabular-nums text-foreground">{T("ov.signal_now", { x: last.motion_std.toFixed(2) })}</span>)}
>
      {!room ? (
        <p className="m-auto text-base text-muted-foreground">{T("ov.signal_no_room")}</p>
      ) : !signal && mysqlDown ? (
        <p role="status" className="m-auto text-base text-warn">{T("ov.signal_mysql")}</p>
      ) : !signal && error ? (
        <p role="alert" className="m-auto text-base text-muted-foreground">{T("common.load_failed")}</p>
      ) : !signal || loading ? (
        <div className="flex flex-1 flex-col justify-center gap-2 px-2" aria-busy="true" aria-label={T("common.loading")}>
          <Skeleton className="h-4 w-11/12 animate-none" /><Skeleton className="h-4 w-9/12 animate-none" /><Skeleton className="h-4 w-10/12 animate-none" />
        </div>
      ) : (
        <>
          {signal.points.length ? (
            <div className="relative min-h-0 flex-1" data-signal-chart={offline ? "offline" : "live"} role="figure" aria-label={chartLabel}>
              <div className={size ? undefined : "absolute inset-0"}>
                <Chart signal={signal} size={size} offline={offline} />
              </div>
              {noData && (
                <div className="pointer-events-none absolute inset-0 flex items-start justify-end pr-4 pt-3">
                  <div className="rounded-md border border-dashed border-off bg-card px-3 py-1.5">{noData}</div>
                </div>
              )}
            </div>
          ) : noData ? (
            <div className="m-auto">{noData}</div>
          ) : (
            <p className="m-auto text-base text-muted-foreground">{T("ov.signal_none", { minutes: signal.minutes })}</p>
          )}
          {mysqlDown && <p className="shrink-0 px-1 pt-1 text-base text-warn">{T("ov.signal_mysql")}</p>}
        </>
      )}
    </Section>
  );
}

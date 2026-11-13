// Calibration: the state of the MindSpore model, the labelled reports of one room as dots against the threshold, and
// what is counting each room right now. The figures come from GET /api/detector and GET /api/signals; nothing here
// says a model is detecting unless the server says a model is loaded.
import { useId } from "react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, XAxis, YAxis } from "recharts";

import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { Section } from "@/components/overview/section";
import { hhmmss } from "@/lib/format";
import { LANG, T } from "@/lib/i18n";
import { signalScale, type PlanRoomRef } from "@/lib/overview";
import type { DetectorPoint, ModelFacts, Room, Signal } from "@/lib/types";
import { cn } from "@/lib/utils";

const axis = { fontSize: 14, fill: "hsl(var(--muted-foreground))" };
const HEADING = "hsl(var(--heading))";

export function modelStatus(m: ModelFacts | null): string {
  if (!m) return T("cal.model_none");
  if (m.active) return T("cal.model_active");
  return T(m.trained_on === "synthetic" ? "cal.model_inactive_synth" : "cal.model_inactive");
}

const pct = (v: number | null) => (v == null || !isFinite(v) ? "–" : `${(v * 100).toFixed(1)}%`);

function trainedOn(v: string | null): string {
  if (v === "synthetic") return T("cal.data_synthetic");
  if (v === "real CSI") return T("cal.data_real");
  return v || "–";
}

function day(ts: number | null): string {
  if (!ts) return "–";
  return new Intl.DateTimeFormat(LANG === "ms" ? "ms-MY" : "en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kuala_Lumpur" }).format(new Date(ts * 1000));
}

/** The true state of the trained model: whether it is counting, and what its file says about itself. */
export function ModelTraining({ model: m, className }: { model: ModelFacts | null; className?: string }) {
  const sim = m?.trained_on === "synthetic";  // the figures then come from simulated rows, and the labels say so
  const facts: [string, string][] = m ? [
    [T("cal.fact_framework"), m.framework || "–"], [T("cal.fact_trained_on"), trainedOn(m.trained_on)],
    [T("cal.fact_rows"), m.n_train != null ? String(m.n_train) : "–"], [T("cal.fact_trained_at"), day(m.trained_at)],
    [T(sim ? "cal.fact_accuracy_sim" : "cal.fact_accuracy"), pct(m.accuracy)],
    [T(sim ? "cal.fact_rule_accuracy_sim" : "cal.fact_rule_accuracy"), pct(m.threshold_accuracy)],
  ] : [];
  return (
    <div data-model={m ? (m.active ? "active" : "inactive") : "none"} className={className}>
      <Section title={T("cal.training_title")} bodyClassName="px-4 py-3">
        <p data-model-status className="text-base font-medium">{modelStatus(m)}</p>
        {facts.length > 0 && (
          <table className="mt-2 w-full text-base" data-model-facts>
            <tbody>
              {facts.map(([k, v]) => (
                <tr key={k} className="border-b last:border-b-0">
                  <th scope="row" className="py-1.5 pr-4 text-left font-normal text-muted-foreground">{k}</th>
                  <td className="py-1.5 text-right font-medium tabular-nums">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

export type DetectorRow = { id: string; name: string; kind: "rule" | "model" | "counter" | "none"; counting: string; threshold: string; last: string };

/** One row per room for the "Live detector" table: every room on the plan and every room that reports. What counts
 *  it (the calibrated rule, a MindSpore model only when the server says one is loaded, an exact people counter, or
 *  nothing: no sensor), its threshold or model, and its last reading from the signals answer. */
export function detectorRows(
  detector: { mode: "rule" | "model"; threshold: number | null; model: { framework: string | null } | null } | undefined,
  plan: PlanRoomRef[], rooms: Room[], signals: Record<string, Signal> | undefined, nameOf: (id: string) => string,
): DetectorRow[] {
  const byId = new Map(rooms.map((r) => [r.room_id, r]));
  const ids = [...new Set([...plan.map((p) => p.id), ...rooms.map((r) => r.room_id)])];
  const linked = new Set(plan.filter((p) => p.linked).map((p) => p.id));
  const model = detector?.mode === "model";
  return ids.map((id) => {
    const room = byId.get(id), name = nameOf(id);
    if (!room && !linked.has(id)) return { id, name, kind: "none" as const, counting: T("plan.no_sensor"), threshold: "–", last: "–" };
    if (room?.counter === "count") return { id, name, kind: "counter" as const, counting: T("cal.by_counter"), threshold: "–", last: "–" };
    const points = signals?.[id]?.points ?? [];
    const point = points[points.length - 1];
    return {
      id, name, kind: model ? "model" as const : "rule" as const, counting: T(model ? "cal.by_model" : "cal.by_rule"),
      threshold: !detector ? "–" : model ? detector.model?.framework || "–" : detector.threshold != null ? `${detector.threshold.toFixed(2)} dB` : "–",
      last: !room ? T("plan.no_report") : point ? T("cal.last_at", { x: point.motion_std.toFixed(2), time: hhmmss(point.ts) }) : "–",
    };
  }).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

/** "Live detector": what is counting each room right now, as a table across the page. */
export function LiveDetector({ rows, mode, className }: { rows: DetectorRow[]; mode: "rule" | "model" | undefined; className?: string }) {
  const list = useShowMore(rows);
  const id = useId();
  return (
    <div data-detector={mode ?? "unknown"} className={className}>
      <Section title={T("cal.live_title")} bodyClassName="p-0">
        <div id={id} className={cn(list.expanded && EXPANDED)}>
          <table className="w-full text-base" data-detector-rows>
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th scope="col" className="px-4 py-2 font-medium">{T("cal.col_room")}</th>
                <th scope="col" className="px-4 py-2 font-medium">{T("cal.col_counting")}</th>
                <th scope="col" className="px-4 py-2 font-medium">{T("cal.col_threshold")}</th>
                <th scope="col" className="px-4 py-2 font-medium">{T("cal.col_last")}</th>
              </tr>
            </thead>
            <tbody>
              {list.shown.map((r) => (
                <tr key={r.id} data-room={r.id} data-kind={r.kind} className="border-b last:border-b-0">
                  <th scope="row" className="px-4 py-2 text-left font-medium">{r.name}</th>
                  <td className={cn("px-4 py-2", r.kind === "none" && "text-off")}>{r.counting}</td>
                  <td className="px-4 py-2 tabular-nums">{r.threshold}</td>
                  <td className="px-4 py-2 tabular-nums">{r.last}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ShowMore hidden={list.hidden} expanded={list.expanded} onToggle={list.toggle} controls={id} />
        {mode && <p className="border-t px-4 py-2 text-base text-muted-foreground">{T(mode === "model" ? "cal.detector_model_hint" : "cal.detector_rule_hint")}</p>}
      </Section>
    </div>
  );
}

/** Where a dot sits across its column: spread out evenly, the same every time. */
const jitter = (i: number) => ((i * 0.618034) % 1 - 0.5) * 0.56;

function Hollow({ cx, cy }: { cx?: number; cy?: number }) {
  return <circle cx={cx} cy={cy} r={4} fill="hsl(var(--card))" stroke="hsl(var(--brand-grey))" strokeWidth={1.75} />;
}

function Solid({ cx, cy }: { cx?: number; cy?: number }) {
  return <circle cx={cx} cy={cy} r={4} fill="hsl(var(--brand))" />;
}

export function LabelledDots({ name, points, threshold, size, fill }: {
  name: string; points: DetectorPoint[]; threshold: number | null; size?: { width: number; height: number };
  /** the chart takes the height its card has left (never less than its usual height) */
  fill?: boolean;
}) {
  const empty = points.filter((p) => p.headcount_label === 0).map((p, i) => ({ x: jitter(i), y: p.motion_std }));
  const occupied = points.filter((p) => p.headcount_label > 0).map((p, i) => ({ x: 1 + jitter(i), y: p.motion_std }));
  const values = points.map((p) => p.motion_std);
  const scale = signalScale(values, threshold);
  const chart = (
    <ScatterChart width={size?.width} height={size?.height} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
      <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
      <XAxis dataKey="x" type="number" domain={[-0.5, 1.5]} ticks={[0, 1]} tick={{ ...axis, fill: "hsl(var(--foreground))" }} tickLine={false} tickMargin={8}
        axisLine={{ stroke: "hsl(var(--border))" }} tickFormatter={(v) => T(v === 0 ? "cal.dots_empty" : "cal.dots_occupied")} />
      <YAxis dataKey="y" type="number" domain={[0, scale.top]} ticks={scale.ticks} tick={axis} tickLine={false} axisLine={false} width={52}
        label={{ value: T("ov.signal_axis"), angle: -90, position: "insideLeft", offset: 12, style: { ...axis, textAnchor: "middle" } }} />
      {threshold != null && (
        <ReferenceLine y={threshold} stroke={HEADING} strokeWidth={1.75} strokeDasharray="7 5"
          label={{ value: T("cal.threshold", { x: threshold.toFixed(2) }), position: "insideBottomLeft", fontSize: 14, fontWeight: 600, fill: HEADING,
            stroke: "hsl(var(--card))", strokeWidth: 4, paintOrder: "stroke", strokeLinejoin: "round" }} />
      )}
      <Scatter data={empty} shape={<Hollow />} isAnimationActive={false} />
      <Scatter data={occupied} shape={<Solid />} isAnimationActive={false} />
    </ScatterChart>
  );
  return (
    <figure data-dots={name} className={cn(fill && "flex min-h-0 flex-1 flex-col")}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3 text-base">
        <span className="font-semibold">{name}</span>
        <span className="text-muted-foreground">{T("cal.dots_count", { empty: empty.length, occupied: occupied.length })}</span>
      </figcaption>
      <div className={size ? undefined : fill ? "relative min-h-56 flex-1" : "h-56"} role="img"
        aria-label={T("cal.dots_label", { name, empty: empty.length, occupied: occupied.length,
          min: Math.min(...values).toFixed(2), max: Math.max(...values).toFixed(2) })}>
        {size ? chart : fill ? <div className="absolute inset-0"><ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer></div>
          : <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>}
      </div>
    </figure>
  );
}

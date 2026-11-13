// "People": how many people were in one room over the last hour, 24 hours, 7 days or 30 days. Each point is the peak
// count of its stretch of time (1 min, 30 min, 3 h or a Malaysian day). A smooth line with a light fill; a stretch
// with no report is a gap, never 0, and a lone point between two gaps is drawn as a dot so it does not vanish.
// When the range is longer than the data the chart starts at the first report and says "Data from 20 Oct". A room
// with a capacity on the plan gets a dashed line at it; the scale always reaches the capacity. 14 px text, no
// animation. The same card is the Overview's chart and the first chart of the room panel.
import { ArrowUpRight, CircleDashed } from "lucide-react";
import { useId, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Area, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { HoverLine, TICK_GAP, axisText, timeTicks, tooltipBox } from "@/components/charts";
import { Section } from "@/components/overview/section";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { SHOWN_MAX, countOf, dayLabel, dayMonth, hhmm, isoDay, shown } from "@/lib/format";
import { T } from "@/lib/i18n";
import { PEOPLE_BUCKET_S, PEOPLE_MINUTES, PEOPLE_RANGES, type PeopleRange } from "@/lib/people-range";
import type { People, Room } from "@/lib/types";
import { cn } from "@/lib/utils";

const MYT = 8 * 3600;
const BRAND = "hsl(var(--brand))";
/** The fewest stretches a chart spans, so one report does not become a chart of a single point. */
const MIN_POINTS = 6;

export type PeoplePoint = { ts: number; n: number | null; raw: number | null; occupied: number | null; lone: boolean };

/** Every stretch of the range in order, with the peak or null where there was no report (a gap in the line).
 *  `dataFrom`: the first report's stretch when the range reaches back further than the data (the chart then starts
 *  there), else null. `cap`: counts above it are drawn at it. */
export function peopleSeries(data: People, minutes: number, cap = SHOWN_MAX) {
  const bucket = data.bucket_s;
  const off = MYT % bucket;
  const floor = (ts: number) => Math.floor((ts + off) / bucket) * bucket - off;
  const start = floor(data.now - minutes * 60);
  const end = floor(data.now);
  const first = data.people.length ? data.people[0][0] : null;
  let from = start;
  if (first != null && first - start > bucket) from = Math.max(start, Math.min(first, end - (MIN_POINTS - 1) * bucket));
  const dataFrom = first != null && from > start ? first : null;
  const byTs = new Map(data.people.map(([ts, peak, occupied]) => [ts, { peak, occupied }]));
  const points: PeoplePoint[] = [];
  for (let ts = from; ts <= end; ts += bucket) {
    const hit = byTs.get(ts);
    points.push({ ts, n: hit ? Math.min(hit.peak, cap) : null, raw: hit?.peak ?? null, occupied: hit?.occupied ?? null, lone: false });
  }
  points.forEach((p, i) => { p.lone = p.n != null && points[i - 1]?.n == null && points[i + 1]?.n == null; });
  return { points, from, end, dataFrom, max: Math.max(0, ...data.people.map(([, peak]) => peak)) };
}

/** Whole-number y ticks from 0: at most five even steps up to the highest count or the capacity (at least 2). */
export function peopleTicks(max: number) {
  const top = Math.max(2, Math.ceil(max));
  const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find((s) => top / s <= 5) ?? 500;
  const end = Math.ceil(top / step) * step;
  return Array.from({ length: end / step + 1 }, (_, i) => i * step);
}

/** "06:52" today, "12 Nov, 06:52" on another day. */
export const sinceText = (ts: number, now: number) => (isoDay(ts) === isoDay(now) ? hhmm(ts) : `${dayMonth(ts)}, ${hhmm(ts)}`);

/** "45 min", "2 h 5 min". */
export const occupiedText = (minutes: number) =>
  (minutes < 60 ? T("ppl.minutes", { n: minutes }) : T("ppl.hours_minutes", { h: Math.floor(minutes / 60), m: minutes % 60 }));

/** The time a point stands for: a minute, a stretch within a day ("Mon 9, 06:00 to 09:00"), or a day. */
function pointTime(ts: number, bucket: number, range: PeopleRange) {
  if (bucket >= 86400) return dayMonth(ts);
  if (bucket <= 60) return hhmm(ts);
  const span = T("ppl.span", { from: hhmm(ts), to: hhmm(ts + bucket) });
  return range === "24h" ? span : `${dayLabel(isoDay(ts))}, ${span}`;
}

function Tip({ active, payload, bucket, range, capacity }: {
  active?: boolean; payload?: { payload: PeoplePoint }[]; bucket: number; range: PeopleRange; capacity: number | null;
}) {
  const p = active ? payload?.[0]?.payload : undefined;
  if (!p || p.raw == null) return null;
  return (
    <div data-people-tip style={tooltipBox} className="px-2.5 py-1.5 text-base">
      <p className="text-muted-foreground">{pointTime(p.ts, bucket, range)}</p>
      <p><span className="text-muted-foreground">{T("ppl.peak")} </span>
        <span className="font-semibold tabular-nums">{capacity ? T("ppl.of_capacity", { n: shown(p.raw), cap: capacity }) : shown(p.raw)}</span></p>
      {bucket > 60 && p.occupied != null && (
        <p><span className="text-muted-foreground">{T("ppl.occupied")} </span><span className="font-semibold tabular-nums">{occupiedText(p.occupied)}</span></p>
      )}
    </div>
  );
}

export function PeopleChart({ data, range, capacity = null, size }: {
  data: People; range: PeopleRange; capacity?: number | null;
  /** fixed size, for tests (the chart otherwise fills its panel) */
  size?: { width: number; height: number };
}) {
  const cap = Math.max(SHOWN_MAX, capacity ?? 0);
  const { points, from, end, max } = peopleSeries(data, PEOPLE_MINUTES[range], cap);
  const bucket = data.bucket_s;
  const ticks = peopleTicks(Math.max(Math.min(max, cap), capacity ?? 0));
  const top = ticks[ticks.length - 1];
  const xTicks = timeTicks(from, end, 8);
  const fmt = (ts: number) => (range === "30d" ? dayMonth(ts) : range === "7d" ? dayLabel(isoDay(ts)) : hhmm(ts));
  // a lone point between two gaps: a line needs two points, so it gets a dot
  const Dot = ({ cx, cy, payload }: { cx?: number; cy?: number; payload?: PeoplePoint }) =>
    (payload?.lone && cx != null && cy != null ? <circle data-lone-point cx={cx} cy={cy} r={3} fill={BRAND} /> : <g />);
  const chart = (
    <ComposedChart data={points} width={size?.width} height={size?.height} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
      <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
      <XAxis dataKey="ts" type="number" domain={[from, end]} ticks={xTicks} interval="preserveStartEnd" minTickGap={16} tickFormatter={fmt}
        tick={axisText} tickLine={false} tickMargin={TICK_GAP} axisLine={{ stroke: "hsl(var(--border))" }} allowDataOverflow />
      <YAxis domain={[0, top]} ticks={ticks} interval={0} allowDecimals={false} tick={axisText} tickLine={false} axisLine={false} width={44}
        tickMargin={TICK_GAP} tickFormatter={(v) => (v === top && max > cap ? `${cap}+` : String(v))} />
      <Tooltip content={<Tip bucket={bucket} range={range} capacity={capacity} />} cursor={{ stroke: "hsl(var(--border))" }} />
      <Area dataKey="n" type="monotone" stroke={BRAND} strokeWidth={2.25} fill={BRAND} fillOpacity={0.12} dot={Dot}
        activeDot={{ r: 4, strokeWidth: 0, fill: BRAND }} connectNulls={false} isAnimationActive={false} />
      {capacity != null && (
        <ReferenceLine y={capacity} ifOverflow="extendDomain"
          shape={(p: { x1: number; x2: number; y1: number }) => (
            <HoverLine kind="capacity" x1={p.x1} x2={p.x2} y={p.y1} color="hsl(var(--muted-foreground))" width={1.5}
              label={T("ppl.capacity_tip", { n: capacity })} />
          )} />
      )}
    </ComposedChart>
  );
  if (size) return chart;
  return <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>;
}

/** The range control: a row of buttons on a wide screen, a compact select below 1536 px, so the header never takes
 *  two rows. On a wide screen the buttons also give way to the select when they would not fit in the card's header
 *  (a narrow card, or longer Malay labels); they come back once the header is as wide as it was when they last
 *  fitted. `compact`: always the select (the room panel). */
export function RangeControl({ range, onRange, compact }: { range: PeopleRange; onRange: (r: PeopleRange) => void; compact?: boolean }) {
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  const [crowded, setCrowded] = useState<number | null>(null);  // header width the buttons needed, when they did not fit
  useLayoutEffect(() => {
    const header = ref.current?.closest("header");
    if (!header || compact) return;
    const check = () => setCrowded((need) => {
      if (need == null) return header.scrollWidth > header.clientWidth + 1 ? header.scrollWidth : null;
      return header.clientWidth >= need ? null : need;
    });
    check();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(check);
    ro.observe(header);
    return () => ro.disconnect();
  }, [compact]);
  const buttons = !compact && crowded == null;
  return (
    <>
      <span ref={ref} hidden />
      <div role="radiogroup" aria-label={T("sig.range")} className={cn("hidden shrink-0 overflow-hidden rounded-md border", buttons && "2xl:flex")} data-people-range>
        {PEOPLE_RANGES.map((r) => (
          <button key={r} type="button" role="radio" aria-checked={range === r} onClick={() => onRange(r)}
            className={cn("h-8 whitespace-nowrap border-r px-2.5 text-base last:border-r-0",
              range === r ? "bg-primary-soft font-medium text-primary" : "text-foreground hover:bg-accent")}>{T(`sig.range_${r}`)}</button>
        ))}
      </div>
      <label htmlFor={id} className="sr-only">{T("sig.range")}</label>
      <select id={id} value={range} onChange={(e) => onRange(e.target.value as PeopleRange)} data-people-range-select
        className={cn("h-8 shrink-0 rounded-md border border-input bg-background px-2 text-base font-medium text-foreground", buttons && "2xl:hidden")}>
        {PEOPLE_RANGES.map((r) => <option key={r} value={r}>{T(`sig.range_${r}`)}</option>)}
      </select>
    </>
  );
}

/** "since 06:52": only while the live count agrees with the state the history saw, so it never sits beside the
 *  wrong count (a room that filled a second ago still has "empty since" in the stored reports). */
export function sinceOf(room: Room | undefined, people: People | undefined): number | null {
  const since = people?.since;
  if (!room || !room.live || room.headcount == null || !since || since.ts == null || people.room_id !== room.room_id) return null;
  return (room.headcount > 0) === since.occupied ? since.ts : null;
}

const NONE = {
  no_sensor: { title: "sig.none_here", hint: "sig.no_sensor_hint" },
  no_report: { title: "sig.not_yet", hint: "sig.no_report_hint" },
} as const;

type CardProps = {
  room: Room | undefined;
  people: People | undefined;
  loading?: boolean;
  error?: unknown;
  range: PeopleRange;
  onRange: (r: PeopleRange) => void;
  /** the room's capacity on the plan, when one is set */
  capacity?: number | null;
  /** the rooms the viewer may choose from, and the one chosen: the card then carries a room select in its title row */
  rooms?: { id: string; name: string }[];
  selected?: string | null;
  onSelect?: (roomId: string) => void;
  /** the chosen room has no count to draw: no sensor, or a sensor pair that has not reported yet. The card says so
   *  in words and draws no chart. */
  none?: keyof typeof NONE | null;
  /** where "Room details" leads (the Overview passes the room panel; inside that panel there is no link) */
  roomLink?: string;
  /** the room panel: the count and "since" are in its own header, and the range is always the compact select */
  panel?: boolean;
  heading?: "h2" | "h3" | "h4";
  className?: string;
  size?: { width: number; height: number };
};

export function PeopleCard({ room, people, loading, error, range, onRange, capacity = null, rooms, selected, onSelect, none, roomLink, panel, heading, className, size }: CardProps) {
  const selectId = useId();
  // an answer for another room or another range (still on screen while the new one loads) is not this chart's
  const mine = people && room && people.room_id === room.room_id && people.bucket_s === PEOPLE_BUCKET_S[range] ? people : undefined;
  const mysqlDown = error instanceof ApiError && error.status === 503;
  const since = sinceOf(room, mine);
  const series = mine ? peopleSeries(mine, PEOPLE_MINUTES[range]) : null;
  const dataFrom = series?.dataFrom ?? null;
  const longRange = T(`sig.range_long_${range}`);
  return (
    <Section title={T("sig.people_title")} heading={heading} className={className} oneRow bodyClassName="flex min-h-0 flex-col px-3 pb-2 pt-1"
      // one row: the room and its count on the left, the range and the link on the right; nothing here wraps
      action={(
        <span className="flex min-w-0 flex-nowrap items-center gap-x-3">
          {!!rooms?.length && onSelect && (
            <>
              <label htmlFor={selectId} className="sr-only">{T("sig.room")}</label>
              <select id={selectId} name="people-room" data-people-room value={selected ?? ""} onChange={(e) => onSelect(e.target.value)} title={room?.name}
                className="h-8 min-w-0 max-w-48 shrink rounded-md border border-input bg-background px-2 text-base font-medium text-foreground">
                {!selected && <option value="" disabled>{T("sig.room")}</option>}
                {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </>
          )}
          {room && !none && !panel && (!room.live
            ? <span data-people-now className="whitespace-nowrap text-off">{T("ov.signal_offline")}</span>
            : (
              <span data-people-now className="whitespace-nowrap text-muted-foreground">
                <span className="font-semibold tabular-nums text-foreground">{T("ppl.now", { count: countOf(room) })}</span>
                {since != null && <span data-people-since> · {T("ppl.since", { time: sinceText(since, mine!.now) })}</span>}
              </span>
            ))}
        </span>
      )}
      aside={(
        <>
          <RangeControl range={range} onRange={onRange} compact={panel} />
          {roomLink && (
            <Link to={roomLink} data-room-details className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap font-medium text-foreground underline underline-offset-2 hover:text-heading">
              {T("ppl.details")}<ArrowUpRight className="size-[1.1em]" aria-hidden />
            </Link>
          )}
        </>
      )}>
      {none ? (
        // never an empty chart: the card says in words why there is no count for this room
        <div data-people-none={none} className="m-auto flex max-w-md flex-col items-center gap-1.5 rounded-md border border-dashed border-off px-5 py-4 text-center">
          <p className="flex items-center gap-2 text-md font-semibold text-off"><CircleDashed className="size-5 shrink-0" aria-hidden />{T(NONE[none].title)}</p>
          <p className="text-base text-muted-foreground">{T(NONE[none].hint)}</p>
        </div>
      ) : !room ? (
        <p className="m-auto text-base text-muted-foreground">{T("ppl.no_room")}</p>
      ) : !mine && mysqlDown ? (
        <p role="status" className="m-auto text-base text-warn">{T("ov.signal_mysql")}</p>
      ) : !mine && error ? (
        <p role="alert" className="m-auto text-base text-muted-foreground">{T("common.load_failed")}</p>
      ) : !mine || loading ? (
        <div className="flex flex-1 flex-col justify-center gap-2 px-2" aria-busy="true" aria-label={T("common.loading")}>
          <Skeleton className="h-4 w-11/12 animate-none" /><Skeleton className="h-4 w-9/12 animate-none" /><Skeleton className="h-4 w-10/12 animate-none" />
        </div>
      ) : !mine.people.length ? (
        <p data-people-empty className="m-auto text-base text-muted-foreground">{T("ppl.none", { range: longRange })}</p>
      ) : (
        <>
          {/* the range reaches back further than the data: the chart starts at the first report and says so. A line
              of its own, because the header's one row has no room for it on a narrow card */}
          {dataFrom != null && (
            <p data-data-from className="shrink-0 px-1 text-right text-base text-muted-foreground">
              {T("chart.data_from", { date: isoDay(dataFrom) === isoDay(mine.now) ? hhmm(dataFrom) : dayMonth(dataFrom) })}</p>
          )}
          <div className="relative min-h-0 flex-1" data-people-chart={range} role="figure"
            aria-label={T("ppl.label", { name: room.name, range: longRange, max: shown(series!.max) })
              + (capacity ? ` ${T("ppl.label_capacity", { cap: capacity })}` : "")}>
            <div className={size ? undefined : "absolute inset-0"}>
              <PeopleChart data={mine} range={range} capacity={capacity} size={size} />
            </div>
          </div>
          {mysqlDown && <p className="shrink-0 px-1 pt-1 text-base text-warn">{T("ov.signal_mysql")}</p>}
        </>
      )}
    </Section>
  );
}


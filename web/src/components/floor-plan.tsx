// The floor plan as an architectural drawing: thin walls, door swings, stairwells, rooms filled softly by status.
// Normal mode: click or Enter on a room opens its details; a room's status is written under its count, never told by
// the fill alone. Emergency mode: occupied rooms in red with their place in the rescue order and "Nearest exit:
// Stair B" written on them. No route is drawn: the plan knows which exit is nearest, not the way a person would walk.
import { useId, useRef } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ago, countOf, peopleWord, shown, statusOf, temp, type RoomStatus } from "@/lib/format";
import { T } from "@/lib/i18n";
import { corridorMid, doorPoint, hasDoor, labelOf, type Box, type Door, type Plan } from "@/lib/plan";
import { useExitName, usePlan } from "@/lib/site";
import { MIN_PX, useSvgScale } from "@/lib/svg-scale";
import type { Room } from "@/lib/types";
import { cn } from "@/lib/utils";

const FILL: Record<RoomStatus, string> = {
  ok: "fill-ok/15 stroke-ok",
  empty: "fill-plan-floor stroke-plan-wall",
  waste: "fill-warn/15 stroke-warn",
  off: "stroke-off",
};

type Props = {
  rooms: Room[];
  now: number;
  emergency?: boolean;
  /** rooms in rescue order (emergency mode) */
  ranked?: Room[];
  selected?: string | null;
  onSelect?: (roomId: string) => void;
  compact?: boolean;
  className?: string;
  /** the plan to draw (default: the floor being shown) */
  plan?: Plan;
};

function DoorSwing({ o }: { o: Box & { door: Door } }) {
  const d = doorPoint(o), w = 36;
  const leaf = d.y + d.dir * (w - 4);
  return (
    <g className="pointer-events-none">
      <line x1={d.x} y1={d.y} x2={d.x + w} y2={d.y} className="stroke-plan-floor" strokeWidth={4} />
      <path d={`M${d.x},${d.y} L${d.x},${leaf} A${w - 4},${w - 4} 0 0 ${d.dir > 0 ? 0 : 1} ${d.x + w - 4},${d.y}`}
        className="fill-none stroke-plan-wall" strokeWidth={1} />
    </g>
  );
}

export function FloorPlan({ rooms, now, emergency, ranked = [], selected, onSelect, compact, className, plan: given }: Props) {
  const hatch = useId().replace(/:/g, "");
  const current = usePlan();
  const exitFor = useExitName();
  const PLAN = given ?? current;
  const byId = Object.fromEntries(rooms.map((r) => [r.room_id, r]));
  const [x0, y0, w0, h0] = PLAN.viewBox;
  const o = PLAN.outline, c = PLAN.corridor;
  const corridorY = corridorMid(PLAN);
  const svgRef = useRef<SVGSVGElement>(null);
  const scale = useSvgScale(svgRef, w0);  // drawn text never below 14 px on screen
  const least = MIN_PX / scale;  // 14.25 px on screen, in drawing units
  const k = compact ? 1.7 : 1;  // the compact plan is drawn small: scale its text up to stay readable
  const fs = (px: number) => ({ fontSize: Math.max(px * k, least) });
  // a label inside a narrow space (a stairwell): no wider than the space less a margin ("Tangga A" is longer than
  // "Stair A"); about 0.6 em per character for this font; never below 14 px on screen
  const fit = (px: number, text: string, width: number) => ({ fontSize: Math.max(least, Math.min(px * k, (width - 14) / (0.6 * text.length))) });
  const sign = Math.max(1, least / 14);  // the exit sign and the rescue numbers grow with their text

  return (
    <svg ref={svgRef} viewBox={`${x0} ${y0} ${w0} ${h0}`} className={cn("h-auto w-full select-none", className)} role="group"
      aria-label={T(emergency ? "plan.em_label" : "plan.label")}>
      <defs>
        <pattern id={hatch} width={10} height={10} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width={10} height={10} className="fill-plan-floor" />
          <line x1={0} y1={0} x2={0} y2={10} className="stroke-plan-line" strokeWidth={3} />
        </pattern>
      </defs>
      <rect x={o.x} y={o.y} width={o.w} height={o.h} className="fill-plan-floor stroke-plan-wall" strokeWidth={2.5} />
      {c && <rect x={c.x} y={c.y} width={c.w} height={c.h} className="fill-muted/60" />}
      {c && <text x={c.x + c.w * 0.62} y={corridorY + 5 * k} textAnchor="middle" className="fill-muted-foreground" style={fs(13)}>{T("plan.corridor")}</text>}

      {PLAN.other.map((s, i) => (
        <g key={`${i}-${labelOf(s)}`}>
          <rect x={s.x} y={s.y} width={s.w} height={s.h} className="fill-plan-floor stroke-plan-line" strokeWidth={1} />
          <text x={s.x + s.w / 2} y={s.y + s.h / 2 + 5 * k} textAnchor="middle" className="fill-muted-foreground" style={fs(13)}>{labelOf(s)}</text>
        </g>
      ))}

      {Object.entries(PLAN.exits).map(([id, ex]) => (
        <g key={id}>
          <rect x={ex.x} y={ex.y} width={ex.w} height={ex.h} className="fill-plan-floor stroke-plan-wall" strokeWidth={1.5} />
          {Array.from({ length: Math.floor((ex.h - 70) / 16) }, (_, i) => (
            <line key={i} x1={ex.x + 14} x2={ex.x + ex.w - 14} y1={ex.y + 60 + i * 16} y2={ex.y + 60 + i * 16}
              className="stroke-plan-line" strokeWidth={1} />
          ))}
          <rect x={ex.x + ex.w / 2 - 33 * sign} y={ex.y + 8} width={66 * sign} height={22 * sign} rx={2} className="fill-ok" />
          <text x={ex.x + ex.w / 2} y={ex.y + 8 + 16 * sign} textAnchor="middle" className="fill-white font-semibold" style={{ fontSize: 14 * sign }}>{T("plan.exit_sign")}</text>
          <text x={ex.x + ex.w / 2} y={ex.y + 22 * sign + 22 + 6 * k * sign} textAnchor="middle" className="fill-foreground font-medium" style={fit(13, labelOf(ex), ex.w)}>{labelOf(ex)}</text>
          {hasDoor(ex) && <DoorSwing o={ex} />}
        </g>
      ))}

      {Object.entries(PLAN.rooms).map(([id, box]) => {
        const r = byId[id];
        const st = statusOf(r);
        const hot = emergency && r && (!r.live || (r.headcount ?? 0) > 0);  // unknown counts as "check this room"
        const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
        const name = r?.name ?? box.name ?? id;  // no report yet: the name written on the plan, as on the overview
        // never reported: "No sensor", or "No report yet" when a sensor pair is drawn for the room
        const none = T(box.link ? "plan.no_report" : "plan.no_sensor");
        const sub = !r ? none
          : !r.live ? (r.headcount != null && r.count_ts
            ? T("count.last_short", { count: shown(r.headcount, r.at_least) }) : T("count.unknown_short"))
          : emergency ? (r.headcount ? T("plan.em_people", { count: shown(r.headcount, r.at_least), people: peopleWord(r.at_least ? 2 : r.headcount) }) : T("plan.em_none"))
          : r.waste ? T("plan.waste_sub", { minutes: r.waste.minutes })
          // the status in words, then the temperature when there is one: "Occupied · 24.1 °C"
          : r.temp_c != null ? `${T(`status.${st}`)} · ${temp(r.temp_c)}` : T(`status.${st}`);
        // emergency: the nearest exit by name on every room to check; on two lines when one would not fit the room
        const exit = emergency && hot ? exitFor(id) : null;
        const exitLine = exit ? T("detail.nearest_exit_is", { exit }) : "";
        const f13 = fs(13).fontSize;
        const oneLine = (box.w - 14) / (0.6 * exitLine.length) >= f13;
        const up = exit ? (oneLine ? 12 : 22) : 0;  // the room's text moves up to make room for the exit
        const subY = cy + 30 + Math.max(12, f13) - up;
        const label = !r ? T(box.link ? "plan.room_no_report" : "plan.room_no_sensor", { name })
          : !r.live ? T("plan.room_unknown", { name, status: T(`status.${st}`) })
          : T("plan.room_label", { name, count: shown(r.headcount, r.at_least), people: peopleWord(r.headcount), status: T(`status.${st}`) });
        const interactive = !emergency && onSelect;
        const room = (
          <g role={interactive ? "button" : "img"} tabIndex={interactive ? 0 : undefined} aria-label={label}
            className={cn(interactive && "cursor-pointer outline-none [&:focus-visible>rect:first-child]:stroke-ring [&:focus-visible>rect:first-child]:[stroke-width:3]")}
            onClick={interactive ? () => onSelect(id) : undefined}
            onKeyDown={interactive ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(id); } } : undefined}>
            <rect x={box.x} y={box.y} width={box.w} height={box.h} strokeWidth={selected === id ? 3 : 1.5}
              fill={st === "off" ? `url(#${hatch})` : undefined}
              strokeDasharray={st === "off" ? "6 4" : undefined}
              className={cn(hot ? "fill-crit/20 stroke-crit" : FILL[st], selected === id && "stroke-primary")} />
            <text x={cx} y={cy - 30 - up} textAnchor="middle" className="fill-foreground font-semibold" style={fs(15)}>{name}</text>
            <text x={cx} y={cy + (compact ? 26 : 14) - up} textAnchor="middle" style={{ fontSize: compact ? 44 : 30 }}
              className={cn("font-semibold", hot ? "fill-crit" : st === "waste" ? "fill-warn" : st === "off" ? "fill-off" : "fill-foreground")}>
              {countOf(r)}
            </text>
            {!compact && <text data-room-sub x={cx} y={subY} textAnchor="middle" className="fill-muted-foreground" style={fs(13)}>{sub}</text>}
            {exit && !compact && (oneLine ? (
              <text data-room-exit x={cx} y={subY + f13 * 1.4} textAnchor="middle" className="fill-foreground font-semibold" style={fs(13)}>{exitLine}</text>
            ) : (
              <text data-room-exit x={cx} y={subY + f13 * 1.4} textAnchor="middle" className="fill-foreground font-semibold" style={fs(13)}>
                <tspan x={cx} className="font-normal">{T("detail.nearest_exit")}:</tspan>
                <tspan x={cx} dy={f13 * 1.25}>{exit}</tspan>
              </text>
            ))}
            {r?.counter === "count" && !emergency && (
              <text x={cx} y={cy + (compact ? 62 : 64)} textAnchor="middle" className="fill-muted-foreground" style={fs(11)}>
                {T("room.sim_counter")}
              </text>
            )}
          </g>
        );
        return (
          <g key={id}>
            {interactive ? (
              <Tooltip delayDuration={150}>
                <TooltipTrigger asChild>{room}</TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  <p className="font-semibold">{name}</p>
                  {r ? (
                    <>
                      <p>{r.live ? `${countOf(r)} ${peopleWord(r.headcount)}, ${T(`status.${st}`)}` : sub}</p>
                      <p>{temp(r.temp_c)}{r.humidity != null ? `, ${Math.round(r.humidity)}% RH` : ""}</p>
                      <p className="text-muted-foreground">{T("detail.last_update")}: {ago(r.count_ts ? now - r.count_ts : null)}</p>
                      <p className="text-muted-foreground">{T("detail.nearest_exit")}: {exitFor(id) ?? "–"}</p>
                    </>
                  ) : <p>{none}</p>}
                </TooltipContent>
              </Tooltip>
            ) : room}
            {hasDoor(box) && <DoorSwing o={box} />}
          </g>
        );
      })}

      {/* the place in the rescue order, on each room to check */}
      {emergency && ranked.map((r, i) => {
        const room = PLAN.rooms[r.room_id];
        if (!room) return null;  // on another floor
        return (
          <g key={r.room_id} className="pointer-events-none" data-rescue-rank={i + 1}>
            <circle cx={room.x + 26 * sign} cy={room.y + 26 * sign} r={15 * sign} className="fill-crit" />
            <text x={room.x + 26 * sign} y={room.y + 26 * sign + 5 * sign} textAnchor="middle" className="fill-white font-bold" style={{ fontSize: 14 * sign }}>{i + 1}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function PlanLegend() {
  const items: [string, string][] = [
    ["legend.ok", "bg-ok/20 border-ok"], ["legend.empty", "bg-card border-plan-wall"],
    ["legend.waste", "bg-warn/20 border-warn"], ["legend.off", "border-dashed border-off"],
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map(([k, cls]) => (
        <li key={k} className="flex items-center gap-1.5"><span className={cn("size-3 rounded-[2px] border", cls)} aria-hidden />{T(k)}</li>
      ))}
    </ul>
  );
}

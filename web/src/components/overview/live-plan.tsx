// The overview's live floor plan. The drawing (walls, doors, stairs) is an SVG; names, counts and status words sit on
// top as ordinary text so they never go below 14 px, whatever size the plan is drawn at. A tile shows the room name,
// the count, the status and a small signal trace; the sensor pair is drawn in the room panel and the editor, not here.
// A room with a sensor shows its count, a status word with an icon, and a small signal trace. A room on the plan
// with no sensor shows "–" and "No sensor" in a quiet dashed style (deliberate, not broken); "?" is only for a
// sensor that stopped reporting.
// What moves, and only when new data arrives: the count rolls and the tile's ring fades once.
// A click (or Enter, or Space) selects a room: the tile gets a purple ring and a corner tab with a tick, and the live
// signal card follows. A double-click opens the room. The signals of all rooms arrive together (GET /api/signals),
// so no tile makes a request of its own.
import { Check, CircleDashed, Snowflake, UserRound, Users, WifiOff } from "lucide-react";
import { useId } from "react";

import { NumberTicker } from "@/components/magicui/number-ticker";
import { peopleWord, shown, statusOf, type RoomStatus } from "@/lib/format";
import { T } from "@/lib/i18n";
import { useNewer } from "@/lib/motion";
import { signalScale } from "@/lib/overview";
import { BUILTIN_PLAN, doorPoint, hasDoor, labelOf, type Box, type Door, type Plan, type PlanLink } from "@/lib/plan";
import { usePlan } from "@/lib/site";
import type { Room, Signal } from "@/lib/types";
import { cn } from "@/lib/utils";

type TileStatus = RoomStatus | "none";

const RECT: Record<TileStatus, string> = {
  ok: "fill-ok/15 stroke-ok",
  empty: "fill-plan-floor stroke-plan-wall",
  waste: "fill-warn/15 stroke-warn",
  off: "stroke-off",
  none: "fill-muted/40 stroke-off",
};
const WORD: Record<TileStatus, { icon: typeof Users; key: string; cls: string }> = {
  ok: { icon: Users, key: "status.ok", cls: "text-ok" },
  empty: { icon: UserRound, key: "status.empty", cls: "text-muted-foreground" },
  waste: { icon: Snowflake, key: "status.waste", cls: "text-warn" },
  off: { icon: WifiOff, key: "status.off", cls: "text-off" },
  none: { icon: CircleDashed, key: "plan.no_sensor", cls: "text-off" },
};
/** A room that never reported: "No sensor", or "No report yet" when a sensor pair is drawn for it on the plan. */
const noneKey = (box: { link?: unknown }) => (box.link ? "plan.no_report" : "plan.no_sensor");

const [X0, Y0, W0, H0] = BUILTIN_PLAN.viewBox;  // every plan is drawn in the same 1000 x 560 box (the server checks it)
const pct = (v: number, of: number) => `${(v / of) * 100}%`;
const place = (b: Box): React.CSSProperties => ({ left: pct(b.x - X0, W0), top: pct(b.y - Y0, H0), width: pct(b.w, W0), height: pct(b.h, H0) });

function DoorSwing({ o }: { o: Box & { door: Door } }) {
  const d = doorPoint(o), w = 36;
  const leaf = d.y + d.dir * (w - 4);
  return (
    <g>
      <line x1={d.x} y1={d.y} x2={d.x + w} y2={d.y} className="stroke-plan-floor" strokeWidth={4} />
      <path d={`M${d.x},${d.y} L${d.x},${leaf} A${w - 4},${w - 4} 0 0 ${d.dir > 0 ? 0 : 1} ${d.x + w - 4},${d.y}`}
        className="fill-none stroke-plan-wall" strokeWidth={1} />
    </g>
  );
}

function Trace({ signal }: { signal: Signal }) {
  const pts = signal.points;
  if (pts.length < 2) return null;
  const from = signal.now - signal.minutes * 60, width = Math.max(1, signal.now - from);
  const top = signalScale(pts.map((p) => p.motion_std), signal.threshold).top;
  const y = (v: number) => 23 - (Math.min(Math.max(v, 0), top) / top) * 22;
  const line = pts.map((p) => `${(Math.max(0, p.ts - from) / width) * 100},${y(p.motion_std).toFixed(2)}`).join(" ");
  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden className="plan-spark h-5 w-3/5 max-w-40 shrink-0 overflow-visible">
      {signal.threshold != null && (
        <line x1={0} x2={100} y1={y(signal.threshold)} y2={y(signal.threshold)} stroke="hsl(var(--heading))" strokeOpacity={0.55}
          strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
      )}
      <polyline points={line} fill="none" stroke="hsl(var(--brand))" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
        vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function RoomTile({ id, box, room, name, still, signal, selected, onSelect, onOpen }: {
  id: string; box: Box & { link?: PlanLink }; room: Room | undefined; name: string; still: boolean; signal: Signal | undefined;
  selected?: boolean; onSelect?: (id: string) => void; onOpen?: (id: string) => void;
}) {
  const reports = useNewer(room?.live ? room.count_ts : null);
  const status: TileStatus = room ? statusOf(room) : "none";
  const { icon: Icon, cls } = WORD[status];
  const key = status === "none" ? noneKey(box) : WORD[status].key;
  const counted = !!room && room.live && room.headcount != null;
  const label = !room ? T(box.link ? "plan.room_no_report" : "plan.room_no_sensor", { name })
    : !room.live ? T("plan.room_unknown", { name, status: T("status.off") })
    : T("plan.room_label", { name, count: shown(room.headcount, room.at_least), people: peopleWord(room.headcount), status: T(`status.${statusOf(room)}`) });
  const body = (
    <>
      {/* over the hatching of an offline room the words get a plain backing */}
      <span className={cn("flex max-w-full flex-col items-center gap-[0.35em]", status === "off" && "rounded-md bg-plan-floor/90 px-3 py-1.5")}>
        <span className="plan-name max-w-full truncate font-semibold">{name}</span>
      <span className={cn("plan-count font-semibold tabular-nums", status === "waste" ? "text-warn" : !counted ? "text-off" : "text-foreground")}>
        {counted
          ? <NumberTicker value={room.headcount ?? 0} still={still} format={(n) => shown(n, room.at_least)} />
          : <span aria-hidden>{room ? "?" : "–"}</span>}
      </span>
      <span className={cn("plan-word flex max-w-full items-center gap-1.5 font-medium", cls)}>
        <Icon className="size-[1.1em] shrink-0" aria-hidden /><span className="whitespace-nowrap">{T(key)}</span>
      </span>
      </span>
      {room?.counter === "count" && (
        <span className="plan-minor max-w-full truncate rounded-sm border border-dashed px-1.5 text-base text-muted-foreground">{T("room.sim_counter")}</span>
      )}
      {signal && room?.live && room.counter !== "count" && <Trace signal={signal} />}
      {selected && (
        // selected: a ring and a corner tab with a tick, so it is a shape as well as a colour
        <>
          <span aria-hidden className="pointer-events-none absolute inset-0 rounded-sm ring-[3px] ring-inset ring-primary" />
          <span aria-hidden data-selected-tab className="pointer-events-none absolute left-0 top-0 flex size-6 items-center justify-center rounded-br-md bg-primary text-primary-foreground">
            <Check className="size-4" strokeWidth={3} />
          </span>
        </>
      )}
      {!still && reports > 0 && <span key={reports} aria-hidden className="report-pulse pointer-events-none absolute inset-0 rounded-sm ring-4 ring-inset ring-brand" />}
    </>
  );
  const cls2 = "absolute flex flex-col items-center justify-center gap-[3%] overflow-hidden px-[1.5%] py-[1%] text-center";
  if (!onSelect) {
    return <div role="img" aria-label={label} data-room={id} data-status={status} className={cls2} style={place(box)}>{body}</div>;
  }
  return (
    <button type="button" aria-label={label} aria-pressed={!!selected} data-room={id} data-status={status} data-selected={selected || undefined}
      style={place(box)} onClick={() => onSelect(id)} onDoubleClick={onOpen ? () => onOpen(id) : undefined}
      className={cn(cls2, "cursor-pointer rounded-sm outline-none hover:bg-foreground/[0.03] focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-ring")}>
      {body}
    </button>
  );
}

export function LivePlan({ rooms, names, still, signals, selected, onSelect, onOpen, className, plan }: {
  rooms: Room[]; names: Record<string, string>; still: boolean;
  /** every sensing room's last minutes, keyed by room (GET /api/signals) */
  signals?: Record<string, Signal>;
  selected?: string | null; onSelect?: (roomId: string) => void;
  /** a double-click on a room */
  onOpen?: (roomId: string) => void; className?: string;
  /** the plan to draw (default: the floor being shown) */
  plan?: Plan;
}) {
  const hatch = useId().replace(/:/g, "");
  const hint = useId();
  const current = usePlan();
  const PLAN = plan ?? current;
  const byId = Object.fromEntries(rooms.map((r) => [r.room_id, r]));
  const o = PLAN.outline, c = PLAN.corridor;
  return (
    <div className={cn("plan-fit flex items-center justify-center", className)} style={{ "--plan-ratio": `${W0} / ${H0}` } as React.CSSProperties}>
      <div className="plan-box relative select-none" role="group" aria-label={T("plan.label")} aria-describedby={onSelect ? hint : undefined}>
        {onSelect && <p id={hint} className="sr-only">{T("plan.select_hint")}</p>}
        <svg viewBox={`${X0} ${Y0} ${W0} ${H0}`} className="absolute inset-0 size-full" aria-hidden>
          <defs>
            <pattern id={hatch} width={10} height={10} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width={10} height={10} className="fill-plan-floor" />
              <line x1={0} y1={0} x2={0} y2={10} className="stroke-plan-line" strokeWidth={3} />
            </pattern>
          </defs>
          <rect x={o.x} y={o.y} width={o.w} height={o.h} className="fill-plan-floor stroke-plan-wall" strokeWidth={2.5} />
          {c && <rect x={c.x} y={c.y} width={c.w} height={c.h} className="fill-muted/60" />}
          {PLAN.other.map((s, i) => (
            <rect key={`${i}-${labelOf(s)}`} x={s.x} y={s.y} width={s.w} height={s.h} className="fill-plan-floor stroke-plan-line" strokeWidth={1} />
          ))}
          {Object.entries(PLAN.exits).map(([id, ex]) => (
            <g key={id}>
              <rect x={ex.x} y={ex.y} width={ex.w} height={ex.h} className="fill-plan-floor stroke-plan-wall" strokeWidth={1.5} />
              {Array.from({ length: Math.floor((ex.h - 110) / 16) }, (_, i) => (
                <line key={i} x1={ex.x + 14} x2={ex.x + ex.w - 14} y1={ex.y + 100 + i * 16} y2={ex.y + 100 + i * 16} className="stroke-plan-line" strokeWidth={1} />
              ))}
              {hasDoor(ex) && <DoorSwing o={ex} />}
            </g>
          ))}
          {Object.entries(PLAN.rooms).map(([id, box]) => {
            const room = byId[id];
            const st: TileStatus = room ? statusOf(room) : "none";
            return (
              <g key={id}>
                <rect x={box.x} y={box.y} width={box.w} height={box.h} strokeWidth={st === "none" ? 1.5 : 2}
                  fill={st === "off" ? `url(#${hatch})` : undefined} strokeDasharray={st === "off" || st === "none" ? "7 5" : undefined}
                  className={RECT[st]} />
                {hasDoor(box) && <DoorSwing o={box} />}
              </g>
            );
          })}
        </svg>

        {c && <span className="plan-minor absolute flex items-center justify-center text-base text-muted-foreground"
          style={place({ x: c.x + c.w * 0.5, y: c.y, w: c.w * 0.24, h: c.h })}>{T("plan.corridor")}</span>}
        {PLAN.other.map((s, i) => (
          <span key={`${i}-${labelOf(s)}`} className="plan-minor absolute flex items-center justify-center text-base text-muted-foreground" style={place(s)}>{labelOf(s)}</span>
        ))}
        {Object.entries(PLAN.exits).map(([id, ex]) => (
          <span key={id} className="absolute flex flex-col items-center gap-1 pt-[1%]" style={place(ex)}>
            <span className="rounded-sm bg-[#1E6B45] px-1.5 text-base font-semibold leading-5 text-white">{T("plan.exit_sign")}</span>
            <span className="plan-minor text-base font-medium leading-tight">{labelOf(ex)}</span>
          </span>
        ))}
        {Object.entries(PLAN.rooms).map(([id, box]) => (
          <RoomTile key={id} id={id} box={box} room={byId[id]} name={byId[id]?.name ?? names[id] ?? box.name ?? id} still={still}
            signal={signals?.[id]} selected={selected === id} onSelect={onSelect} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

/** What the fills, borders and the signal line mean. Words with every swatch: colour is never the only cue. */
/** The legend of the live plan and, on the same row at the right, how to use the plan. The row never wraps the hint
 *  under the swatches on a wide screen; on a narrow one the hint takes the next line. */
export function LivePlanLegend({ className, hint, hintClassName }: {
  className?: string; /** a short line at the right end */ hint?: string; hintClassName?: string;
}) {
  const items: [string, string][] = [
    ["legend.ok", "border-ok bg-ok/20"], ["legend.empty", "border-plan-wall bg-card"], ["legend.waste", "border-warn bg-warn/20"],
    ["legend.off", "border-dashed border-off bg-off-soft"], ["plan.no_sensor", "border-dashed border-off bg-muted/40"],
  ];
  return (
    <div data-plan-legend className={cn("flex flex-wrap items-center gap-x-5 gap-y-1 px-1 text-base text-muted-foreground", className)}>
      <ul className="flex flex-wrap items-center gap-x-5 gap-y-1">
        {items.map(([k, cls]) => (
          <li key={k} className="flex items-center gap-2 whitespace-nowrap"><span aria-hidden className={cn("size-3.5 rounded-[2px] border-2", cls)} />{T(k)}</li>
        ))}
      </ul>
      {hint && <p aria-hidden data-plan-hint className={cn("ml-auto whitespace-nowrap", hintClassName)}>{hint}</p>}
    </div>
  );
}

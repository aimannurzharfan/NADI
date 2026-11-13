// The editor's drawing surface: the plan in its 1000 x 560 box with a 10-unit snap. Drag on empty floor to draw
// with the chosen tool, drag a shape to move it, drag a handle to resize it. With the canvas focused, the arrow keys
// move the selected shape by 10 (Shift: 1) and Delete removes it. Every value can also be typed in the side panel,
// so nothing here needs a mouse.
import { useRef, useState } from "react";

import { T } from "@/lib/i18n";
import { atLeast, useSvgScale } from "@/lib/svg-scale";
import { labelOf, type Box, type Plan, type Point } from "@/lib/plan";
import { BOX, SNAP, snap, type Target } from "@/lib/plan-validate";
import { cn } from "@/lib/utils";

export type Tool = "select" | "room" | "exit" | "other";
type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
const HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

export function boxOf(plan: Plan, t: Target): Box | null {
  const o = t.kind === "room" ? plan.rooms[t.id] : t.kind === "exit" ? plan.exits[t.id] : plan.other[Number(t.id)];
  return o ? { x: o.x, y: o.y, w: o.w, h: o.h } : null;
}

const clampBox = (b: Box): Box => {
  const w = Math.max(SNAP, Math.min(b.w, BOX.w)), h = Math.max(SNAP, Math.min(b.h, BOX.h));
  return { x: Math.max(0, Math.min(b.x, BOX.w - w)), y: Math.max(0, Math.min(b.y, BOX.h - h)), w, h };
};

/** The plan with one shape at a new box: a move carries its door and sensor pair along; a resize keeps the door on
 *  the wall it is on. */
export function withBox(plan: Plan, t: Target, next: Box, moved: boolean): Plan {
  const old = boxOf(plan, t);
  if (!old) return plan;
  const b = clampBox(next);
  const dx = b.x - old.x, dy = b.y - old.y;
  const fit = <T extends { x: number; y: number; w: number; h: number; door?: { x: number; side: "n" | "s" } }>(o: T): T => ({
    ...o, ...b,
    ...(o.door ? { door: { ...o.door, x: moved ? o.door.x + dx : Math.max(b.x, Math.min(o.door.x, b.x + b.w)) } } : {}),
  });
  if (t.kind === "room") {
    const room = fit(plan.rooms[t.id]);
    if (room.link && moved) {
      const shift = (p: Point) => ({ x: p.x + dx, y: p.y + dy });
      room.link = { send: shift(room.link.send), recv: shift(room.link.recv) };
    }
    return { ...plan, rooms: { ...plan.rooms, [t.id]: room } };
  }
  if (t.kind === "exit") return { ...plan, exits: { ...plan.exits, [t.id]: fit(plan.exits[t.id]) } };
  return { ...plan, other: plan.other.map((o, i) => (i === Number(t.id) ? fit(o) : o)) };
}

export function without(plan: Plan, t: Target): Plan {
  if (t.kind === "room") {
    const { [t.id]: _gone, ...rooms } = plan.rooms;
    return { ...plan, rooms };
  }
  if (t.kind === "exit") {
    const { [t.id]: _gone, ...exits } = plan.exits;
    return { ...plan, exits };
  }
  return { ...plan, other: plan.other.filter((_, i) => i !== Number(t.id)) };
}

type Drag = { mode: "draw" | "move" | "resize"; start: Point; orig?: Box; target?: Target; handle?: Handle };

export function EditorCanvas({ plan, selected, tool, problems, placing, background, onSelect, onChange, onDraw, onPlace, className }: {
  plan: Plan;
  selected: Target | null;
  tool: Tool;
  /** shapes with a problem: drawn with a red dashed outline */
  problems: Set<string>;
  /** placing a sensor pair: the next click inside the room places it */
  placing: boolean;
  background: string | null;
  onSelect: (t: Target | null) => void;
  onChange: (plan: Plan) => void;
  /** a rectangle drawn with the room, exit or other tool */
  onDraw: (tool: Exclude<Tool, "select">, box: Box) => void;
  onPlace: (p: Point) => void;
  className?: string;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const scale = useSvgScale(svg, BOX.w);
  const px = (n: number) => ({ fontSize: atLeast(n, scale) });  // never below 14 px on screen
  const drag = useRef<Drag | null>(null);
  const [ghost, setGhost] = useState<Box | null>(null);

  const point = (e: React.PointerEvent): Point => {
    const s = svg.current!;
    const m = s.getScreenCTM();
    if (!m) return { x: 0, y: 0 };
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return { x: p.x, y: p.y };
  };
  const key = (t: Target) => `${t.kind}:${t.id}`;
  const isSel = (t: Target) => !!selected && key(selected) === key(t);

  const down = (e: React.PointerEvent, target?: Target, handle?: Handle) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    svg.current?.focus();
    const p = point(e);
    if (placing) {
      onPlace({ x: snap(p.x, 1), y: snap(p.y, 1) });
      return;
    }
    if (handle && target) {
      drag.current = { mode: "resize", start: p, orig: boxOf(plan, target)!, target, handle };
    } else if (target && tool === "select") {
      onSelect(target);
      drag.current = { mode: "move", start: p, orig: boxOf(plan, target)!, target };
    } else if (tool !== "select") {
      drag.current = { mode: "draw", start: { x: snap(p.x), y: snap(p.y) } };
      setGhost({ x: snap(p.x), y: snap(p.y), w: 0, h: 0 });
    } else {
      onSelect(target ?? null);
      return;
    }
    svg.current?.setPointerCapture(e.pointerId);
  };

  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = point(e);
    if (d.mode === "draw") {
      const x2 = snap(p.x), y2 = snap(p.y);
      setGhost({ x: Math.min(d.start.x, x2), y: Math.min(d.start.y, y2), w: Math.abs(x2 - d.start.x), h: Math.abs(y2 - d.start.y) });
      return;
    }
    const o = d.orig!, dx = snap(p.x - d.start.x), dy = snap(p.y - d.start.y);
    if (d.mode === "move") {
      onChange(withBox(plan, d.target!, { ...o, x: o.x + dx, y: o.y + dy }, true));
      return;
    }
    const h = d.handle!;
    let { x, y, w, h: ht } = o;
    if (h.includes("e")) w = Math.max(SNAP, o.w + dx);
    if (h.includes("s")) ht = Math.max(SNAP, o.h + dy);
    if (h.includes("w")) { x = Math.min(o.x + o.w - SNAP, o.x + dx); w = o.x + o.w - x; }
    if (h.includes("n")) { y = Math.min(o.y + o.h - SNAP, o.y + dy); ht = o.y + o.h - y; }
    onChange(withBox(plan, d.target!, { x, y, w, h: ht }, false));
  };

  const up = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    svg.current?.releasePointerCapture?.(e.pointerId);
    if (d?.mode === "draw" && ghost && tool !== "select") {
      setGhost(null);
      if (ghost.w >= SNAP && ghost.h >= SNAP) onDraw(tool, ghost);
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!selected) return;
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      onChange(without(plan, selected));
      onSelect(null);
      return;
    }
    if (e.key === "Escape") {
      onSelect(null);
      return;
    }
    const step = e.shiftKey ? 1 : SNAP;
    const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!delta) return;
    e.preventDefault();
    const b = boxOf(plan, selected);
    if (b) onChange(withBox(plan, selected, { ...b, x: b.x + delta[0], y: b.y + delta[1] }, true));
  };

  const shapeCls = (t: Target, base: string) => cn(base, problems.has(key(t)) && "stroke-crit [stroke-dasharray:6_4]", isSel(t) && "stroke-primary");
  const handles = (t: Target) => {
    const b = boxOf(plan, t);
    if (!b || !isSel(t)) return null;
    const at: Record<Handle, Point> = { nw: { x: b.x, y: b.y }, n: { x: b.x + b.w / 2, y: b.y }, ne: { x: b.x + b.w, y: b.y },
      e: { x: b.x + b.w, y: b.y + b.h / 2 }, se: { x: b.x + b.w, y: b.y + b.h }, s: { x: b.x + b.w / 2, y: b.y + b.h },
      sw: { x: b.x, y: b.y + b.h }, w: { x: b.x, y: b.y + b.h / 2 } };
    return HANDLES.map((h) => (
      <rect key={h} data-handle={h} x={at[h].x - 6} y={at[h].y - 6} width={12} height={12} className="fill-card stroke-primary"
        strokeWidth={2} style={{ cursor: `${h}-resize` }} onPointerDown={(e) => down(e, t, h)} />
    ));
  };

  return (
    <svg ref={svg} viewBox={`0 0 ${BOX.w} ${BOX.h}`} tabIndex={0} role="application" aria-label={T("ed.canvas")}
      aria-describedby="plan-editor-keys" data-editor-canvas data-tool={tool}
      className={cn("h-auto w-full touch-none select-none rounded-md border bg-plan-floor outline-none focus-visible:ring-2 focus-visible:ring-ring",
        placing || tool !== "select" ? "cursor-crosshair" : "cursor-default", className)}
      onPointerDown={(e) => down(e)} onPointerMove={move} onPointerUp={up} onKeyDown={onKey}>
      <defs>
        <pattern id="ed-grid" width={50} height={50} patternUnits="userSpaceOnUse">
          <path d="M 50 0 L 0 0 0 50" className="fill-none stroke-plan-line" strokeWidth={0.6} />
        </pattern>
      </defs>
      <rect width={BOX.w} height={BOX.h} fill="url(#ed-grid)" />
      {background && <image href={background} x={0} y={0} width={BOX.w} height={BOX.h} preserveAspectRatio="xMidYMid meet"
        opacity={plan.background?.opacity ?? 0.5} className="pointer-events-none" />}
      <rect x={plan.outline.x} y={plan.outline.y} width={plan.outline.w} height={plan.outline.h} className="pointer-events-none fill-none stroke-plan-wall" strokeWidth={2} />
      {plan.corridor && <rect x={plan.corridor.x} y={plan.corridor.y} width={plan.corridor.w} height={plan.corridor.h} className="pointer-events-none fill-muted/50" />}
      {plan.other.map((o, i) => {
        const t: Target = { kind: "other", id: String(i) };
        return (
          <g key={`o${i}`} data-shape={`other:${i}`} onPointerDown={(e) => down(e, t)}>
            <rect x={o.x} y={o.y} width={o.w} height={o.h} className={shapeCls(t, "fill-muted/40 stroke-plan-line")} strokeWidth={isSel(t) ? 3 : 1.5} />
            <text x={o.x + o.w / 2} y={o.y + o.h / 2 + 5} textAnchor="middle" className="pointer-events-none fill-muted-foreground" style={px(15)}>{labelOf(o)}</text>
          </g>
        );
      })}
      {Object.entries(plan.exits).map(([id, ex]) => {
        const t: Target = { kind: "exit", id };
        return (
          <g key={`e${id}`} data-shape={`exit:${id}`} onPointerDown={(e) => down(e, t)}>
            <rect x={ex.x} y={ex.y} width={ex.w} height={ex.h} className={shapeCls(t, "fill-ok/10 stroke-ok")} strokeWidth={isSel(t) ? 3 : 2} />
            <text x={ex.x + ex.w / 2} y={ex.y + 24} textAnchor="middle" className="pointer-events-none fill-ok font-semibold" style={px(15)}>{T("plan.exit_sign")}</text>
            <text x={ex.x + ex.w / 2} y={ex.y + 44} textAnchor="middle" className="pointer-events-none fill-foreground" style={px(15)}>{labelOf(ex) || id}</text>
            {ex.door && <line x1={ex.door.x - 15} x2={ex.door.x + 15} y1={ex.door.side === "s" ? ex.y + ex.h : ex.y} y2={ex.door.side === "s" ? ex.y + ex.h : ex.y}
              className="pointer-events-none stroke-ok" strokeWidth={6} />}
          </g>
        );
      })}
      {Object.entries(plan.rooms).map(([id, r]) => {
        const t: Target = { kind: "room", id };
        return (
          <g key={`r${id}`} data-shape={`room:${id}`} onPointerDown={(e) => down(e, t)}>
            <rect x={r.x} y={r.y} width={r.w} height={r.h} className={shapeCls(t, "fill-card/80 stroke-plan-wall")} strokeWidth={isSel(t) ? 3 : 2} />
            <text x={r.x + r.w / 2} y={r.y + r.h / 2 - 4} textAnchor="middle" className="pointer-events-none fill-foreground font-semibold" style={px(16)}>{r.name || id}</text>
            <text x={r.x + r.w / 2} y={r.y + r.h / 2 + 16} textAnchor="middle" className="pointer-events-none fill-muted-foreground" style={px(14)}>{id}</text>
            {r.door && <line x1={r.door.x - 15} x2={r.door.x + 15} y1={r.door.side === "s" ? r.y + r.h : r.y} y2={r.door.side === "s" ? r.y + r.h : r.y}
              className="pointer-events-none stroke-plan-floor" strokeWidth={6} />}
            {r.link && (
              <g className="pointer-events-none">
                <line x1={r.link.send.x} y1={r.link.send.y} x2={r.link.recv.x} y2={r.link.recv.y} className="stroke-brand" strokeWidth={2} strokeDasharray="4 4" />
                <circle cx={r.link.send.x} cy={r.link.send.y} r={7} className="fill-brand" />
                <circle cx={r.link.recv.x} cy={r.link.recv.y} r={7} className="fill-card stroke-brand" strokeWidth={3} />
              </g>
            )}
          </g>
        );
      })}
      {selected && handles(selected)}
      {ghost && <rect x={ghost.x} y={ghost.y} width={ghost.w} height={ghost.h} className="pointer-events-none fill-primary/10 stroke-primary" strokeDasharray="6 4" strokeWidth={2} />}
    </svg>
  );
}

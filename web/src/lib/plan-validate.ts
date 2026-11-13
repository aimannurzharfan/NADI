// The floor plan editor's rules, the same as the server's (server/site.py validate_plan): the same checks, the same
// strings keys and values, so a problem reads the same in the editor and in the server's refusal. The server checks
// again on save; this list only lets the editor show problems while drawing and keep Save off while there are any.
import { T } from "./i18n";
import { labelOf, type Box, type Plan, type PlanExit, type PlanRoom } from "./plan";

export const BOX = { w: 1000, h: 560 };
export const MIN_SIDE = 40;
export const MIN_LINK = 30;
export const MAX_ROOMS = 60;
export const MAX_PLAN_BYTES = 64 * 1024;
export const MAX_NAME = 40;
/** The most people a room's capacity may say (the server's limit). */
export const MAX_CAPACITY = 1000;
export const ROOM_ID = /^[a-z0-9][a-z0-9_-]{0,31}$/;
export const SNAP = 10;

export type Target = { kind: "room" | "exit" | "other"; id: string };
export type Problem = { key: string; values: Record<string, string | number>; target?: Target };

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isRect = (o: unknown): o is Box => !!o && typeof o === "object" && ["x", "y", "w", "h"].every((k) => num((o as Record<string, unknown>)[k]));
const inside = (o: Box) => o.x >= 0 && o.y >= 0 && o.w > 0 && o.h > 0 && o.x + o.w <= BOX.w && o.y + o.h <= BOX.h;
/** Two rectangles share area; touching edges do not count. */
export const overlap = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const nameOk = (n: unknown): n is string => typeof n === "string" && n.trim().length >= 1 && n.length <= MAX_NAME;

/** Every problem with a draft plan, all at once. others: room IDs already used on another floor -> that floor's name.
 *  live: rooms with a sensor reporting now; before: the rooms of the plan as it is saved now. */
export function validatePlan(plan: Plan, others: Record<string, string> = {}, live: Set<string> = new Set(),
  before: Record<string, PlanRoom> = {}): Problem[] {
  const out: Problem[] = [];
  const add = (key: string, values: Record<string, string | number> = {}, target?: Target) => out.push({ key, values, target });
  if (new TextEncoder().encode(JSON.stringify(plan)).length > MAX_PLAN_BYTES) return [{ key: "site.err_too_large", values: { kb: MAX_PLAN_BYTES / 1024 } }];
  if (Object.keys(plan.rooms).length > MAX_ROOMS) add("site.err_too_many", { n: MAX_ROOMS });

  const shape = (item: Box & { door?: { x: number; side: string } }, name: string, target: Target) => {
    if (!isRect(item)) {
      add("site.err_shape_of", { name }, target);
      return false;
    }
    if (!inside(item)) add("site.err_outside", { name }, target);
    else if (item.w < MIN_SIDE || item.h < MIN_SIDE) add("site.err_small", { name, min: MIN_SIDE }, target);
    const d = item.door;
    if (d && !(num(d.x) && (d.side === "n" || d.side === "s") && item.x <= d.x && d.x <= item.x + item.w)) add("site.err_door", { name }, target);
    return true;
  };

  const exits: [string, PlanExit][] = [];
  if (!Object.keys(plan.exits).length) add("site.err_no_exit");
  for (const [key, ex] of Object.entries(plan.exits)) {
    const target: Target = { kind: "exit", id: key };
    const name = labelOf(ex) || key;
    if (!ex.label && !nameOk(ex.name)) add("site.err_name", { name: key, max: MAX_NAME }, target);
    if (shape(ex, name, target)) exits.push([name, ex]);
  }
  plan.other.forEach((o, i) => {
    const target: Target = { kind: "other", id: String(i) };
    const name = labelOf(o) || `#${i + 1}`;
    if (!o.label && !nameOk(o.name)) add("site.err_name", { name, max: MAX_NAME }, target);
    shape(o, name, target);
  });
  const placed: [string, PlanRoom][] = [];
  for (const [id, room] of Object.entries(plan.rooms)) {
    const target: Target = { kind: "room", id };
    if (!ROOM_ID.test(id)) {
      add("site.err_id", { id: id.slice(0, 32) }, target);
      continue;
    }
    const name = nameOk(room.name) ? room.name : id;
    if (room.name !== undefined && !nameOk(room.name)) add("site.err_name", { name: id, max: MAX_NAME }, target);
    if (id in others) add("site.err_taken", { id, floor: others[id] }, target);
    if (!(room.exit in plan.exits)) add("site.err_exit_missing", { name }, target);
    if (room.area_m2 !== undefined && !(num(room.area_m2) && room.area_m2 >= 1 && room.area_m2 <= 100000)) add("site.err_area", { name }, target);
    if (room.capacity !== undefined && !(Number.isInteger(room.capacity) && room.capacity >= 1 && room.capacity <= MAX_CAPACITY)) add("site.err_capacity", { name, max: MAX_CAPACITY }, target);
    if (!shape(room, name, target)) continue;
    const link = room.link;
    if (link) {
      const ends = [link.send, link.recv];
      const good = ends.every((e) => e && num(e.x) && num(e.y) && room.x <= e.x && e.x <= room.x + room.w && room.y <= e.y && e.y <= room.y + room.h);
      if (!good || Math.hypot(link.send.x - link.recv.x, link.send.y - link.recv.y) < MIN_LINK) add("site.err_link", { name, min: MIN_LINK }, target);
    }
    for (const [otherName, r] of placed) if (overlap(room, r)) add("site.err_overlap", { a: otherName, b: name }, target);
    for (const [exitName, ex] of exits) if (overlap(room, ex)) add("site.err_overlap", { a: name, b: exitName }, target);
    placed.push([name, room]);
  }
  for (const id of Object.keys(before).filter((r) => live.has(r) && !(r in plan.rooms)).sort()) {
    add("site.err_live", { id, name: before[id].name || id });
  }
  return out;
}

export const message = (p: { key: string; values: Record<string, string | number> }) => T(p.key, p.values);

/** Guideline only: one sensor pair covers about 3 to 5 m between boards (our test), so about one pair per 16 m². */
export const suggestedPairs = (area: number) => Math.max(1, Math.ceil(area / 16));

export const snap = (v: number, step = SNAP) => Math.round(v / step) * step;

/** "2 rooms added, 1 moved": what a save changes, against the plan as it is saved now. `details`: rooms whose
 *  capacity, exit, door, floor area or sensor pair changed. */
export function changeSummary(before: Plan, after: Plan): { added: number; removed: number; moved: number; renamed: number; details: number; other: boolean } {
  const ids = new Set([...Object.keys(before.rooms), ...Object.keys(after.rooms)]);
  let added = 0, removed = 0, moved = 0, renamed = 0, details = 0;
  const rest = ({ x: _x, y: _y, w: _w, h: _h, name: _n, ...r }: PlanRoom) => JSON.stringify(r, Object.keys(r).sort());
  for (const id of ids) {
    const a = before.rooms[id], b = after.rooms[id];
    if (!a) added++;
    else if (!b) removed++;
    else {
      if (a.x !== b.x || a.y !== b.y || a.w !== b.w || a.h !== b.h) moved++;
      if ((a.name ?? "") !== (b.name ?? "")) renamed++;
      if (rest(a) !== rest(b)) details++;
    }
  }
  const strip = (p: Plan) => JSON.stringify({ ...p, rooms: {} });
  return { added, removed, moved, renamed, details, other: strip(before) !== strip(after) };
}

export function summaryText(s: ReturnType<typeof changeSummary>): string {
  const parts = [
    s.added && T(s.added === 1 ? "ed.sum_added_one" : "ed.sum_added", { n: s.added }),
    s.removed && T(s.removed === 1 ? "ed.sum_removed_one" : "ed.sum_removed", { n: s.removed }),
    s.moved && T(s.moved === 1 ? "ed.sum_moved_one" : "ed.sum_moved", { n: s.moved }),
    s.renamed && T(s.renamed === 1 ? "ed.sum_renamed_one" : "ed.sum_renamed", { n: s.renamed }),
    s.details && T(s.details === 1 ? "ed.sum_details_one" : "ed.sum_details", { n: s.details }),
    s.other && T("ed.sum_other"),
  ].filter(Boolean) as string[];
  return parts.length ? parts.join(", ") : T("ed.sum_none");
}

// --- templates (the corridor one is the server's corridor_plan, so the example floors pass the same checks) ---

const OUTLINE = { x: 20, y: 20, w: 960, h: 520 };

export function corridorTemplate(prefix: string, level = 1, perSide = 4): Plan {
  const plan: Plan = { viewBox: [0, 0, BOX.w, BOX.h], outline: { ...OUTLINE }, corridor: { x: 20, y: 240, w: 960, h: 70 }, rooms: {},
    exits: { stairA: { label: "plan.stair_a", kind: "stair", x: 20, y: 20, w: 100, h: 220, door: { x: 70, side: "s" } },
      stairB: { label: "plan.stair_b", kind: "stair", x: 860, y: 310, w: 120, h: 230, door: { x: 920, side: "n" } } },
    other: [{ label: "plan.toilets", x: 860, y: 20, w: 120, h: 220 }, { label: "plan.lifts", x: 20, y: 310, w: 140, h: 230 }],
    background: null };
  const rows: [number, number, number, number, "n" | "s"][] = [[120, 860, 20, 220, "s"], [160, 860, 310, 230, "n"]];
  let n = 0;
  for (const [x0, x1, y, h, side] of rows) {
    const w = Math.floor((x1 - x0) / perSide);
    for (let i = 0; i < perSide; i++) {
      const x = x0 + i * w;
      const id = `${prefix}-${String.fromCharCode(97 + n)}`;
      n++;
      plan.rooms[id] = { name: T("site.example_room", { level, n: String(n).padStart(2, "0") }), x, y, w, h, door: { x: x + Math.floor(w / 2), side },
        exit: x + w / 2 < 500 ? "stairA" : "stairB" };
    }
  }
  return plan;
}

export function hallTemplate(prefix: string): Plan {
  return { viewBox: [0, 0, BOX.w, BOX.h], outline: { ...OUTLINE }, corridor: null,
    rooms: { [`${prefix}-hall`]: { name: T("ed.tpl_hall_name"), x: 140, y: 20, w: 720, h: 520, door: { x: 500, side: "s" }, exit: "exitA" } },
    exits: { exitA: { name: T("ed.tpl_exit_name", { x: "A" }), kind: "exit", x: 20, y: 20, w: 120, h: 240, door: { x: 80, side: "s" } },
      exitB: { name: T("ed.tpl_exit_name", { x: "B" }), kind: "exit", x: 860, y: 300, w: 120, h: 240, door: { x: 920, side: "n" } } },
    other: [], background: null };
}

export const blankTemplate = (): Plan => ({ viewBox: [0, 0, BOX.w, BOX.h], outline: { ...OUTLINE }, corridor: null, rooms: {}, exits: {},
  other: [], background: null });

/** A room ID not used on this plan or any other floor: room1, room2, ... */
export function freeRoomId(plan: Plan, taken: Iterable<string>, base = "room"): string {
  const used = new Set([...Object.keys(plan.rooms), ...taken]);
  for (let n = 1; ; n++) if (!used.has(`${base}${n}`)) return `${base}${n}`;
}

export function freeExitId(plan: Plan): string {
  for (let n = 1; ; n++) if (!(`exit${n}` in plan.exits)) return `exit${n}`;
}

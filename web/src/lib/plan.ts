// Floor plans. The bundled dashboard/plan.json is floor f1's built-in plan: the first paint, and the fallback when the
// server cannot answer. Every floor's current plan comes from the server (lib/site.tsx), which checks it on save.
import planJson from "@plan";

import { T, hasKey } from "./i18n";

export type Box = { x: number; y: number; w: number; h: number };
export type Door = { x: number; side: "n" | "s" };
export type Point = { x: number; y: number };
/** Where a room's CSI sender and receiver stand: the overview draws the sensing line between them. */
export type PlanLink = { send: Point; recv: Point };
/** name: what the room is called when ROOM_NAMES has no entry for it (the server uses the same fallback). */
/** capacity: how many people the room is meant for (optional, 1 to 1000): a dashed line on its people chart. */
export type PlanRoom = Box & { name?: string; door?: Door; exit: string; link?: PlanLink; area_m2?: number; capacity?: number };
/** label: a strings key (the built-in plan); name: free text typed by an admin, shown as written in both languages */
export type PlanExit = Box & { label?: string; name?: string; kind?: "stair" | "exit"; door?: Door };
export type PlanOther = Box & { label?: string; name?: string };
export type Plan = {
  viewBox: [number, number, number, number];
  outline: Box;
  corridor: Box | null;
  rooms: Record<string, PlanRoom>;
  exits: Record<string, PlanExit>;
  other: PlanOther[];
  background?: { image: string; opacity: number } | null;
};

const { _about: _ignored, ...builtin } = planJson as unknown as Plan & { _about?: string };
/** Floor f1's built-in plan (version 0). */
export const BUILTIN_PLAN = { background: null, ...builtin } as Plan;
/** The built-in plan: kept for code that only needs the fixed 1000 x 560 box. */
export const PLAN = BUILTIN_PLAN;

/** A new floor that has not been drawn yet. */
export const BLANK_PLAN: Plan = { viewBox: [0, 0, 1000, 560], outline: { x: 20, y: 20, w: 960, h: 520 }, corridor: null,
  rooms: {}, exits: {}, other: [], background: null };

/** What a stair, exit or other space is called: its strings key in the page language, or the name typed in. */
export const labelOf = (item: { label?: string; name?: string }) =>
  item.label && hasKey(item.label) ? T(item.label) : (item.name ?? "").trim();

/** The nearest exit of a room on this plan, by name; null when the room is not on it. */
export function exitIn(plan: Plan, roomId: string): string | null {
  const room = plan.rooms[roomId];
  const ex = room && plan.exits[room.exit];
  return ex ? labelOf(ex) || null : null;
}

/** The nearest exit on the built-in plan (code without the site context: tests, the first paint). */
export const exitFor = (roomId: string) => exitIn(BUILTIN_PLAN, roomId);

/** The rooms drawn on a plan, and whether a sensor pair is drawn for each. */
export const planRoomRefs = (plan: Plan) => Object.entries(plan.rooms).map(([id, r]) => ({ id, linked: !!r.link }));

/** The middle of the corridor (or of the floor, when none is drawn): where its name is written. */
export const corridorMid = (plan: Plan) => (plan.corridor ? plan.corridor.y + plan.corridor.h / 2 : plan.outline.y + plan.outline.h / 2);

export const doorPoint = (o: Box & { door: Door }) => ({
  x: o.door.x,
  y: o.door.side === "s" ? o.y + o.h : o.y,
  dir: o.door.side === "s" ? 1 : -1,
});

/** A door to draw, or none: plans an admin draws may leave doors out. */
export const hasDoor = <T extends { door?: Door }>(o: T): o is T & { door: Door } => !!o.door;

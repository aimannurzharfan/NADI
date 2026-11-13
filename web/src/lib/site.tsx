// Buildings and floors: which floor the console is showing, and that floor's plan.
// The floor comes from ?floor= in the address, else the browser's last choice (localStorage nadiFloor), else the
// server's default floor. The bundled plan is the first paint and the fallback for f1, so a server error never
// blanks the plan. Rooms belong to the floor whose plan lists them; reporting rooms on no plan belong to the default
// floor.
import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useState } from "react";

import { getJSON, useInfo } from "./api";
import { LANG } from "./i18n";
import { BLANK_PLAN, BUILTIN_PLAN, exitIn, type Plan } from "./plan";
import type { Room } from "./types";

export type SiteFloor = { id: string; name: string; level: number; rooms: number; version: number };
export type SiteBuilding = { id: string; name: string; code: string; example: boolean; floors: SiteFloor[] };
export type Site = { buildings: SiteBuilding[]; default_floor: string; editor: boolean };
export type FloorPlanDoc = { floor_id: string; version: number; saved_ts: number | null; saved_by: string | null; plan: Plan };

export const DEFAULT_FLOOR = "f1";
const STORE = "nadiFloor";

type SiteValue = {
  site: Site | undefined;
  floorId: string;
  setFloor: (id: string) => void;
  building: SiteBuilding | undefined;
  floor: SiteFloor | undefined;
  /** the example building: no sensors, read-only */
  example: boolean;
  plan: Plan;
  version: number | null;
  defaultFloor: string;
  /** every room on a real floor: its floor and its nearest exit (from GET /api/info) */
  roomFloors: Record<string, string>;
  roomExits: Record<string, string | null>;
};

const builtin: SiteValue = { site: undefined, floorId: DEFAULT_FLOOR, setFloor: () => {}, building: undefined, floor: undefined,
  example: false, plan: BUILTIN_PLAN, version: 0, defaultFloor: DEFAULT_FLOOR, roomFloors: {}, roomExits: {} };
const Ctx = createContext<SiteValue>(builtin);

function stored(): string | null {
  try {
    return localStorage.getItem(STORE);
  } catch {
    return null;  // private mode
  }
}

function store(id: string) {
  try {
    localStorage.setItem(STORE, id);
  } catch {
    /* not kept */
  }
}

export const findFloor = (site: Site | undefined, id: string) => {
  for (const b of site?.buildings ?? []) {
    const f = b.floors.find((x) => x.id === id);
    if (f) return { building: b, floor: f };
  }
  return null;
};

export const useSiteQuery = () => useQuery({ queryKey: ["site"], queryFn: () => getJSON<Site>(`/api/site?lang=${LANG}`), refetchInterval: 60000 });

/** One floor's current plan; f1 starts from the bundled plan. */
export const useFloorPlan = (floorId: string | null) =>
  useQuery({ queryKey: ["plan", floorId], queryFn: () => getJSON<FloorPlanDoc>(`/api/floors/${encodeURIComponent(floorId!)}/plan?lang=${LANG}`),
    enabled: !!floorId, refetchInterval: 60000 });

export function SiteProvider({ children }: { children: React.ReactNode }) {
  const site = useSiteQuery();
  const { data: info } = useInfo();
  const [params, setParams] = useSearchParams();
  const [last, setLast] = useState<string | null>(stored);
  const fromUrl = params.get("floor");
  const defaultFloor = site.data?.default_floor ?? DEFAULT_FLOOR;
  const wanted = fromUrl ?? last ?? defaultFloor;
  // an unknown floor (deleted, or a link from another server) falls back to the default one
  const floorId = site.data && !findFloor(site.data, wanted) ? defaultFloor : wanted;
  useEffect(() => {  // a shared link with ?floor= becomes this browser's choice too
    if (fromUrl && site.data && findFloor(site.data, fromUrl) && fromUrl !== last) {
      store(fromUrl);
      setLast(fromUrl);
    }
  }, [fromUrl, site.data, last]);
  const doc = useFloorPlan(floorId);
  const found = findFloor(site.data, floorId);
  const value = useMemo<SiteValue>(() => ({
    site: site.data, floorId, building: found?.building, floor: found?.floor, example: !!found?.building.example,
    plan: doc.data?.floor_id === floorId ? doc.data.plan : floorId === DEFAULT_FLOOR ? BUILTIN_PLAN : BLANK_PLAN,
    version: doc.data?.floor_id === floorId ? doc.data.version : null, defaultFloor,
    roomFloors: info?.room_floors ?? {}, roomExits: info?.room_exits ?? {},
    setFloor: (id: string) => {
      store(id);
      setLast(id);
      setParams((p) => {
        const next = new URLSearchParams(p);
        next.set("floor", id);
        next.delete("room");  // the selected room belongs to the floor that was shown
        return next;
      });
    },
  }), [site.data, floorId, found?.building, found?.floor, doc.data, defaultFloor, setParams, info?.room_floors, info?.room_exits]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useSite = () => useContext(Ctx);

/** The current floor's plan. */
export const usePlan = () => useContext(Ctx).plan;

/** The nearest exit of any room, on whichever floor it is drawn (the server knows every floor). */
export function useExitName() {
  const { plan, roomExits } = useSite();
  return (roomId: string): string | null => roomExits[roomId] ?? exitIn(plan, roomId) ?? exitIn(BUILTIN_PLAN, roomId);
}

/** Which floor a room is on: the floor whose plan lists it, else the default floor. */
export function useFloorOf() {
  const { defaultFloor, plan, floorId, roomFloors } = useSite();
  return (roomId: string): string => roomFloors[roomId] ?? (roomId in plan.rooms ? floorId : defaultFloor);
}

/** The plan for the emergency view and the export: the floor being shown when one of its rooms has reported, else
 *  the first real floor that has one (never the example building while a real room reports), else the default floor. */
export function useEmergencyPlan(rooms: Room[]): Plan {
  const { site, floorId, plan, example, defaultFloor } = useSite();
  const floorOf = useFloorOf();
  const reported = new Set(rooms.filter((r) => r.count_ts != null).map((r) => floorOf(r.room_id)));
  const real = (site?.buildings ?? []).filter((b) => !b.example).flatMap((b) => b.floors.map((f) => f.id));
  const target = !example && reported.has(floorId) ? floorId : real.find((id) => reported.has(id)) ?? defaultFloor;
  const doc = useFloorPlan(target === floorId ? null : target);
  if (target === floorId) return plan;
  return doc.data?.floor_id === target ? doc.data.plan : target === DEFAULT_FLOOR ? BUILTIN_PLAN : BLANK_PLAN;
}

/** The rooms of the floor being shown. */
export function useFloorRooms(rooms: Room[]): Room[] {
  const floorOf = useFloorOf();
  const { floorId } = useSite();
  return rooms.filter((r) => floorOf(r.room_id) === floorId);
}

// Overview: one screen that answers "is the building all right?" at a glance (docs/design/DIRECTION.md).
//   title and live chip
//   building status                    full width: air conditioning waste today (the highlight), rooms, sensors
//   live floor plan (the hero)         left, about 65%;  needs attention + live activity on the right
//   people, today, detection           bottom row
// A click on a room of the plan selects it and the People card follows; the choice is kept in the address
// (?room=, ?range=) and in this browser. One request (GET /api/signals) feeds the trace of every tile, whatever the
// number of rooms; the People card asks for the selected room's history only. From 1280 px wide the page fills the window; on a short window the plan keeps its size and the bottom
// row scrolls. Movement is data-driven only (see lib/motion.ts); during an emergency or drill, or with "reduce
// motion", none.
import { LazyMotion, domAnimation } from "motion/react";
import { useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { LIST_LIMIT } from "@/components/list-limit";
import { LiveChip } from "@/components/live-chip";
import { LiveActivity } from "@/components/overview/activity";
import { NeedsAttention } from "@/components/overview/attention";
import { BuildingStatus } from "@/components/overview/building-status";
import { DetectionCard } from "@/components/overview/detection-card";
import { LivePlan, LivePlanLegend } from "@/components/overview/live-plan";
import { Section } from "@/components/overview/section";
import { PeopleCard } from "@/components/overview/people-chart";
import { TodayCard } from "@/components/overview/today-card";
import { ErrorState } from "@/components/panel";
import { ExampleNote } from "@/components/site-switcher";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, useHistory, useIncidents, useInfo, useMe, usePeople, useRooms, useSignals, useUptime } from "@/lib/api";
import { PEOPLE_MINUTES, peopleRefetchMs, pickRange, storeRange, storedRange, type PeopleRange } from "@/lib/people-range";
import { countOf, statusOf } from "@/lib/format";
import { T } from "@/lib/i18n";
import { usePrefersReducedMotion } from "@/lib/motion";
import { attentionItems, defaultRoom, drillLine, minutesToday, pickRoom, storeRoom, storedRoom, todayStats } from "@/lib/overview";
import { planRoomRefs } from "@/lib/plan";
import { useFloorRooms, usePlan, useSite } from "@/lib/site";

export function OverviewPage() {
  const rooms = useRooms();
  const info = useInfo();
  const me = useMe();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const reduced = usePrefersReducedMotion();
  const all = rooms.data;
  const now = all?.now ?? Math.floor(Date.now() / 1000);
  // the floor on screen: its plan, and the rooms that belong to it (the alerts and the waste total stay building-wide)
  const PLAN = usePlan();
  const site = useSite();
  const floorRooms = useFloorRooms(all?.rooms ?? []);
  const data = all && { ...all, rooms: floorRooms };
  const PLAN_ROOMS = planRoomRefs(PLAN);

  // the server cannot be reached: everything on screen is the last answer (or nothing yet)
  const lost = rooms.isError ? { since: rooms.dataUpdatedAt ? Math.floor(rooms.dataUpdatedAt / 1000) : null } : null;
  const items = attentionItems(all, lost);
  // no movement at all during an emergency or drill, or when the viewer asked for reduced motion
  const still = reduced || !!data?.emergency.on;

  // ---- the selected room: the address, else the viewer's last choice, else a default worked out once
  const names = info.data?.room_names ?? {};
  const nameOf = (id: string) => data?.rooms.find((r) => r.room_id === id)?.name ?? names[id] ?? PLAN.rooms[id]?.name ?? id;
  const offPlan = (data?.rooms ?? []).filter((r) => !(r.room_id in PLAN.rooms));
  const known = [...PLAN_ROOMS.map((p) => p.id), ...offPlan.map((r) => r.room_id)];
  const [stored, setStored] = useState(storedRoom);
  // the default must not jump between rooms by itself: it is set when room data first arrives and then kept
  // a new floor works out its own default once its plan is in
  const fallback = useRef<{ floor: string; version: number | null; id: string | null } | null>(null);
  if (data && (fallback.current?.floor !== site.floorId || fallback.current.version !== site.version)) {
    fallback.current = { floor: site.floorId, version: site.version, id: defaultRoom(data.rooms, PLAN_ROOMS) };
  }
  const selected = pickRoom(known, params.get("room"), stored, fallback.current?.id ?? null);
  const select = (id: string) => {
    setStored(id);
    storeRoom(id);
    setParams((before) => {
      const next = new URLSearchParams(before);
      next.set("room", id);
      return next;
    }, { replace: true });
  };
  const open = (id: string) => navigate(`/floor?room=${encodeURIComponent(id)}`);

  // the dropdown lists every room, on the plan or off it, by name ("Room 2" before "Room 10")
  const choices = known.map((id) => ({ id, name: nameOf(id) })).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));

  const signals = useSignals();
  const room = data?.rooms.find((r) => r.room_id === selected);
  // why there is no chart for the selected room, in words (never an empty chart)
  const none = !data || !selected || room ? null : PLAN_ROOMS.find((p) => p.id === selected)?.linked ? "no_report" : "no_sensor";
  // the People card's range: the address, else this browser's last choice, else the last hour
  const [rangeStored, setRangeStored] = useState(storedRange);
  const range = pickRange(params.get("range"), rangeStored);
  const setRange = (r: PeopleRange) => {
    setRangeStored(r);
    storeRange(r);
    setParams((before) => {
      const next = new URLSearchParams(before);
      next.set("range", r);
      return next;
    }, { replace: true });
  };
  const people = usePeople(selected ?? "", PEOPLE_MINUTES[range], { enabled: !!room, refetchMs: peopleRefetchMs(range) });

  const history = useHistory(minutesToday(now));
  const today = todayStats(history.data, now);
  const uptime = useUptime();
  const incidents = useIncidents();

  return (
    <LazyMotion features={domAnimation} strict>
      <div className="flex min-h-0 flex-col gap-3 xl:h-full xl:min-h-[880px]" data-still={still || undefined}>
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-xl font-semibold text-heading">{T("ui.summary_label")}</h1>
          <LiveChip />
        </div>
        <ExampleNote className="shrink-0" />
        <BuildingStatus data={data} items={items} lost={!!lost} plan={PLAN_ROOMS} />

        <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,65fr)_minmax(0,35fr)] xl:grid-rows-[minmax(0,1fr)]">
          <Section title={T("ov.plan_title")} className="min-w-0 xl:min-h-[260px]" bodyClassName="flex min-h-0 flex-col gap-2 p-3"
            aside={(site.building || info.data) && <span>{site.building?.name ?? info.data?.building}, {site.floor?.name ?? info.data?.level}</span>}>
            {!data ? (rooms.isError ? <ErrorState error={rooms.error} /> : (
              <div className="space-y-3 p-2" aria-busy="true" aria-label={T("common.loading")}>
                <Skeleton className="h-4 w-11/12 animate-none" /><Skeleton className="h-4 w-9/12 animate-none" /><Skeleton className="h-4 w-10/12 animate-none" />
              </div>
            )) : (
              <>
                <LivePlan rooms={data.rooms} names={names} still={still}
                  signals={signals.data?.rooms} selected={selected} onSelect={select} onOpen={open}
                  className="aspect-[1000/560] w-full xl:aspect-auto xl:min-h-0 xl:flex-1" />
                {offPlan.length > 0 && (
                  <p data-off-plan className="shrink-0 text-base text-muted-foreground">
                    <span className="font-medium text-foreground">{T("ov.off_plan")}: </span>
                    {offPlan.slice(0, LIST_LIMIT).map((r) => `${r.name} ${countOf(r)} (${T(`status.${statusOf(r)}`)})`).join(", ")}
                    {offPlan.length > LIST_LIMIT && (
                      <>{" "}<Link to="/rooms" data-off-plan-more className="font-medium text-foreground underline underline-offset-2 hover:text-heading">
                        {T("list.and_more", { n: offPlan.length - LIST_LIMIT })}</Link></>
                    )}
                  </p>
                )}
                {/* a short window keeps the legend and drops the hint: the two do not fit one row beside a narrow plan */}
                <LivePlanLegend hint={T("plan.select_hint")} className="shrink-0" hintClassName="[@media(max-height:860px)]:xl:hidden" />
              </>
            )}
          </Section>
          <div className="flex min-h-0 min-w-0 flex-col gap-3">
            <NeedsAttention items={items} admin={!!me.data?.admin} loading={!data && !lost} className="shrink-0 xl:max-h-[58%]" />
            <LiveActivity alerts={data?.alerts ?? []} now={now} still={still} loading={!data} className="max-h-[420px] xl:max-h-none xl:min-h-[150px] xl:flex-1" />
          </div>
        </div>

        <div className="grid shrink-0 gap-3 xl:h-[250px] xl:grid-cols-[minmax(0,5fr)_minmax(0,3fr)_minmax(0,3fr)]">
          <PeopleCard room={room} none={none} people={people.data} loading={!data || (!!room && people.isLoading)} error={room ? people.error : undefined}
            range={range} onRange={setRange} capacity={selected ? PLAN.rooms[selected]?.capacity ?? null : null}
            rooms={choices} selected={selected} onSelect={select}
            roomLink={selected ? `/floor?room=${encodeURIComponent(selected)}` : undefined}
            className="h-64 min-h-0 xl:h-auto" />
          <TodayCard today={today} uptimePct={uptime.data?.pct} incidents={drillLine(incidents.data, data?.emergency, now)}
            loading={history.isLoading} uptimeLoading={uptime.isLoading} incidentsLoading={incidents.isLoading && !data}
            offline={!history.data && history.error instanceof ApiError && history.error.status === 503}
            uptimeOffline={!uptime.data && uptime.error instanceof ApiError && uptime.error.status === 503}
            link="/summary" className="min-h-0" />
          <DetectionCard detector={info.data?.detector} loading={info.isLoading} className="min-h-0" />
        </div>
      </div>
    </LazyMotion>
  );
}

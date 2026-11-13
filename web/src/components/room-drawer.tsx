// One room's details in a side panel, in the order a visitor asks: how many people and since when, where the nearest
// exit is; the people over time; the Wi-Fi signal behind the count; the temperature and humidity; then the facts
// and the health of its sensors.
import { useEffect, useId, useRef, useState } from "react";

import { AdminGate } from "@/components/admin";
import { ClimateChart } from "@/components/charts";
import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { PeopleCard, sinceOf, sinceText } from "@/components/overview/people-chart";
import { LiveSignal } from "@/components/overview/signal-chart";
import { PanelSkeleton, EmptyState, ErrorState } from "@/components/panel";
import { RecordedWaves } from "@/components/recorded-waves";
import { SignalDiagram, pairCaption, pairState } from "@/components/signal-diagram";
import { RoomStatusPill, SimCounter, StatusDot } from "@/components/status";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useClimate, useDevices, useMe, usePeople, useRooms, useSignal } from "@/lib/api";
import { ago, countOf, pct, peopleWord, rm, shown, statusOf, temp, uptime } from "@/lib/format";
import { T } from "@/lib/i18n";
import { usePrefersReducedMotion } from "@/lib/motion";
import { PEOPLE_MINUTES, peopleRefetchMs, storeRange, storedRange, DEFAULT_RANGE, type PeopleRange } from "@/lib/people-range";
import { useExitName, usePlan } from "@/lib/site";
import type { Room } from "@/lib/types";
import { cn } from "@/lib/utils";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b py-1.5 text-base last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

function SensorHealth({ roomId, now }: { roomId: string; now: number }) {
  const me = useMe();
  const devices = useDevices(!!me.data?.admin);
  // every device that reports for this room, the simulator and demo device included
  const mine = (devices.data?.devices ?? []).filter((d) => (d.rooms?.length ? d.rooms : [d.room_id]).includes(roomId));
  const list = useShowMore(mine);
  const listId = useId();
  if (devices.isLoading) return <PanelSkeleton rows={2} />;
  if (!mine.length) return <EmptyState>{T("drawer.no_sensors")}</EmptyState>;
  return (
    <div className="rounded-md border">
    <ul id={listId} data-room-devices className={cn("divide-y text-base", list.expanded && EXPANDED)}>
      {list.shown.map((d) => (
        <li key={d.device_id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 py-2">
          <StatusDot tone={d.online ? "ok" : "off"} />
          <span className="min-w-0 flex-1 truncate font-mono">{d.device_id}
            {d.simulator && <span className="ml-2 rounded-sm border px-1 font-sans font-medium text-muted-foreground">{T("sensors.simulator")}</span>}</span>
          <span className="text-muted-foreground">{d.wifi_rssi != null ? `${d.wifi_rssi} dBm` : "–"}</span>
          <span className="text-muted-foreground">{uptime(d.uptime_s)}</span>
          <span className="text-muted-foreground">{ago(d.last_seen ? now - d.last_seen : null)}</span>
        </li>
      ))}
    </ul>
    <ShowMore hidden={list.hidden} expanded={list.expanded} onToggle={list.toggle} controls={listId} />
    </div>
  );
}

/** The room's sensing pair as a picture, its live signal (the last 5 minutes) and, when there are any, its recorded waves. */
function RoomSignal({ room }: { room: Room }) {
  const rooms = useRooms();
  const reduced = usePrefersReducedMotion();
  const signal = useSignal(room.room_id, 5);
  const data = signal.data && signal.data.room_id === room.room_id ? signal.data : undefined;
  const state = pairState(room, data);
  // nothing moves during an emergency or drill, or when the viewer asked for reduced motion
  const still = reduced || !!rooms.data?.emergency.on;
  return (
    <div className="space-y-4" data-still={still || undefined}>
      <div className="rounded-lg border bg-card px-4 py-3">
        <SignalDiagram state={state} caption={pairCaption(state, data)} still={still}
          reportTs={data?.points.length ? data.points[data.points.length - 1].ts : null} />
      </div>
      <LiveSignal room={room} signal={data} loading={signal.isLoading} error={signal.error} heading="h4" className="h-80" />
      <RecordedWaves roomId={room.room_id} />
    </div>
  );
}

/** Side drawer with one room's details: counts, signal, climate, sensors and last update. A room that is drawn on
 *  the plan but has never reported opens too (`noSensor`), and says so (no sensor, or a sensor pair that is silent). `section="signal"` opens it at the signal. */
export function RoomDrawer({ room, noSensor = null, now, onClose, section }: {
  room: Room | null; noSensor?: { id: string; name: string; linked?: boolean } | null; now: number; onClose: () => void; section?: string | null;
}) {
  const exitFor = useExitName();
  const plan = usePlan();
  const id = room?.room_id ?? "";
  // the same range as the Overview's People card, remembered in this browser; the climate chart follows it
  const [range, setRangeState] = useState<PeopleRange>(() => storedRange() ?? DEFAULT_RANGE);
  const setRange = (r: PeopleRange) => { setRangeState(r); storeRange(r); };
  const minutes = PEOPLE_MINUTES[range];
  const people = usePeople(id, minutes, { enabled: !!room, refetchMs: peopleRefetchMs(range) });
  const climate = useClimate(id, minutes);
  const since = sinceOf(room ?? undefined, people.data);
  const exit = exitFor(room?.room_id ?? noSensor?.id ?? "");
  const capacity = plan.rooms[id]?.capacity ?? null;
  const open = !!room || !!noSensor;
  const signalRef = useRef<HTMLHeadingElement>(null);
  const openId = room?.room_id ?? noSensor?.id ?? "";
  useEffect(() => {
    if (section !== "signal" || !openId) return;
    // after the sheet has been put on the page
    const timer = window.setTimeout(() => signalRef.current?.scrollIntoView?.({ block: "start" }), 50);
    return () => window.clearTimeout(timer);
  }, [section, openId]);
  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        {!room && noSensor && (
          <>
            <SheetHeader className="text-left">
              <SheetTitle className="text-lg">{noSensor.name}</SheetTitle>
              <SheetDescription className="text-base">{T("sig.plan_id", { id: noSensor.id })}</SheetDescription>
            </SheetHeader>
            <h3 className="mt-5 text-base font-semibold text-heading">{T("sig.title")}</h3>
            <div data-no-sensor className="mt-2 rounded-lg border-2 border-dashed border-off bg-off-soft px-4 py-5 text-base">
              <p className="font-semibold text-off">{T(noSensor.linked ? "plan.no_report" : "plan.no_sensor")}</p>
              <p className="mt-1 text-muted-foreground">{T(noSensor.linked ? "sig.no_report_hint" : "sig.no_sensor_hint")}</p>
            </div>
            <dl className="mt-5">
              <Fact label={T("detail.nearest_exit")}>{exit ?? T("detail.not_on_plan")}</Fact>
            </dl>
          </>
        )}
        {room && (
          <>
            <SheetHeader className="text-left">
              <div className="flex items-center gap-2">
                <SheetTitle className="text-lg">{room.name}</SheetTitle>
                <RoomStatusPill status={statusOf(room)} />
              </div>
              {/* the answer first: how many people, since when, and the way out */}
              <SheetDescription asChild>
                <div className="text-base text-foreground">
                  <p data-room-count>
                    <span className="text-xl font-semibold tabular-nums">{countOf(room)}</span>{" "}
                    <span className="text-muted-foreground">{room.live ? peopleWord(room.headcount) : T("count.unknown")}
                      {since != null && <span data-room-since> · {T("ppl.since", { time: sinceText(since, people.data!.now) })}</span>}
                      {!room.live && room.headcount != null && <> · {T("count.last_short", { count: shown(room.headcount, room.at_least) })}</>}</span>
                  </p>
                  <p data-room-exit className="text-muted-foreground">{exit ? T("detail.nearest_exit_is", { exit }) : T("detail.not_on_plan")}</p>
                  <SimCounter room={room} className="mt-1" />
                </div>
              </SheetDescription>
            </SheetHeader>
            {room.waste && <p className="mt-3 rounded-md bg-warn-soft px-3 py-2 text-base text-warn">
              {T("detail.waste_note", { minutes: room.waste.minutes, minute_word: T(room.waste.minutes === 1 ? "unit.minute" : "unit.minutes"), rm: room.waste.rm.toFixed(2) })}</p>}
            {!room.live && <p className="mt-3 rounded-md bg-off-soft px-3 py-2 text-base text-off">{T("detail.offline_note")}</p>}

            <PeopleCard panel heading="h3" room={room} people={people.data} loading={people.isLoading} error={people.error}
              range={range} onRange={setRange} capacity={capacity} className="mt-4 h-72" />

            {room.counter !== "count" && (
              <>
                <h3 ref={signalRef} id="room-signal" className="mt-5 scroll-mt-4 text-base font-semibold text-heading">{T("sig.title")}</h3>
                <div className="mt-2"><RoomSignal room={room} /></div>
              </>
            )}

            <div className="mt-5 flex flex-wrap items-baseline justify-between gap-x-3">
              <h3 className="text-base font-semibold text-heading">{T("drawer.climate_chart")}</h3>
              {(room.temp_c != null || room.humidity != null) && (
                <p data-climate-now className="text-base font-medium tabular-nums">{temp(room.temp_c)}{room.humidity != null && ` · ${pct(room.humidity)}`}</p>
              )}
            </div>
            <div className="mt-1">
              {climate.isLoading ? <PanelSkeleton rows={3} /> : climate.error ? <ErrorState error={climate.error} />
                : !climate.data?.points.length ? <EmptyState>{T("drawer.no_climate")}</EmptyState>
                : <ClimateChart points={climate.data.points} />}
            </div>

            <dl className="mt-5">
              <Fact label={T("detail.last_update")}>{ago(room.count_ts ? now - room.count_ts : null)}</Fact>
              {capacity != null && <Fact label={T("detail.capacity")}>{capacity} {peopleWord(capacity)}</Fact>}
              <Fact label={T("rooms.col_waste")}>{rm(room.waste?.rm ?? 0)}</Fact>
              <Fact label={T("detail.room_id_label")}><span className="font-mono">{room.room_id}</span></Fact>
            </dl>

            <h3 className="mt-5 text-base font-semibold text-heading">{T("drawer.sensor_health")}</h3>
            <div className="mt-2"><AdminGate what={T("drawer.sensor_health_what")}><SensorHealth roomId={room.room_id} now={now} /></AdminGate></div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

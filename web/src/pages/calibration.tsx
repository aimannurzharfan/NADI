// /calibration (the old /label leads here), inside the normal frame. Two columns of the same height: on the left,
// label the headcount of one room at a time (each tap is saved to ml/data/labels.csv) and the recent labels; on the
// right, the true state of the trained model and the labelled reports of ONE room against the threshold (it follows
// the room being labelled, and has its own select). Below both, across the page: what is counting each room right
// now. The admin rule applies to all of it.
import { useQueryClient } from "@tanstack/react-query";
import { Square, Undo2 } from "lucide-react";
import { useId, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AdminGate } from "@/components/admin";
import { LabelledDots, LiveDetector, ModelTraining, detectorRows } from "@/components/calibration-charts";
import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { Section } from "@/components/overview/section";
import { ErrorState, PageHeader, PanelSkeleton } from "@/components/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, postJSON, useDetector, useInfo, useLabels, useRooms, useSignals } from "@/lib/api";
import { TIME_ZONE, dateTime, hhmmss, shown } from "@/lib/format";
import { T } from "@/lib/i18n";
import { BUILTIN_PLAN as PLAN, planRoomRefs } from "@/lib/plan";
import { usePlan } from "@/lib/site";
import type { Detector, LabelView, Room } from "@/lib/types";
import { cn } from "@/lib/utils";

const MAX = 100;
const QUICK = [0, 1, 2, 3, 4, 5];

type RoomChoice = { ids: string[]; id: string; pick: (id: string) => void; nameOf: (id: string) => string; live: Record<string, Room>; view: LabelView };

function Labeller({ choice, className }: { choice: RoomChoice; className?: string }) {
  const { ids, id, pick, nameOf, live, view } = choice;
  const qc = useQueryClient();
  const roomId = useId(), customId = useId(), recentId = useId();
  const [toast, setToast] = useState<{ text: string; error?: boolean } | null>(null);
  const [custom, setCustom] = useState("");
  const cur = view.open[id];
  const recent = useShowMore(view.recent);

  async function send(url: string, body?: unknown, ok?: string) {
    try {
      const next = await postJSON<LabelView>(url, body);
      qc.setQueryData(["labels"], next);
      qc.invalidateQueries({ queryKey: ["detector"] });
      if (ok) setToast({ text: ok });
      if (navigator.vibrate) navigator.vibrate(30);
    } catch (e) {
      setToast({ text: T("label.error", { detail: e instanceof Error ? e.message : String(e) }), error: true });
    }
  }
  const now = () => hhmmss(Math.floor(Date.now() / 1000));
  // a label from an earlier day carries its date, so the list never looks out of order
  const when = (ts: number) => (dayKey(ts) === dayKey(Date.now() / 1000) ? hhmmss(ts) : dateTime(ts));
  const label = (n: number) => send("/api/labels", { room_id: id, headcount: n }, T("label.saved", { name: nameOf(id), count: String(n), time: now() }));

  return (
    <Section title={T("cal.label_title")} className={className} bodyClassName="space-y-4 p-4">
      {toast && <p role="status" className={cn("rounded-md border-l-4 bg-muted px-3 py-2 text-base font-medium", toast.error ? "border-crit text-crit" : "border-ok")}>{toast.text}</p>}
      <p className="text-base text-muted-foreground">{T("label.intro")}</p>

      <div className="grid gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,14rem)_1fr] sm:items-end">
        <div>
          <label htmlFor={roomId} className="mb-1 block text-base font-medium">{T("cal.room")}</label>
          <select id={roomId} name="room" value={id} onChange={(e) => { pick(e.target.value); setCustom(""); }} data-room-select
            className="h-11 w-full rounded-md border border-input bg-background px-3 text-base text-foreground">
            {ids.map((r) => <option key={r} value={r}>{nameOf(r)}{view.open[r] ? ` (${T("cal.labelling_now")})` : ""}</option>)}
          </select>
        </div>
        <p className="flex min-h-11 flex-wrap items-center gap-x-4 text-base" data-label-state>
          <span className={cn(cur ? "font-medium text-ok" : "text-muted-foreground")}>
            {cur ? T("label.current", { count: String(cur.headcount), time: hhmmss(cur.start_ts) }) : T("label.none")}
          </span>
          {/* hidden while a label runs, so the sensor's number cannot sway the person counting */}
          {cur ? <span className="text-muted-foreground">{T("label.sensor_hidden")}</span>
            : id in live && <span className="text-muted-foreground">{T("label.sensor", { count: shown(live[id].headcount, live[id].at_least) })}</span>}
        </p>
      </div>

      <div>
        <p id={`${roomId}-count`} className="mb-1 text-base font-medium">{T("cal.people_now")}</p>
        {/* one segmented row: the six usual counts, joined */}
        <div role="group" aria-labelledby={`${roomId}-count`} data-segmented className="flex overflow-hidden rounded-lg border-2 border-border">
          {QUICK.map((n) => (
            <button key={n} type="button" aria-pressed={cur?.headcount === n} onClick={() => label(n)}
              className={cn("h-14 min-w-0 flex-1 border-l-2 border-border text-2xl font-semibold transition-colors first:border-l-0 focus-visible:relative focus-visible:z-10",
                cur?.headcount === n ? "bg-primary text-primary-foreground" : "bg-background hover:bg-accent")}>
              {n}
            </button>
          ))}
        </div>
      </div>

      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => {
        e.preventDefault();
        const n = Number(custom);
        if (!/^\d{1,3}$/.test(custom) || n > MAX) return;
        label(n);
        setCustom("");
      }}>
        <div className="min-w-40 flex-1">
          <label htmlFor={customId} className="mb-1 block text-base font-medium">{T("label.custom")}</label>
          <Input id={customId} name="headcount" type="number" inputMode="numeric" min={0} max={MAX} step={1} value={custom}
            onChange={(e) => setCustom(e.target.value)} className="h-11 text-base" />
        </div>
        <Button type="submit" variant="outline" className="h-11 text-base" disabled={!/^\d{1,3}$/.test(custom) || Number(custom) > MAX}>{T("label.save_custom")}</Button>
        <Button type="button" variant="outline" className="h-11 gap-1.5 text-base" disabled={!cur}
          onClick={() => send("/api/labels", { room_id: id, headcount: null }, T("label.stopped", { name: nameOf(id), time: now() }))}>
          <Square className="size-[18px]" aria-hidden />{T("label.stop")}
        </Button>
      </form>

      <div className="border-t pt-3">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-heading">{T("cal.recent")}</h3>
          <Button variant="outline" size="sm" className="h-9 gap-1.5 border-warn text-base text-warn hover:bg-warn-soft hover:text-warn"
            disabled={!view.recent.length} onClick={() => send("/api/labels/undo", undefined, T("label.undone"))}>
            <Undo2 className="size-[18px]" aria-hidden />{T("label.undo")}
          </Button>
        </div>
        {view.recent.length ? (
          <>
            {/* ten rows, then "Show N more": expanded, the rows scroll in here and the card stops growing */}
            <div id={recentId} className={cn(recent.expanded && EXPANDED)}>
              <table className="w-full text-base" data-recent-labels>
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th scope="col" className="py-1.5 pr-3 font-medium">{T("cal.col_room")}</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">{T("cal.col_people")}</th>
                    <th scope="col" className="py-1.5 text-right font-medium">{T("cal.col_time")}</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.shown.map((r) => (
                    <tr key={`${r.room_id}-${r.start_ts}`} className="border-b last:border-b-0">
                      <td className="py-1.5 pr-3 font-medium">{r.name}</td>
                      <td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{r.headcount}</td>
                      <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                        {r.end_ts ? T("label.ended", { start: when(r.start_ts), end: hhmmss(r.end_ts) }) : T("label.running", { start: when(r.start_ts) })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ShowMore hidden={recent.hidden} expanded={recent.expanded} onToggle={recent.toggle} controls={recentId} className="px-0" />
          </>
        ) : <p className="py-1.5 text-base text-muted-foreground">{T("label.empty")}</p>}
      </div>
    </Section>
  );
}

/** The labelled reports of one room as dots against the threshold. The room follows the one being labelled until the
 *  viewer picks another here, so the card's height does not depend on how many rooms have labels. */
function LabelledReports({ detector, ids, room, onRoom, nameOf, className }: {
  detector: Detector; ids: string[]; room: string; onRoom: (id: string) => void; nameOf: (id: string) => string; className?: string;
}) {
  const selectId = useId();
  const any = Object.values(detector.rooms).some((points) => points.length > 0);
  const points = detector.rooms[room] ?? [];
  // every room that can be labelled, and any room that has labelled reports but is no longer on the list
  const choices = [...new Set([...ids, ...Object.keys(detector.rooms)])];
  return (
    <Section title={T("cal.dots_title")} className={className} bodyClassName="flex min-h-0 flex-col p-4"
      action={any && (
        <>
          <label htmlFor={selectId} className="sr-only">{T("cal.dots_room")}</label>
          <select id={selectId} name="dots-room" data-dots-room value={room} onChange={(e) => onRoom(e.target.value)}
            className="h-8 max-w-48 rounded-md border border-input bg-background px-2 text-base font-medium text-foreground">
            {choices.map((r) => <option key={r} value={r}>{nameOf(r)}</option>)}
          </select>
        </>
      )}>
      {!any ? (
        <div data-no-labelled className="m-auto w-full rounded-lg border-2 border-dashed px-4 py-6 text-center text-base">
          <p className="font-semibold">{T("cal.none")}</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">{T("cal.none_hint")}</p>
        </div>
      ) : !points.length ? (
        <div data-no-labelled-room className="m-auto w-full rounded-lg border-2 border-dashed px-4 py-6 text-center text-base">
          <p className="font-semibold">{T("cal.dots_none_room")}</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">{T("cal.none_hint")}</p>
        </div>
      ) : (
        <>
          <LabelledDots name={nameOf(room)} points={points} threshold={detector.threshold} fill />
          <p className="mt-3 shrink-0 text-base text-muted-foreground">{T("cal.dots_caption", { seconds: detector.report_interval_s })}</p>
        </>
      )}
    </Section>
  );
}

function Calibration() {
  const planRefs = planRoomRefs(usePlan());  // the floor on screen; the room select lists every floor
  const labels = useLabels(true);
  const detector = useDetector(true);
  const signals = useSignals();
  const { data: info } = useInfo();
  const { data: rooms } = useRooms();
  const [params] = useSearchParams();
  const view = labels.data ?? { recent: [], open: {} };
  // every room on a real floor (the server knows them all), and every room with a name
  const ids = [...new Set([...Object.keys(info?.room_floors ?? PLAN.rooms), ...Object.keys(info?.room_names ?? {})])].sort();
  const nameOf = (id: string) => info?.room_names[id] ?? PLAN.rooms[id]?.name ?? id;
  const live = Object.fromEntries((rooms?.rooms ?? []).filter((r) => r.live).map((r) => [r.room_id, r]));
  // the room in the address, else the one being labelled, else the first with a sensor reporting, else the first
  const [picked, setPicked] = useState<string | null>(params.get("room"));
  const id = picked && ids.includes(picked) ? picked : Object.keys(view.open)[0] ?? ids.find((r) => r in live) ?? ids[0] ?? "";
  // the dots follow the labeller's room until another is chosen in their own select
  const [dots, setDots] = useState<string | null>(null);
  const choice: RoomChoice = { ids, id, nameOf, live, view, pick: (next) => { setPicked(next); setDots(null); } };
  const d = detector.data;
  const offline = detector.error instanceof ApiError && detector.error.status === 503;
  const summary = d ?? info?.detector;

  return (
    <>
      <div className="grid items-stretch gap-3 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]" data-cal-columns>
        <Labeller choice={choice} className="h-full" />
        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          {d ? (
            <>
              <ModelTraining model={d.model} className="shrink-0" />
              <LabelledReports detector={d} ids={ids} room={dots ?? id} onRoom={setDots} nameOf={nameOf} className="flex-1" />
            </>
          ) : offline ? <p role="status" className="flex-1 rounded-lg border bg-card p-4 text-base text-warn">{T("cal.mysql")}</p>
            : detector.error ? <div className="flex-1 rounded-lg border bg-card"><ErrorState error={detector.error} /></div>
            : <div className="flex-1 rounded-lg border bg-card p-4"><PanelSkeleton rows={4} /></div>}
        </div>
      </div>
      <LiveDetector mode={summary?.mode} rows={detectorRows(summary, planRefs, rooms?.rooms ?? [], signals.data?.rooms, nameOf)} />
    </>
  );
}

/** The Malaysian calendar day of a time, to tell today's labels from older ones. */
const dayKey = (ts: number) => new Date(ts * 1000).toLocaleDateString("en-CA", { timeZone: TIME_ZONE });

export function CalibrationPage() {
  return (
    <>
      <PageHeader title={T("label.title")} description={T("cal.description")} />
      <AdminGate what={T("label.what")}><Calibration /></AdminGate>
    </>
  );
}

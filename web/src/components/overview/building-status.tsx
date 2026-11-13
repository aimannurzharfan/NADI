// Building status: the first thing to read on the overview. Three groups and one overall pill at the top right.
// The first group is the highlight: what the air conditioning has wasted today, as a figure (RM), the energy beside
// it (kWh) and one labelled pill. Rooms and sensors follow as rows of labelled pills. An emergency is not a group
// here: the header button and the full-screen view cover it, and its normal-day line is in today's summary.
// Driven by lib/overview (levelOf, buildingStatus, overallStatus).
import { DoorOpen, Radio, Snowflake, type LucideIcon } from "lucide-react";
import { useId } from "react";

import { StatusPill } from "@/components/status";
import { Skeleton } from "@/components/ui/skeleton";
import { num, rm } from "@/lib/format";
import { T } from "@/lib/i18n";
import { buildingStatus, overallStatus, type AttentionItem, type PlanRoomRef, type StatusGroup, type StatusPillSpec } from "@/lib/overview";
import { BUILTIN_PLAN, planRoomRefs } from "@/lib/plan";
import type { RoomsState } from "@/lib/types";
import { cn } from "@/lib/utils";

const GROUP: Record<StatusGroup["id"], { label: string; icon: LucideIcon }> = {
  ac: { label: "bs.ac_today", icon: Snowflake },
  rooms: { label: "bs.rooms", icon: DoorOpen },
  sensors: { label: "bs.sensors", icon: Radio },
};

/** The rooms drawn on the built-in plan, and whether a sensor pair is drawn for each. */
export const PLAN_ROOMS: PlanRoomRef[] = planRoomRefs(BUILTIN_PLAN);

function Pills({ pills, lost }: { pills: StatusPillSpec[] | undefined; lost: boolean }) {
  if (pills) return <>{pills.map((p) => <StatusPill key={p.id} tone={p.tone} dashed={p.dashed}>{p.text}</StatusPill>)}</>;
  if (lost) return <StatusPill tone="off" dashed>{T("ov.not_live")}</StatusPill>;
  return <Skeleton className="h-6 w-28 animate-none" />;
}

export function BuildingStatus({ data, items, lost, plan = PLAN_ROOMS, className }: {
  data: RoomsState | undefined; items: AttentionItem[]; lost: boolean;
  /** the rooms of the floor on screen (the bundled plan unless the page passes another) */
  plan?: PlanRoomRef[]; className?: string;
}) {
  const id = useId();
  const overall = overallStatus(data, items, lost);
  const groups = data ? buildingStatus(data, plan) : null;
  const pillsOf = (gid: StatusGroup["id"]) => groups?.find((g) => g.id === gid)?.pills;
  const wasted = data?.waste_today_rm ?? 0;
  return (
    <section aria-labelledby={id} className={cn("shrink-0 rounded-lg border bg-card shadow-panel", className)}>
      <header className="flex min-h-10 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b px-4 py-1.5">
        <h2 id={id} className="text-md font-semibold text-heading">{T("ov.status_label")}</h2>
        {!data && !lost ? <span className="sr-only" role="status">{T("ov.loading_status")}</span> : (
          <p role="status" data-level={overall.level} data-overall={overall.id}>
            <span className="sr-only">{T("bs.overall")}: </span>
            <StatusPill tone={overall.tone} dashed={overall.dashed} className="px-3 py-1 font-semibold">{overall.text}</StatusPill>
          </p>
        )}
      </header>
      <dl className="grid grid-cols-1 divide-y sm:grid-cols-[minmax(0,2fr)_minmax(0,1.5fr)_minmax(0,1fr)] sm:divide-x sm:divide-y-0 [&>*]:border-border">
        {(["ac", "rooms", "sensors"] as const).map((gid) => {
          const { label, icon: Icon } = GROUP[gid];
          return (
            <div key={gid} data-group={gid} className="min-w-0 px-4 py-2.5">
              <dt className="flex items-center gap-2 text-base font-medium text-muted-foreground">
                <Icon className="size-4 shrink-0" aria-hidden />{T(label)}
              </dt>
              {gid === "ac" ? (
                // the highlight: a figure, its energy, one pill. Made by size and place, not by a tint.
                <dd className="mt-1 flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1">
                  {data ? (
                    <>
                      <span data-waste-rm className={cn("text-2xl font-semibold tabular-nums", wasted > 0 ? "text-warn" : "text-foreground")}>{rm(wasted)}</span>
                      {data.waste_today_kwh != null && (
                        <span data-waste-kwh className="whitespace-nowrap text-base tabular-nums text-muted-foreground">{T("bs.kwh", { kwh: num(data.waste_today_kwh, 1) })}</span>
                      )}
                    </>
                  ) : lost ? <span data-waste-rm className="text-2xl font-semibold text-off">–</span> : <Skeleton className="h-8 w-24 animate-none" />}
                  <Pills pills={pillsOf(gid)} lost={lost} />
                </dd>
              ) : (
                <dd className="mt-1.5 flex min-h-7 flex-wrap items-center gap-1.5"><Pills pills={pillsOf(gid)} lost={lost} /></dd>
              )}
            </div>
          );
        })}
      </dl>
    </section>
  );
}

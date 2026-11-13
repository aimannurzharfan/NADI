// The chip beside every page title: is this screen live, and how old is the newest reading. What used to sit in the
// header (mode, rooms reporting, the clock) is one hover or focus away, so the header stays for actions.
import { useEffect, useState } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useInfo, useRooms } from "@/lib/api";
import { ago, hhmmss } from "@/lib/format";
import { T } from "@/lib/i18n";
import { useNewer } from "@/lib/motion";
import { SEP, feedOf, type Feed } from "@/lib/overview";
import type { RoomsState } from "@/lib/types";
import { cn } from "@/lib/utils";

const FEED: Record<Feed, string> = { live: "ov.live", none: "ov.no_live_data", stopped: "ov.not_live" };

/** Server time now: the time of the last answer plus the seconds since it arrived (ticks once a second). */
export function useServerNow(data: RoomsState | undefined, updatedAt: number): number {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (!data) return Math.floor(Date.now() / 1000);
  return data.now + Math.max(0, Math.floor((Date.now() - updatedAt) / 1000));
}

/** Green and "Live" only while at least one sensor is reporting; grey and dashed otherwise, with words that say which
 *  case. The dot does not loop: a ring leaves it once per new report, never in an emergency or with reduced motion. */
export function LiveChip({ className }: { className?: string }) {
  const rooms = useRooms();
  const { data: info } = useInfo();
  const data = rooms.data;
  const now = useServerNow(data, rooms.dataUpdatedAt);
  const newest = (data?.rooms ?? []).reduce<number | null>((max, r) => (r.live && r.count_ts != null && (max == null || r.count_ts > max) ? r.count_ts : max), null);
  const beats = useNewer(newest);
  if (!data && !rooms.isError) return null;
  const feed = feedOf(data, rooms.isError);
  const latest = Math.max(0, ...(data?.rooms ?? []).map((r) => r.count_ts ?? 0));
  const updated = latest ? T("ov.s_updated", { ago: ago(now - latest) }) : null;
  const live = data?.rooms.filter((r) => r.live).length ?? 0;
  const total = data?.rooms.length ?? 0;
  const huawei = info?.mode === "huawei";
  const still = !!data?.emergency.on;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" data-live-chip data-feed={feed}
          className={cn("inline-flex h-7 items-center gap-2 whitespace-nowrap rounded-full border px-2.5 text-base",
            feed === "live" ? "border-ok/40 bg-ok-soft" : "border-dashed border-off bg-off-soft", className)}>
          <span aria-hidden className={cn("relative size-2 rounded-full", feed === "live" ? "bg-ok" : "border-2 border-off")}>
            {feed === "live" && !still && beats > 0 && <span key={beats} className="live-beat absolute inset-0 rounded-full bg-ok" />}
          </span>
          <span className={cn("font-medium", feed === "live" ? "text-ok" : "text-off")}>{T(FEED[feed])}</span>
          {updated && <span className="text-muted-foreground">{SEP.trim()} {updated}</span>}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="start" className="space-y-0.5 text-base">
        <p className="font-medium">{T(huawei ? "ui.mode_huawei" : "ui.mode_local")}: {T(huawei ? "ui.mode_huawei_hint" : "ui.mode_local_hint")}</p>
        <p>{T("ui.rooms_reporting", { live, total })}</p>
        <p>{T("top.clock")}: <time>{hhmmss(now)}</time> ({T("time.zone")})</p>
      </TooltipContent>
    </Tooltip>
  );
}

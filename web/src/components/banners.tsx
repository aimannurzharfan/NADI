import { CirclePlay, CloudOff } from "lucide-react";

import { useRooms } from "@/lib/api";
import { duration, hhmm } from "@/lib/format";
import { T } from "@/lib/i18n";

/** "DEMO SCENARIO" on every page while DEMO_SCENARIO=on: a recorded story must never pass for live data. */
export function DemoBanner() {
  const { data } = useRooms();
  const d = data?.demo;
  if (!d?.on) return null;
  return (
    <div role="status" className="flex items-center gap-2 border-b border-[#6B4FA3]/30 bg-[#F1ECFA] px-4 py-1.5 text-base text-[#4A2F80] dark:bg-[#2A2140] dark:text-[#D9C9F7]">
      <CirclePlay className="size-4" aria-hidden />
      <strong className="font-semibold">{T("ui.demo")}</strong>
      <span>{d.t != null ? T("ui.demo_hint", { t: duration(d.t) }) : T("ui.demo_pause")}</span>
    </div>
  );
}

/** What is offline, with the time of the data still on screen, and a server clock that is off by more than a minute
 *  (checked against NTP by the server; nothing is shown when it could not check). Recovers on its own. */
export function OfflineBanner() {
  const { data, error, dataUpdatedAt } = useRooms();
  const lines: string[] = [];
  if (error && dataUpdatedAt) lines.push(T("banner.server", { time: hhmm(Math.floor(dataUpdatedAt / 1000)) }));
  else if (error) lines.push(T("banner.server", { time: "–" }));
  else if (data) {
    const off = data.offline || {};
    if ("redis" in off) lines.push(T("banner.redis", { time: hhmm(data.stale_ts || off.redis || data.now) }));
    if ("mysql" in off) lines.push(T("banner.mysql", { time: hhmm(off.mysql || data.now) }));
    if ("mqtt" in off) lines.push(T("banner.mqtt", { time: hhmm(off.mqtt || data.now) }));
    if (data.clock) lines.push(T("banner.clock", { n: Math.round(Math.abs(data.clock.offset_s)) }));
  }
  if (!lines.length) return null;
  return (
    <div role="alert" data-offline-banner className="flex items-start gap-2 border-b border-warn/30 bg-warn-soft px-4 py-2 text-base text-warn">
      <CloudOff className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{lines.map((l) => <p key={l}>{l}</p>)}</div>
    </div>
  );
}

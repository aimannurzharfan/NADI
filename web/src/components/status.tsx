import { T } from "@/lib/i18n";
import type { RoomStatus } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Tone = "ok" | "warn" | "crit" | "off" | "neutral";

const DOT: Record<Tone, string> = {
  ok: "bg-ok", warn: "bg-warn", crit: "bg-crit", off: "bg-off", neutral: "bg-muted-foreground/40",
};
const PILL: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", crit: "bg-crit-soft text-crit",
  off: "bg-off-soft text-off", neutral: "bg-muted text-muted-foreground",
};

export const roomTone = (s: RoomStatus): Tone => ({ ok: "ok", empty: "neutral", waste: "warn", off: "off" } as const)[s];

/** Shown wherever a room's count comes from the "count" service: a simulated counter (phase 2), not Wi-Fi sensing. */
export function SimCounter({ room, className }: { room: { counter?: string } | undefined; className?: string }) {
  if (room?.counter !== "count") return null;
  return (
    <span className={cn("inline-block rounded-sm border border-dashed px-1.5 py-px text-base font-medium text-muted-foreground", className)}>
      {T("room.sim_counter")}
    </span>
  );
}

export function StatusDot({ tone, className }: { tone: Tone; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone], className)} />;
}

/** A status as a pill: a soft tint, the status colour for the words, and a mark in front of them, so the colour is
 *  never the only cue. dashed: the grey states (offline, no sensor) carry a dashed outline and a hollow mark too. */
export function StatusPill({ tone, children, className, dashed }: { tone: Tone; children: React.ReactNode; className?: string; dashed?: boolean }) {
  return (
    <span data-tone={tone} className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-base font-medium",
      PILL[tone], dashed ? "border-dashed border-off" : "border-transparent", className)}>
      {dashed ? <span aria-hidden className="inline-block size-2 shrink-0 rounded-full border-2 border-off" /> : <StatusDot tone={tone} />}
      {children}
    </span>
  );
}

export function RoomStatusPill({ status }: { status: RoomStatus }) {
  return <StatusPill tone={roomTone(status)} dashed={status === "off"}>{T(`status.${status}`)}</StatusPill>;
}

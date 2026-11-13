import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { T } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type KpiProps = {
  label: string;
  value: React.ReactNode;
  unit?: string;
  /** difference from the previous period; null = not enough data */
  delta?: number | null;
  deltaText?: string;
  /** "up" if a rise is good news, "down" if a fall is, "none" if neither */
  better?: "up" | "down" | "none";
  hint?: React.ReactNode;
  loading?: boolean;
  tone?: "warn" | "crit" | "ok";
};

/** One figure with its unit and how it moved against the previous period. Deliberately modest in size. */
export function Kpi({ label, value, unit, delta, deltaText, better = "none", hint, loading, tone }: KpiProps) {
  const dir = delta == null || Math.abs(delta) < 1e-9 ? 0 : delta > 0 ? 1 : -1;
  const good = better === "none" || dir === 0 ? null : (dir > 0) === (better === "up");
  const Icon = dir > 0 ? ArrowUpRight : dir < 0 ? ArrowDownRight : Minus;
  return (
    <div className="flex min-w-0 flex-col gap-1 px-4 py-3">
      <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
      {loading ? (
        <Skeleton className="h-7 w-20" />
      ) : (
        <p className={cn("text-2xl font-semibold leading-8 tracking-tight", tone === "warn" && "text-warn", tone === "crit" && "text-crit")}>
          {value}
          {unit && <span className="ml-1 text-sm font-medium text-muted-foreground">{unit}</span>}
        </p>
      )}
      <div className="flex min-h-4 flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
        {delta !== undefined && !loading && (
          delta == null ? (
            <span>{T("ov.no_previous")}</span>
          ) : (
            <span className={cn("inline-flex items-center gap-0.5 font-medium", good === true && "text-ok", good === false && "text-crit")}>
              <Icon className="size-3.5" aria-hidden />
              {deltaText}
            </span>
          )
        )}
        {hint && <span className="truncate">{hint}</span>}
      </div>
    </div>
  );
}

export function KpiStrip({ children, cols = 4 }: { children: React.ReactNode; cols?: 3 | 4 }) {
  return (
    <div className={cn("grid divide-x divide-y rounded-lg border bg-card shadow-panel md:divide-y-0 [&>*]:border-border",
      cols === 3 ? "grid-cols-1 sm:grid-cols-3 sm:divide-y-0" : "grid-cols-2 md:grid-cols-4")}>
      {children}
    </div>
  );
}

import { LiveChip } from "@/components/live-chip";
import { AlertCircle, Inbox } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { T } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type PanelProps = {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  emptyText?: React.ReactNode;
  skeleton?: React.ReactNode;
  children?: React.ReactNode;
  id?: string;
};

/** A bordered section with a header row. Shows a skeleton while loading, a reason on error, and guidance when empty. */
export function Panel({ title, description, actions, className, bodyClassName, loading, error, empty, emptyText, skeleton,
  children, id }: PanelProps) {
  return (
    <section id={id} className={cn("flex min-w-0 flex-col rounded-lg border bg-card shadow-panel", className)}
      aria-label={typeof title === "string" ? title : undefined}>
      {(title || actions) && (
        <header className="flex min-h-11 items-center gap-3 border-b px-4 py-2">
          <div className="min-w-0 flex-1">
            {title && <h2 className="truncate text-sm font-semibold">{title}</h2>}
            {description && <p className="truncate text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName ?? "p-4")}>
        {loading ? (skeleton ?? <PanelSkeleton />) : error ? <ErrorState error={error} /> : empty ? <EmptyState>{emptyText}</EmptyState> : children}
      </div>
    </section>
  );
}

export function PanelSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-busy="true" aria-label={T("common.loading")}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-4" style={{ width: `${92 - i * 11}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({ children, icon }: { children?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-24 flex-col items-center justify-center gap-2 py-6 text-center text-base text-muted-foreground">
      {icon ?? <Inbox className="size-5" aria-hidden />}
      <p className="max-w-sm">{children ?? T("common.empty")}</p>
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const detail = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex h-full min-h-24 flex-col items-center justify-center gap-2 py-6 text-center text-base">
      <AlertCircle className="size-5 text-crit" aria-hidden />
      <p className="font-medium">{T("common.load_failed")}</p>
      <p className="max-w-sm text-base text-muted-foreground">{detail}</p>
    </div>
  );
}

/** The title row of every page: the title, the chip that says how live the data is, and the page's own controls on
 *  the right. */
export function PageHeader({ title, description, actions, live = true }: {
  title: string; description?: React.ReactNode; actions?: React.ReactNode; live?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-balance text-xl font-semibold text-heading">{title}</h1>
          {live && <LiveChip />}
        </div>
        {description && <p className="mt-1 max-w-3xl text-pretty text-base text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="no-print flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

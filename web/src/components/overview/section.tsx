import { useId } from "react";

import { cn } from "@/lib/utils";

/** A titled block of the overview. Headings are sentence case in the brand colour; nothing in here is smaller than 14 px. */
export function Section({ title, action, aside, className, bodyClassName, children, heading: Heading = "h2", bodyRef, footer, oneRow }: {
  /** the header never wraps: the action and the aside shrink instead (the live signal card) */
  oneRow?: boolean;
  /** the body element, for a list that measures how many whole rows fit in it */
  bodyRef?: React.Ref<HTMLDivElement>;
  /** a line under the body that stays in place: "View all N" */
  footer?: React.ReactNode;
  /** a link that belongs to the block as a whole: it sits beside the title, so it never adds a line to the header */
  action?: React.ReactNode;
  /** h2 on a page; a block inside a panel that already has a title passes a lower level */
  heading?: "h2" | "h3" | "h4";
  title: string; aside?: React.ReactNode; className?: string; bodyClassName?: string; children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("flex min-h-0 min-w-0 flex-col rounded-lg border bg-card shadow-panel", className)}>
      <header className={cn("flex min-h-10 shrink-0 items-center gap-x-3 gap-y-0.5 border-b px-4 py-1.5", oneRow ? "flex-nowrap" : "flex-wrap")}>
        <Heading id={id} className={cn("text-md font-semibold text-heading", oneRow && "shrink-0 whitespace-nowrap")}>{title}</Heading>
        {action && <div className={cn("text-base", oneRow && "min-w-0")}>{action}</div>}
        {aside && <div className={cn("ml-auto flex min-w-0 items-center gap-x-3 gap-y-0.5 text-base text-muted-foreground", oneRow ? "flex-nowrap" : "flex-wrap")}>{aside}</div>}
      </header>
      <div ref={bodyRef} className={cn("min-h-0 flex-1", bodyClassName ?? "p-3")}>{children}</div>
      {footer && <footer className="shrink-0 border-t px-4 py-1">{footer}</footer>}
    </section>
  );
}

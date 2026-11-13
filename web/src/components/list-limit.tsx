// One rule for every list in the console (docs/design/DIRECTION.md, "Lists"): a list never makes its card taller
// than its neighbours expect, and never pushes another card.
//   long feeds (live activity, needs attention): whole rows only, at most LIST_LIMIT, no scroll box; when rows are
//     hidden a "View all N" link at the foot of the card opens the full page            -> useWholeRows + ViewAll
//   short secondary lists (recent labels, audit log, ...): LIST_LIMIT rows, then "Show N more"; expanded, the list
//     scrolls inside the card at a fixed maximum height and the button reads "Show fewer" -> useShowMore + ShowMore
// A page's own main table is the full list, and lists a person's safety depends on show everything: neither uses this.
import { ArrowRight, ChevronDown, ChevronUp } from "lucide-react";
import { useLayoutEffect, useState, type RefObject } from "react";
import { Link } from "react-router-dom";

import { T } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const LIST_LIMIT = 10;
/** An expanded list scrolls inside its card at this height, so the card stops growing. */
export const EXPANDED = "max-h-[26rem] overflow-y-auto";

/** The first `limit` items, or all of them once expanded. `hidden` is how many the button stands for (0: no button). */
export function useShowMore<T>(items: T[], limit = LIST_LIMIT) {
  const [open, setOpen] = useState(false);
  const hidden = Math.max(0, items.length - limit);
  const expanded = open && hidden > 0;
  return { shown: expanded ? items : items.slice(0, limit), hidden, expanded, toggle: () => setOpen((v) => !v) };
}

/** "Show 3 more" / "Show fewer" under a short list. Draws nothing when the list fits. */
export function ShowMore({ hidden, expanded, onToggle, controls, className }: {
  hidden: number; expanded: boolean; onToggle: () => void;
  /** the id of the list this button opens and closes */
  controls?: string; className?: string;
}) {
  if (hidden <= 0) return null;
  const Icon = expanded ? ChevronUp : ChevronDown;
  return (
    <div className={cn("border-t px-4 py-1", className)}>
      <button type="button" data-show-more aria-expanded={expanded} aria-controls={controls} onClick={onToggle}
        className="inline-flex min-h-8 items-center gap-1 rounded-sm text-base font-medium text-foreground underline underline-offset-2 hover:text-heading">
        {expanded ? T("list.show_fewer") : T("list.show_more", { n: hidden })}<Icon className="size-4" aria-hidden />
      </button>
    </div>
  );
}

/** "View all 14" with an arrow: the foot of a feed that has more rows than it shows. */
export function ViewAll({ to, count, label, className }: { to: string; count?: number; label?: string; className?: string }) {
  return (
    <Link to={to} data-view-all
      className={cn("inline-flex min-h-8 items-center gap-1 rounded-sm text-base font-medium text-foreground underline underline-offset-2 hover:text-heading", className)}>
      {label ?? T("list.view_all", { n: count ?? 0 })}<ArrowRight className="size-4" aria-hidden />
    </Link>
  );
}

/** How many of a list's rows fit whole in the box that holds it, so a feed never shows half a row and never needs a
 *  scroll box. `box` is the element whose height is limited (by the layout or a maximum), `list` the element whose
 *  direct children are the rows. Rows the caller hides with `style={{ display: "none" }}` are laid out again for the
 *  measurement, so the answer does not depend on what is shown now. null before the first layout and wherever there
 *  is no layout (tests): the caller then falls back to LIST_LIMIT. `watch` changes when the rows do. */
export function useWholeRows(box: RefObject<HTMLElement | null>, list: RefObject<HTMLElement | null>, watch: unknown = null): number | null {
  const [fit, setFit] = useState<number | null>(null);
  useLayoutEffect(() => {
    const outer = box.current, inner = list.current;
    if (!outer || !inner) {
      setFit(null);
      return;
    }
    const measure = () => {
      const rows = [...inner.children] as HTMLElement[];
      const was = rows.map((r) => r.style.display);
      for (const r of rows) r.style.display = "";
      const style = getComputedStyle(outer);
      const room = outer.clientHeight - (parseFloat(style.paddingTop) || 0) - (parseFloat(style.paddingBottom) || 0);
      const top = outer.getBoundingClientRect().top + outer.clientTop + (parseFloat(style.paddingTop) || 0);
      let n = 0;
      for (const r of rows) {
        if (r.getBoundingClientRect().bottom - top > room + 0.5) break;
        n += 1;
      }
      rows.forEach((r, i) => { r.style.display = was[i]; });
      setFit(outer.clientHeight > 0 ? n : null);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const watcher = new ResizeObserver(measure);
    watcher.observe(outer);
    if (outer.parentElement) watcher.observe(outer.parentElement);
    return () => watcher.disconnect();
  }, [box, list, watch]);
  return fit;
}

/** How many rows a feed draws: whole rows only, never more than the limit, and at least one when there is anything. */
export function wholeRows(total: number, fit: number | null, limit = LIST_LIMIT): number {
  const cap = Math.min(total, limit);
  return fit == null ? cap : Math.max(Math.min(cap, 1), Math.min(cap, fit));
}

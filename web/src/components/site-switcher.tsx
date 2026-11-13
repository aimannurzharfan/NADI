// The building and floor switcher: the chip at the top of the sidebar (the building icon in the rail) opens a wide
// panel beside the sidebar. The search box spans the top. With no search: buildings on the left, the floors of the
// highlighted building on the right (room counts, the current floor marked, 10 then "Show N more"). With a search: one
// list of "Building > Floor" rows. The focus stays in the search box: Up and Down move, Right or Enter on a building
// goes to its floors, Left goes back, Enter on a floor switches and closes, Escape closes and returns to the chip.
import { Building2, Check, ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { LIST_LIMIT } from "@/components/list-limit";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useInfo } from "@/lib/api";
import { T } from "@/lib/i18n";
import { useSite, type Site, type SiteBuilding, type SiteFloor } from "@/lib/site";
import { cn } from "@/lib/utils";

/** The buildings and floors that match a search: a match in a building's name or code keeps all its floors, else
 *  only the floors whose name matches. Case-insensitive; an empty search keeps everything. */
export function filterSite(site: Site | undefined, query: string): SiteBuilding[] {
  const q = query.trim().toLowerCase();
  const all = site?.buildings ?? [];
  if (!q) return all;
  return all.flatMap((b) => {
    if (b.name.toLowerCase().includes(q) || b.code.toLowerCase().includes(q)) return [b];
    const floors = b.floors.filter((f) => f.name.toLowerCase().includes(q));
    return floors.length ? [{ ...b, floors }] : [];
  });
}

/** A search as one list: "Building > Floor" rows, in building order. */
export const searchRows = (site: Site | undefined, query: string) =>
  filterSite(site, query).flatMap((b) => b.floors.map((f) => ({ building: b, floor: f })));

const roomsText = (n: number) => T(n === 1 ? "site.rooms_one" : "site.rooms_count", { n });

/** A grey line on pages that show the example building. */
export function ExampleNote({ className }: { className?: string }) {
  const { example } = useSite();
  if (!example) return null;
  return (
    <p data-example-note className={cn("rounded-lg border border-dashed border-off bg-muted/40 px-4 py-2 text-base text-muted-foreground", className)}>
      {T("site.example_note")}
    </p>
  );
}

const PANEL_W = 640;
const ROW = "flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-base";
const ExampleTag = () => <span className="shrink-0 rounded-full border border-dashed border-off px-2 text-muted-foreground">{T("site.example")}</span>;

export function SiteSwitcher({ rail }: { rail: boolean }) {
  const { site, floorId, setFloor, building, floor } = useSite();
  const { data: info } = useInfo();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [col, setCol] = useState<"b" | "f">("b");  // the column the arrow keys move in (no search)
  const [hiB, setHiB] = useState<string | null>(null);  // highlighted building
  const [hiF, setHiF] = useState<string | null>(null);  // highlighted floor, or "more"
  const [hiR, setHiR] = useState(-1);  // highlighted search row
  const [moreF, setMoreF] = useState(false);
  const [moreR, setMoreR] = useState(false);
  const chip = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const panelId = useId();
  const name = building?.name ?? info?.building ?? "…";
  const level = floor?.name ?? info?.level ?? "";
  const buildings = site?.buildings ?? [];
  const shownB = buildings.find((b) => b.id === hiB) ?? building ?? buildings[0];
  const floorsAll = shownB?.floors ?? [];
  const floors = moreF ? floorsAll : floorsAll.slice(0, LIST_LIMIT);
  const hiddenF = floorsAll.length - Math.min(floorsAll.length, LIST_LIMIT);
  const floorOpts = [...floors.map((f) => f.id), ...(hiddenF ? ["more"] : [])];
  const searching = query.trim().length > 0;
  const rowsAll = searching ? searchRows(site, query) : [];
  const rows = moreR ? rowsAll : rowsAll.slice(0, LIST_LIMIT);
  const rowOpts = rows.length + (rowsAll.length > LIST_LIMIT ? 1 : 0);  // the last option is "Show N more" or "Show fewer"

  // the panel is drawn over the page beside the sidebar (the sidebar scrolls and would clip it), anchored to the chip
  const [at, setAt] = useState<{ top: number; left: number; width: number } | null>(null);
  const place = () => {
    const r = chip.current?.getBoundingClientRect();
    const side = chip.current?.closest("#sidebar")?.getBoundingClientRect();
    if (!r) return;
    const width = Math.min(PANEL_W, window.innerWidth - 32);
    const left = Math.max(16, Math.min((side?.right ?? r.right) + 8, window.innerWidth - width - 16));
    setAt({ top: Math.max(8, r.top), left, width });
  };
  useLayoutEffect(() => {
    if (!open) return;
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open, rail]);

  const close = (focusChip = true) => {
    setOpen(false);
    setQuery("");
    setMoreR(false);
    setHiR(-1);
    if (focusChip) chip.current?.focus();
  };
  // open on the building and floor in use: set when the chip is pressed, so a key pressed straight away is not undone
  const openPanel = () => {
    setHiB(building?.id ?? buildings[0]?.id ?? null);
    setHiF(floorId);
    setCol("b");
    setMoreF(!!building && building.floors.findIndex((f) => f.id === floorId) >= LIST_LIMIT);
    place();  // placed before it opens: a hidden panel's search box could not take the focus
    setOpen(true);
  };
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const away = (e: MouseEvent) => {
      if (!panel.current?.contains(e.target as Node) && !chip.current?.contains(e.target as Node)) close(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const pick = (id: string) => {
    setFloor(id);
    close();
  };
  const optId = (kind: string, id: string) => `${panelId}-${kind}-${id.replace(/[^a-z0-9-]/gi, "_")}`;
  const highlightBuilding = (id: string) => {
    setHiB(id);
    setMoreF(false);
    setHiF(null);
  };
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView?.({ block: "nearest" });

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (searching) {
      if (step && rowOpts) {
        e.preventDefault();
        const next = Math.min(rowOpts - 1, Math.max(0, hiR + step));
        setHiR(next);
        scrollTo(optId("r", String(next)));
      } else if (e.key === "Enter" && hiR >= 0) {
        e.preventDefault();
        if (hiR < rows.length) pick(rows[hiR].floor.id);
        else setMoreR((v) => !v);
      }
      return;
    }
    if (col === "b") {
      const ids = buildings.map((b) => b.id);
      if (step && ids.length) {
        e.preventDefault();
        const at = Math.max(0, ids.indexOf(shownB?.id ?? ""));
        const id = ids[Math.min(ids.length - 1, Math.max(0, at + step))];
        highlightBuilding(id);
        scrollTo(optId("b", id));
      } else if ((e.key === "ArrowRight" || e.key === "Enter") && floorOpts.length) {
        e.preventDefault();
        setCol("f");
        setHiF(floorOpts.includes(floorId) ? floorId : floorOpts[0]);
      }
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setCol("b");
      return;
    }
    if (step && floorOpts.length) {
      e.preventDefault();
      const at = hiF ? floorOpts.indexOf(hiF) : -1;
      const id = floorOpts[Math.min(floorOpts.length - 1, Math.max(0, at + step))];
      setHiF(id);
      scrollTo(optId("f", id));
    } else if (e.key === "Enter" && hiF) {
      e.preventDefault();
      if (hiF === "more") setMoreF((v) => !v);
      else pick(hiF);
    }
  };

  const active = searching ? (hiR >= 0 ? optId("r", String(hiR)) : undefined)
    : col === "b" ? (shownB ? optId("b", shownB.id) : undefined) : hiF ? optId("f", hiF) : undefined;
  const listFor = searching ? `${panelId}-rows` : col === "b" ? `${panelId}-buildings` : `${panelId}-floors`;

  const trigger = rail ? (
    <Tooltip>
      <TooltipTrigger asChild>
        <button ref={chip} type="button" data-building aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? panelId : undefined}
          aria-label={`${T("site.switch")}: ${name}, ${level}`} onClick={() => (open ? close(false) : openPanel())}
          className="mx-auto flex size-10 items-center justify-center rounded-full border text-muted-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
          <Building2 className="size-[18px]" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">{name}, {level}</TooltipContent>
    </Tooltip>
  ) : (
    <button ref={chip} type="button" data-building aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? panelId : undefined}
      aria-label={`${T("site.switch")}: ${name}, ${level}`} onClick={() => (open ? close(false) : openPanel())}
      className="flex w-full items-center gap-3 rounded-lg border bg-background px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
      <Building2 className="size-[18px] shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1 text-base leading-tight">
        <span className="block truncate font-medium" title={name} translate="no">{name}</span>
        <span className="block truncate text-muted-foreground">{level}</span>
      </span>
      <ChevronDown className={cn("size-4 shrink-0 -rotate-90 text-muted-foreground transition-transform", open && "rotate-0")} aria-hidden />
    </button>
  );

  const floorRow = (f: SiteFloor, opt: string, hi: boolean, label?: React.ReactNode) => (
    <li key={opt} id={opt} role="option" aria-selected={hi} data-floor-option={f.id} data-current={f.id === floorId || undefined}
      onClick={() => pick(f.id)} onMouseMove={() => { if (!searching) { setCol("f"); setHiF(f.id); } }}
      className={cn(ROW, hi && "bg-accent ring-2 ring-inset ring-ring", f.id === floorId && "font-medium text-primary", !hi && "hover:bg-accent")}>
      {label ?? <span className="min-w-0 flex-1 truncate">{f.name}</span>}
      <span className="shrink-0 text-muted-foreground">{roomsText(f.rooms)}</span>
      {f.id === floorId && <span className="flex shrink-0 items-center gap-1 text-primary"><Check className="size-4" aria-hidden />{T("site.current")}</span>}
    </li>
  );
  const moreRow = (opt: string, hi: boolean, hidden: number, expanded: boolean, onClick: () => void) => (
    <li key={opt} id={opt} role="option" aria-selected={hi} data-show-more onClick={onClick}
      className={cn(ROW, "font-medium text-primary", hi ? "bg-accent ring-2 ring-inset ring-ring" : "hover:bg-accent")}>
      {expanded ? T("list.show_fewer") : T("list.show_more", { n: hidden })}
    </li>
  );

  return (
    <div className="relative">
      {trigger}
      {open && createPortal(
        <div ref={panel} id={panelId} role="dialog" aria-label={T("site.switch")} onKeyDown={onKey} data-site-panel
          style={at ? { top: at.top, left: at.left, width: at.width } : { visibility: "hidden" }}
          className="fixed z-50 flex max-h-[min(34rem,calc(100vh-2rem))] flex-col rounded-lg border bg-popover text-popover-foreground shadow-lg">
          <div className="border-b p-3">
            <label htmlFor={`${panelId}-q`} className="sr-only">{T("site.search")}</label>
            <input ref={input} id={`${panelId}-q`} type="search" value={query} placeholder={T("site.search")} autoComplete="off" autoFocus
              onChange={(e) => { setQuery(e.target.value); setHiR(-1); setMoreR(false); }}
              role="combobox" aria-expanded="true" aria-autocomplete="list" aria-controls={listFor} aria-activedescendant={active}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          </div>
          {searching ? (
            <div className="min-h-0 flex-1 overflow-y-auto p-2" data-site-results>
              {!rows.length && <p className="px-3 py-2 text-base text-muted-foreground">{T("site.none_found")}</p>}
              <ul id={`${panelId}-rows`} role="listbox" aria-label={T("site.results")}>
                {rows.map((r, i) => floorRow(r.floor, optId("r", String(i)), hiR === i, (
                  <span className="flex min-w-0 flex-1 items-center gap-1.5">
                    <span className="truncate" translate="no">{r.building.name}</span>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="truncate">{r.floor.name}</span>
                    {r.building.example && <ExampleTag />}
                  </span>
                )))}
                {rowsAll.length > LIST_LIMIT && moreRow(optId("r", String(rows.length)), hiR === rows.length, rowsAll.length - LIST_LIMIT, moreR, () => setMoreR((v) => !v))}
              </ul>
            </div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] divide-x">
              <div className="min-h-0 overflow-y-auto p-2">
                <p id={`${panelId}-bh`} className="px-3 pb-1 pt-1 text-base font-semibold text-heading">{T("site.buildings")}</p>
                <ul id={`${panelId}-buildings`} role="listbox" aria-labelledby={`${panelId}-bh`} data-site-buildings>
                  {buildings.map((b) => {
                    const hi = shownB?.id === b.id;
                    return (
                      <li key={b.id} id={optId("b", b.id)} role="option" aria-selected={hi} data-site-building={b.id}
                        onClick={() => { highlightBuilding(b.id); setCol("f"); }} onMouseMove={() => { if (col === "b" && !hi) highlightBuilding(b.id); }}
                        className={cn(ROW, hi ? (col === "b" ? "bg-accent ring-2 ring-inset ring-ring" : "bg-accent") : "hover:bg-accent")}>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium" translate="no" title={b.name}>{b.name}</span>
                          {b.code && <span className="block truncate text-muted-foreground" translate="no">{b.code}</span>}
                        </span>
                        {b.example && <ExampleTag />}
                        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                      </li>
                    );
                  })}
                </ul>
              </div>
              <div className="min-h-0 overflow-y-auto p-2" data-site-floors={shownB?.id}>
                <p id={`${panelId}-fh`} className="truncate px-3 pb-1 pt-1 text-base font-semibold text-heading">
                  {T("site.floors_of", { name: shownB?.name ?? "" })}
                </p>
                <ul id={`${panelId}-floors`} role="listbox" aria-labelledby={`${panelId}-fh`}>
                  {floors.map((f) => floorRow(f, optId("f", f.id), col === "f" && hiF === f.id))}
                  {hiddenF > 0 && moreRow(optId("f", "more"), col === "f" && hiF === "more", hiddenF, moreF, () => setMoreF((v) => !v))}
                </ul>
              </div>
            </div>
          )}
        </div>, document.body,
      )}
    </div>
  );
}

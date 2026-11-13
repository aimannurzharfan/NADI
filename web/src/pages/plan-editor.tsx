// The floor plan editor (/floor/edit?floor=ID, admins only, opened by "Edit plan" on the Floor plan page).
//   header        Edit plan: building, floor (version N)       Preview  Save...  Cancel
//   toolbar       three labelled groups: Draw (Select | Room | Stairs or exit | Other space), Start from, Background image
//   canvas        the draft, 1000 x 560, snap 10                 side panel: shapes and the selected shape's fields
//   checks        the same rules as the server, click a problem to select its shape; Save stays off while any
//   versions      every kept version, Restore makes one current again (as a new version)
// Rectangles only in this round. The server checks every save again; a save on top of someone else's is refused.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AdminGate } from "@/components/admin";
import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { LivePlan } from "@/components/overview/live-plan";
import { PageHeader, Panel } from "@/components/panel";
import { EditorCanvas, type Tool } from "@/components/plan-editor/canvas";
import { Inspector } from "@/components/plan-editor/inspector";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, adminToken, getJSON, postJSON, putJSON, useEnergySettings, useInfo, useRooms, viewerToken } from "@/lib/api";
import { dateTimeYear } from "@/lib/format";
import { LANG, T } from "@/lib/i18n";
import type { Box, Plan, Point } from "@/lib/plan";
import {
  BOX, blankTemplate, changeSummary, corridorTemplate, freeExitId, freeRoomId, hallTemplate, message, overlap, summaryText,
  validatePlan, type Problem, type Target,
} from "@/lib/plan-validate";
import { findFloor, useFloorPlan, useSite } from "@/lib/site";
import { cn } from "@/lib/utils";

type Version = { version: number; saved_ts: number | null; saved_by: string | null; note: string; rooms: number; restored_from?: number };

const TOOLS: [Tool, string][] = [["select", "ed.tool_select"], ["room", "ed.tool_room"], ["exit", "ed.tool_exit"], ["other", "ed.tool_other"]];

/** A free spot for a new shape: the first place on a 10-unit grid inside the outline that touches nothing. */
function freeSpot(plan: Plan, w = 120, h = 100): Box {
  const taken: Box[] = [...Object.values(plan.rooms), ...Object.values(plan.exits), ...plan.other];
  const o = plan.outline;
  for (let y = o.y; y + h <= o.y + o.h; y += 10) {
    for (let x = o.x; x + w <= o.x + o.w; x += 10) {
      const b = { x, y, w, h };
      if (!taken.some((t) => overlap(t, b))) return b;
    }
  }
  return { x: o.x, y: o.y, w, h };
}

export function PlanEditorPage() {
  return (
    <AdminGate what={T("ed.what")}>
      <Editor />
    </AdminGate>
  );
}

function Editor() {
  const { site, floorId, building, floor, example } = useSite();
  const { data: info } = useInfo();
  const rooms = useRooms();
  const energy = useEnergySettings();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const doc = useFloorPlan(floorId);
  const versions = useQuery({ queryKey: ["versions", floorId], queryFn: () => getJSON<{ versions: Version[] }>(`/api/floors/${encodeURIComponent(floorId)}/versions`) });

  const [draft, setDraft] = useState<Plan | null>(null);
  const [base, setBase] = useState<{ floor: string; version: number } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [selected, setSelected] = useState<Target | null>(null);
  const [tool, setTool] = useState<Tool>("select");
  const [placing, setPlacing] = useState<Point[] | null>(null);
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState("");
  const [serverErrors, setServerErrors] = useState<Problem[]>([]);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState("");
  const [restoreOf, setRestoreOf] = useState<number | null>(null);
  const [template, setTemplate] = useState("corridor");
  const [uploadError, setUploadError] = useState("");
  const file = useRef<HTMLInputElement>(null);

  // the draft starts from the floor's current plan, and starts again when another floor or version is loaded
  useEffect(() => {
    if (!doc.data || doc.data.floor_id !== floorId) return;
    if (base && base.floor === floorId && base.version === doc.data.version) return;
    if (base && base.floor === floorId && dirty) return;  // never throw away unsaved work
    setDraft(structuredClone(doc.data.plan));
    setBase({ floor: floorId, version: doc.data.version });
    setDirty(false);
    setSelected(null);
  }, [doc.data, floorId, base, dirty]);

  // leaving with unsaved changes asks first: closing or reloading the tab, and links inside the console
  useEffect(() => {
    if (!dirty) return;
    const unload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    const click = (e: MouseEvent) => {
      const a = (e.target as HTMLElement | null)?.closest?.("a[href]");
      if (a && !a.closest("[data-plan-editor]") && !window.confirm(T("ed.leave"))) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", click, true); };
  }, [dirty]);

  // room IDs on other floors (the example building's too): an ID may be used once in the whole site
  const others = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [id, f] of Object.entries(info?.room_floors ?? {})) {
      const found = findFloor(site, f);
      if (f !== floorId) out[id] = found ? `${found.building.name}, ${found.floor.name}` : f;
    }
    for (const b of site?.buildings ?? []) {
      if (!b.example) continue;
      for (const f of b.floors) {
        const n = Number(f.id.split("-")[1]);
        for (const id of Object.keys(corridorTemplate(`ex-l${String(n).padStart(2, "0")}`, n).rooms)) out[id] = `${b.name}, ${f.name}`;
      }
    }
    return out;
  }, [info?.room_floors, site, floorId]);
  const live = useMemo(() => new Set((rooms.data?.rooms ?? []).filter((r) => r.live).map((r) => r.room_id)), [rooms.data]);
  const problems = useMemo(() => (draft ? validatePlan(draft, others, live, doc.data?.plan.rooms ?? {}) : []), [draft, others, live, doc.data]);
  const marked = new Set(problems.filter((p) => p.target).map((p) => `${p.target!.kind}:${p.target!.id}`));

  if (doc.error && !doc.data) return <Panel error={doc.error} />;  // the plan could not be fetched: say why, never spin
  if (!site || !doc.data || !draft) return <Panel loading />;
  if (example) {
    return (
      <>
        <PageHeader title={T("ed.title", { building: building?.name ?? "", floor: floor?.name ?? "" })} />
        <Panel><p className="text-base">{T("site.err_example")} <Link to="/floor" className="font-medium text-primary underline">{T("ed.back")}</Link></p></Panel>
      </>
    );
  }
  if (!site.editor) {
    return <Panel><p className="text-base">{T("ed.off")}</p></Panel>;
  }

  const change = (next: Plan) => {
    setDraft(next);
    setDirty(true);
    setNotice("");
  };
  const taken = new Set(Object.keys(others));
  const add = (kind: Target["kind"], box?: Box) => {
    const b = box ?? freeSpot(draft);
    if (kind === "room") {
      const id = freeRoomId(draft, taken);
      const exit = Object.keys(draft.exits)[0] ?? "";
      change({ ...draft, rooms: { ...draft.rooms, [id]: { name: T("ed.new_room"), ...b, exit,
        door: { x: Math.round(b.x + b.w / 2), side: b.y + b.h / 2 < BOX.h / 2 ? "s" : "n" } } } });
      setSelected({ kind: "room", id });
    } else if (kind === "exit") {
      const id = freeExitId(draft);
      change({ ...draft, exits: { ...draft.exits, [id]: { name: T("ed.new_exit"), kind: "stair", ...b } } });
      setSelected({ kind: "exit", id });
    } else {
      change({ ...draft, other: [...draft.other, { name: T("ed.new_other"), ...b }] });
      setSelected({ kind: "other", id: String(draft.other.length) });
    }
    setTool("select");
  };
  const place = (p: Point) => {
    if (!placing || selected?.kind !== "room") return;
    const r = draft.rooms[selected.id];
    if (!(r.x <= p.x && p.x <= r.x + r.w && r.y <= p.y && p.y <= r.y + r.h)) return;  // only inside the room
    if (!placing.length) return setPlacing([p]);
    change({ ...draft, rooms: { ...draft.rooms, [selected.id]: { ...r, link: { send: placing[0], recv: p } } } });
    setPlacing(null);
  };
  const startFrom = () => {
    if (dirty && !window.confirm(T("ed.replace"))) return;
    const prefix = freeRoomId(draft, taken, "r").replace(/\d+$/, "") + String(Date.now() % 1000);
    change(template === "corridor" ? corridorTemplate(prefix, floor?.level ?? 1) : template === "hall" ? hallTemplate(prefix) : blankTemplate());
    setSelected(null);
  };
  const upload = async (f: File | undefined) => {
    setUploadError("");
    if (!f) return;
    try {
      const res = await fetch(`/api/floors/${encodeURIComponent(floorId)}/image?lang=${LANG}`, {
        method: "POST", body: f, headers: { "X-Admin-Token": adminToken(), "X-Viewer-Token": viewerToken(), "Content-Type": "application/octet-stream" } });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
      change({ ...draft, background: { image: body.image, opacity: draft.background?.opacity ?? 0.5 } });
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      if (file.current) file.current.value = "";
    }
  };
  const refresh = () => {
    for (const key of [["plan", floorId], ["site"], ["info"], ["versions", floorId], ["rooms"]]) qc.invalidateQueries({ queryKey: key });
  };
  const save = async () => {
    setSaving(true);
    setServerErrors([]);
    try {
      const out = await putJSON<{ version: number }>(`/api/floors/${encodeURIComponent(floorId)}/plan?lang=${LANG}`,
        { plan: draft, note, base_version: base?.version ?? 0 });
      setDirty(false);
      setBase(null);
      setNote("");
      setNotice(T("ed.saved", { n: out.version }));
      setSaving(false);
      refresh();
    } catch (e) {
      setSaving(false);
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      else if (e instanceof ApiError && Array.isArray(e.errorList)) setServerErrors(e.errorList as Problem[]);
      else setServerErrors([{ key: "es.err_save", values: { reason: e instanceof Error ? e.message : String(e) } }]);
    }
  };
  const reload = () => {
    setConflict(false);
    setDirty(false);
    setBase(null);
    refresh();
  };
  const restore = async () => {
    if (restoreOf == null) return;
    try {
      const out = await postJSON<{ version: number }>(`/api/floors/${encodeURIComponent(floorId)}/restore?lang=${LANG}`, { version: restoreOf });
      setNotice(T("ed.restored", { from: restoreOf, n: out.version }));
      setDirty(false);
      setBase(null);
      refresh();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setRestoreOf(null);
    }
  };
  const summary = summaryText(changeSummary(doc.data.plan, draft));
  const shown = [...problems, ...serverErrors];

  return (
    <div data-plan-editor className="space-y-3">
      <PageHeader live={false} title={T("ed.title", { building: building?.name ?? "", floor: floor?.name ?? "" })}
        description={doc.data.version === 0 ? T("ed.version_builtin") : T("ed.version", { n: doc.data.version })}
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" aria-pressed={preview} onClick={() => setPreview((v) => !v)}>{T(preview ? "ed.edit" : "ed.preview")}</Button>
            <Button type="button" disabled={!dirty || problems.length > 0} onClick={() => setSaving(true)} data-open-save>{T("ed.save_open")}</Button>
            <Button type="button" variant="outline" onClick={() => { if (!dirty || window.confirm(T("ed.leave"))) { setDirty(false); navigate("/floor"); } }}>{T("es.cancel")}</Button>
          </div>
        )} />
      {notice && <p role="status" data-editor-notice className="rounded-lg border bg-card px-4 py-2 text-base font-medium">{notice}</p>}

      {/* three labelled groups: the labels share one line and the controls the next; a note sits under its button */}
      <div className="flex flex-wrap items-start gap-x-8 gap-y-3 rounded-lg border bg-card px-4 py-3 text-base" data-editor-toolbar>
        <div data-toolbar-group="draw">
          <p id="ed-draw-label" className="mb-1 text-muted-foreground">{T("ed.group_draw")}</p>
          <div role="radiogroup" aria-labelledby="ed-draw-label" className="flex overflow-hidden rounded-md border">
            {TOOLS.map(([t, key]) => (
              <button key={t} type="button" role="radio" aria-checked={tool === t} onClick={() => { setTool(t); setPlacing(null); }}
                className={cn("h-10 border-r px-3 last:border-r-0", tool === t ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{T(key)}</button>
            ))}
          </div>
        </div>
        <div data-toolbar-group="start">
          <label htmlFor="ed-template" className="mb-1 block text-muted-foreground">{T("ed.template")}</label>
          <div className="flex items-center gap-2">
            <select id="ed-template" value={template} onChange={(e) => setTemplate(e.target.value)} className="h-10 rounded-md border border-input bg-background px-3">
              <option value="corridor">{T("ed.tpl_corridor")}</option>
              <option value="hall">{T("ed.tpl_hall")}</option>
              <option value="blank">{T("ed.tpl_blank")}</option>
            </select>
            <Button type="button" variant="outline" onClick={startFrom}>{T("ed.template_use")}</Button>
          </div>
        </div>
        <div role="group" aria-labelledby="ed-image-label" data-toolbar-group="image">
          <p id="ed-image-label" className="mb-1 text-muted-foreground">{T("ed.group_image")}</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            {/* the browser's own file button says "Choose File" in its language: ours says it in the page's */}
            <input ref={file} id="ed-upload" type="file" accept="image/png,image/jpeg" className="peer sr-only" aria-describedby="ed-upload-help"
              onChange={(e) => upload(e.target.files?.[0])} />
            <label htmlFor="ed-upload" className="inline-flex h-10 cursor-pointer items-center rounded-md border bg-background px-3 font-medium hover:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-ring">
              {T("ed.upload_button")}
            </label>
            {draft.background && (
              <>
                <label htmlFor="ed-opacity" className="flex items-center gap-2 whitespace-nowrap text-muted-foreground">
                  {T("ed.opacity", { n: Math.round(draft.background.opacity * 100) })}
                  <input id="ed-opacity" type="range" min={0} max={100} value={Math.round(draft.background.opacity * 100)} className="h-10 w-32"
                    onChange={(e) => change({ ...draft, background: { ...draft.background!, opacity: Number(e.target.value) / 100 } })} />
                </label>
                <Button type="button" variant="outline" onClick={() => change({ ...draft, background: null })}>{T("ed.bg_remove")}</Button>
              </>
            )}
          </div>
          <p id="ed-upload-help" className="mt-1 text-muted-foreground">{T("ed.upload_help")}</p>
        </div>
        {uploadError && <p role="alert" className="basis-full text-crit">{uploadError}</p>}
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Panel title={preview ? T("ed.preview_title") : T("ed.canvas")} bodyClassName="p-3">
          {preview ? (
            <div data-editor-preview className="aspect-[1000/560]">
              <LivePlan plan={draft} rooms={rooms.data?.rooms ?? []} names={info?.room_names ?? {}} still />
            </div>
          ) : (
            <>
              <EditorCanvas plan={draft} selected={selected} tool={tool} problems={marked} placing={!!placing}
                background={draft.background ? `/api/site/images/${draft.background.image}` : null}
                onSelect={(t) => { setSelected(t); setPlacing(null); }} onChange={change} onDraw={(t, b) => add(t, b)} onPlace={place} />
              <p id="plan-editor-keys" className="mt-2 text-base text-muted-foreground">
                {placing ? T(placing.length ? "ed.place_recv" : "ed.place_send") : T("ed.keys")}
              </p>
            </>
          )}
        </Panel>
        {/* on a wide screen the panel is as tall as the drawing beside it (height 0 with a full minimum: the drawing
            sets the row) and scrolls inside itself, so pressing a button in it never scrolls the drawing away */}
        <Panel title={T("ed.panel")} className="xl:h-0 xl:min-h-full" bodyClassName="p-4 xl:overflow-y-auto">
          <Inspector plan={draft} selected={selected} onSelect={(t) => { setSelected(t); setPlacing(null); }} onChange={change} onAdd={(k) => add(k)}
            placing={!!placing} onPlace={(on) => setPlacing(on ? [] : null)} taken={taken}
            acKw={(id) => energy.data?.settings.ac_kw_rooms[id] ?? energy.data?.settings.ac_kw ?? 10} />
        </Panel>
      </div>

      <Panel title={shown.length ? T("ed.checks_n", { n: shown.length }) : T("ed.checks")} bodyClassName="p-0">
        {!shown.length ? <p className="px-4 py-3 text-base text-ok" data-checks-ok>{T("ed.checks_ok")}</p> : (
          <ul className="divide-y text-base" data-checks>
            {shown.map((p, i) => (
              <li key={i}>
                <button type="button" disabled={!p.target} onClick={() => p.target && setSelected(p.target)}
                  className="flex w-full items-center gap-2 px-4 py-2 text-left text-crit enabled:hover:bg-accent disabled:cursor-default">
                  {message(p)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Versions data={versions.data?.versions ?? []} current={doc.data.version} onRestore={setRestoreOf} />

      <Dialog open={saving && !conflict && !serverErrors.length && dirty} onOpenChange={(open) => !open && setSaving(false)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{T("ed.save_title")}</DialogTitle>
            <DialogDescription data-save-summary>{summary}</DialogDescription>
          </DialogHeader>
          <label htmlFor="ed-note" className="block text-base text-muted-foreground">{T("ed.note")}</label>
          <Input id="ed-note" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} className="h-10 text-base" />
          <DialogFooter className="mt-2">
            <Button type="button" variant="outline" onClick={() => setSaving(false)}>{T("es.cancel")}</Button>
            <Button type="button" onClick={save} data-confirm-save>{T("ed.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={conflict} onOpenChange={(open) => !open && setConflict(false)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{T("ed.conflict_title")}</DialogTitle>
            <DialogDescription>{T("ed.conflict")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConflict(false)}>{T("es.cancel")}</Button>
            <Button type="button" onClick={reload}>{T("ed.reload")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={restoreOf != null} onOpenChange={(open) => !open && setRestoreOf(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{T("ed.restore_title", { n: restoreOf ?? 0 })}</DialogTitle>
            <DialogDescription>{T("ed.restore_note")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setRestoreOf(null)}>{T("es.cancel")}</Button>
            <Button type="button" onClick={restore} data-confirm-restore>{T("ed.restore")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Versions({ data, current, onRestore }: { data: Version[]; current: number; onRestore: (v: number) => void }) {
  const list = useShowMore(data);
  return (
    <Panel title={T("ed.versions")} bodyClassName="p-0">
      <div id="ed-versions" className={cn(list.expanded && EXPANDED)}>
        <table className="w-full text-base" data-versions>
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th scope="col" className="px-4 py-2 font-medium">{T("ed.col_version")}</th>
              <th scope="col" className="px-4 py-2 font-medium">{T("es.col_when")}</th>
              <th scope="col" className="px-4 py-2 font-medium">{T("es.col_who")}</th>
              <th scope="col" className="px-4 py-2 font-medium">{T("ed.note")}</th>
              <th scope="col" className="px-4 py-2"><span className="sr-only">{T("ed.restore")}</span></th>
            </tr>
          </thead>
          <tbody>
            {list.shown.map((v) => (
              <tr key={v.version} className="border-b last:border-b-0" data-version={v.version}>
                <td className="px-4 py-2 tabular-nums">{v.version === 0 ? T("ed.builtin") : v.version}</td>
                <td className="px-4 py-2 tabular-nums">{v.saved_ts ? dateTimeYear(v.saved_ts) : "–"}</td>
                <td className="px-4 py-2">{v.saved_by ?? "–"}</td>
                <td className="px-4 py-2">{v.restored_from != null ? T("ed.restored_from", { n: v.restored_from }) : v.note || "–"}</td>
                <td className="px-4 py-2 text-right">
                  {v.version === current ? <span className="text-muted-foreground">{T("site.current")}</span>
                    : <Button type="button" size="sm" variant="outline" onClick={() => onRestore(v.version)}>{T("ed.restore")}</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShowMore hidden={list.hidden} expanded={list.expanded} onToggle={list.toggle} controls="ed-versions" />
    </Panel>
  );
}

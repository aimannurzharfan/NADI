// The editor's side panel: the list of shapes (select any without a mouse, add one with a button) and every field of
// the selected room, stairs or exit, or other space as a typed value.
import { Link } from "react-router-dom";
import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { T } from "@/lib/i18n";
import { labelOf, type Box, type Door, type Plan, type PlanRoom } from "@/lib/plan";
import { MAX_CAPACITY, ROOM_ID, suggestedPairs, type Target } from "@/lib/plan-validate";
import { cn } from "@/lib/utils";

import { withBox, without } from "./canvas";

const FIELD = "h-10 text-base tabular-nums";
const SELECT = "h-10 w-full rounded-md border border-input bg-background px-3 text-base text-foreground";

function NumberField({ label, value, onChange, step = 10, min, max }: {
  label: string; value: number | undefined; onChange: (v: number) => void; step?: number; min?: number; max?: number;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-base text-muted-foreground">{label}</label>
      <Input id={id} type="number" inputMode="decimal" step={step} min={min} max={max} value={value ?? ""} className={FIELD}
        onChange={(e) => { if (e.target.value !== "" && Number.isFinite(Number(e.target.value))) onChange(Number(e.target.value)); }} />
    </div>
  );
}

function TextField({ label, value, onChange, invalid, hint, name }: {
  label: string; value: string; onChange: (v: string) => void; invalid?: string | null; hint?: string; name?: string;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-base text-muted-foreground">{label}</label>
      <Input id={id} name={name} value={value} maxLength={40} className="h-10 text-base" aria-invalid={invalid ? true : undefined}
        aria-describedby={invalid || hint ? `${id}-note` : undefined} onChange={(e) => onChange(e.target.value)} />
      {(invalid || hint) && <p id={`${id}-note`} role={invalid ? "alert" : undefined} className={cn("mt-1 text-base", invalid ? "text-crit" : "text-muted-foreground")}>{invalid ?? hint}</p>}
    </div>
  );
}

/** How many people the room is meant for: optional, so the field may be emptied (the line on the people chart then
 *  goes). Never an alert, and nothing to do with the detection threshold, which comes from calibration only. */
function CapacityField({ name, value, onChange }: { name: string; value: number | undefined; onChange: (v: number | undefined) => void }) {
  const id = useId();
  const bad = value !== undefined && !(Number.isInteger(value) && value >= 1 && value <= MAX_CAPACITY);
  return (
    <div data-capacity>
      <label htmlFor={id} className="mb-1 block text-base text-muted-foreground">{T("ed.capacity")}</label>
      <Input id={id} name="room-capacity" type="number" inputMode="numeric" step={1} min={1} max={MAX_CAPACITY} value={value ?? ""} className={FIELD}
        aria-invalid={bad || undefined} aria-describedby={`${id}-note`}
        onChange={(e) => onChange(e.target.value === "" || !Number.isFinite(Number(e.target.value)) ? undefined : Number(e.target.value))} />
      <p id={`${id}-note`} role={bad ? "alert" : undefined} className={cn("mt-1 text-base", bad ? "text-crit" : "text-muted-foreground")}>
        {bad ? T("site.err_capacity", { name, max: MAX_CAPACITY }) : T("ed.capacity_hint")}</p>
    </div>
  );
}

function BoxFields({ box, onChange }: { box: Box; onChange: (b: Box) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <NumberField label="X" value={box.x} onChange={(x) => onChange({ ...box, x })} />
      <NumberField label="Y" value={box.y} onChange={(y) => onChange({ ...box, y })} />
      <NumberField label={T("ed.width")} value={box.w} onChange={(w) => onChange({ ...box, w })} />
      <NumberField label={T("ed.height")} value={box.h} onChange={(h) => onChange({ ...box, h })} />
    </div>
  );
}

function DoorFields({ door, box, onChange }: { door: Door | undefined; box: Box; onChange: (d: Door | undefined) => void }) {
  const id = useId();
  return (
    <div className="grid grid-cols-2 gap-2">
      <div>
        <label htmlFor={id} className="mb-1 block text-base text-muted-foreground">{T("ed.door_side")}</label>
        <select id={id} value={door?.side ?? ""} className={SELECT}
          onChange={(e) => onChange(e.target.value ? { x: door?.x ?? Math.round(box.x + box.w / 2), side: e.target.value as Door["side"] } : undefined)}>
          <option value="">{T("ed.door_none")}</option>
          <option value="n">{T("ed.door_n")}</option>
          <option value="s">{T("ed.door_s")}</option>
        </select>
      </div>
      {door && <NumberField label={T("ed.door_x")} value={door.x} onChange={(x) => onChange({ ...door, x })} />}
    </div>
  );
}

/** Rename a room's ID, keeping its place in the plan. */
function renameRoom(plan: Plan, from: string, to: string): Plan {
  const rooms: Record<string, PlanRoom> = {};
  for (const [id, r] of Object.entries(plan.rooms)) rooms[id === from ? to : id] = r;
  return { ...plan, rooms };
}

export function Inspector({ plan, selected, onSelect, onChange, onAdd, placing, onPlace, acKw, taken }: {
  plan: Plan;
  selected: Target | null;
  onSelect: (t: Target | null) => void;
  onChange: (plan: Plan) => void;
  onAdd: (kind: Target["kind"]) => void;
  placing: boolean;
  onPlace: (on: boolean) => void;
  /** a room's air conditioner power (Energy settings), for the read-only line */
  acKw: (roomId: string) => number;
  /** room IDs used on other floors */
  taken: Set<string>;
}) {
  const shapes: [Target, string][] = [
    ...Object.entries(plan.rooms).map(([id, r]) => [{ kind: "room", id }, `${r.name || id} (${id})`] as [Target, string]),
    ...Object.entries(plan.exits).map(([id, e]) => [{ kind: "exit", id }, labelOf(e) || id] as [Target, string]),
    ...plan.other.map((o, i) => [{ kind: "other", id: String(i) }, labelOf(o) || `#${i + 1}`] as [Target, string]),
  ];
  const isSel = (t: Target) => selected?.kind === t.kind && selected.id === t.id;
  const room = selected?.kind === "room" ? plan.rooms[selected.id] : undefined;
  const exit = selected?.kind === "exit" ? plan.exits[selected.id] : undefined;
  const other = selected?.kind === "other" ? plan.other[Number(selected.id)] : undefined;
  const setRoom = (patch: Partial<PlanRoom>) => selected && room && onChange({ ...plan, rooms: { ...plan.rooms, [selected.id]: { ...room, ...patch } } });
  const area = room?.area_m2;

  return (
    <div className="space-y-4 text-base" data-inspector>
      <section aria-labelledby="ed-shapes">
        <h3 id="ed-shapes" className="mb-2 font-semibold">{T("ed.shapes")}</h3>
        <div className="mb-2 flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onAdd("room")}>{T("ed.add_room")}</Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onAdd("exit")}>{T("ed.add_exit")}</Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onAdd("other")}>{T("ed.add_other")}</Button>
        </div>
        <ul className="max-h-[calc(13.5rem+2px)] overflow-y-auto rounded-md border" data-shape-list>
          {shapes.map(([t, name]) => (
            <li key={`${t.kind}:${t.id}`}>
              <button type="button" aria-pressed={isSel(t)} onClick={() => onSelect(t)}
                className={cn("flex h-9 w-full items-center gap-2 px-3 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                  isSel(t) && "bg-primary-soft font-medium text-primary")}>
                <span className="min-w-0 flex-1 truncate">{name}</span>
                <span className="text-muted-foreground">{T(`ed.kind_${t.kind}`)}</span>
              </button>
            </li>
          ))}
          {!shapes.length && <li className="px-3 py-2 text-muted-foreground">{T("ed.no_shapes")}</li>}
        </ul>
      </section>

      {!selected && <p className="text-muted-foreground">{T("ed.select_hint")}</p>}

      {room && selected && (
        <section aria-labelledby="ed-selected" className="space-y-3" data-selected-room={selected.id}>
          <h3 id="ed-selected" className="font-semibold">{T("ed.selected", { name: room.name || selected.id })}</h3>
          <TextField label={T("ed.room_id")} name="room-id" value={selected.id}
            invalid={!ROOM_ID.test(selected.id) ? T("site.err_id", { id: selected.id }) : taken.has(selected.id) ? T("ed.id_taken", { id: selected.id }) : null}
            onChange={(v) => {
              const next = v.trim().toLowerCase();
              if (!next || next === selected.id || next in plan.rooms) return;
              onChange(renameRoom(plan, selected.id, next));
              onSelect({ kind: "room", id: next });
            }} />
          <TextField label={T("ed.name")} name="room-name" value={room.name ?? ""} onChange={(v) => setRoom({ name: v })} />
          <div>
            <label htmlFor="ed-exit" className="mb-1 block text-base text-muted-foreground">{T("ed.nearest_exit")}</label>
            <select id="ed-exit" value={room.exit in plan.exits ? room.exit : ""} className={SELECT} onChange={(e) => setRoom({ exit: e.target.value })}>
              {!(room.exit in plan.exits) && <option value="">{T("ed.choose_exit")}</option>}
              {Object.entries(plan.exits).map(([id, e]) => <option key={id} value={id}>{labelOf(e) || id}</option>)}
            </select>
          </div>
          <CapacityField name={room.name || selected.id} value={room.capacity} onChange={(capacity) => setRoom({ capacity })} />
          <DoorFields door={room.door} box={room} onChange={(door) => setRoom({ door })} />
          <BoxFields box={room} onChange={(b) => onChange(withBox(plan, selected, b, false))} />
          <div className="rounded-md border p-3">
            <p className="mb-2 font-medium">{T("ed.size")}</p>
            <NumberField label={T("ed.area")} value={area} step={1} min={1} onChange={(v) => setRoom({ area_m2: v })} />
            <p className="mt-2 text-muted-foreground">{T("ed.area_or")}</p>
            <AreaFromSides onArea={(v) => setRoom({ area_m2: v })} />
            <p className="mt-2" data-guideline>{T("ed.guideline", { n: suggestedPairs(area ?? 16) })}</p>
          </div>
          <div className="rounded-md border p-3" data-pair>
            <p className="mb-2 font-medium">{T("ed.pair")}</p>
            <p className="mb-2 text-muted-foreground">{placing ? T("ed.pair_placing") : room.link ? T("ed.pair_placed") : T("ed.pair_none")}</p>
            <div className="flex gap-2">
              <Button type="button" size="sm" variant={placing ? "default" : "outline"} onClick={() => onPlace(!placing)}>{placing ? T("es.cancel") : T("ed.pair_place")}</Button>
              {room.link && <Button type="button" size="sm" variant="outline" onClick={() => setRoom({ link: undefined })}>{T("ed.pair_clear")}</Button>}
            </div>
          </div>
          <p data-room-ac>{T("ed.ac_power", { kw: acKw(selected.id) })} <Link to="/energy" className="font-medium text-primary underline underline-offset-2">{T("ed.ac_link")}</Link></p>
          <Button type="button" variant="outline" onClick={() => { onChange(without(plan, selected)); onSelect(null); }}>{T("ed.remove")}</Button>
        </section>
      )}

      {exit && selected && (
        <section aria-labelledby="ed-selected" className="space-y-3" data-selected-exit={selected.id}>
          <h3 id="ed-selected" className="font-semibold">{T("ed.selected", { name: labelOf(exit) || selected.id })}</h3>
          <TextField label={T("ed.name")} name="exit-name" value={exit.label ? labelOf(exit) : exit.name ?? ""}
            onChange={(v) => { const { label: _l, ...rest } = exit; onChange({ ...plan, exits: { ...plan.exits, [selected.id]: { ...rest, name: v } } }); }} />
          <div>
            <label htmlFor="ed-kind" className="mb-1 block text-base text-muted-foreground">{T("ed.kind")}</label>
            <select id="ed-kind" value={exit.kind ?? "stair"} className={SELECT}
              onChange={(e) => onChange({ ...plan, exits: { ...plan.exits, [selected.id]: { ...exit, kind: e.target.value as "stair" | "exit" } } })}>
              <option value="stair">{T("ed.kind_stair")}</option>
              <option value="exit">{T("ed.kind_door")}</option>
            </select>
          </div>
          <DoorFields door={exit.door} box={exit} onChange={(door) => onChange({ ...plan, exits: { ...plan.exits, [selected.id]: { ...exit, door } } })} />
          <BoxFields box={exit} onChange={(b) => onChange(withBox(plan, selected, b, false))} />
          <Button type="button" variant="outline" onClick={() => { onChange(without(plan, selected)); onSelect(null); }}>{T("ed.remove")}</Button>
        </section>
      )}

      {other && selected && (
        <section aria-labelledby="ed-selected" className="space-y-3" data-selected-other={selected.id}>
          <h3 id="ed-selected" className="font-semibold">{T("ed.selected", { name: labelOf(other) || `#${Number(selected.id) + 1}` })}</h3>
          <TextField label={T("ed.name")} name="other-name" value={other.label ? labelOf(other) : other.name ?? ""}
            onChange={(v) => { const { label: _l, ...rest } = other; onChange({ ...plan, other: plan.other.map((o, i) => (i === Number(selected.id) ? { ...rest, name: v } : o)) }); }} />
          <BoxFields box={other} onChange={(b) => onChange(withBox(plan, selected, b, false))} />
          <Button type="button" variant="outline" onClick={() => { onChange(without(plan, selected)); onSelect(null); }}>{T("ed.remove")}</Button>
        </section>
      )}
    </div>
  );
}

/** Width x length in metres: the product is the floor area that is stored. */
function AreaFromSides({ onArea }: { onArea: (v: number) => void }) {
  const w = useId(), l = useId();
  const read = () => {
    const a = Number((document.getElementById(w) as HTMLInputElement | null)?.value), b = Number((document.getElementById(l) as HTMLInputElement | null)?.value);
    if (a > 0 && b > 0) onArea(Math.round(a * b * 10) / 10);
  };
  return (
    <div className="mt-1 grid grid-cols-2 gap-2">
      <div>
        <label htmlFor={w} className="mb-1 block text-base text-muted-foreground">{T("ed.width_m")}</label>
        <Input id={w} type="number" inputMode="decimal" step={0.1} min={0} className={FIELD} onChange={read} />
      </div>
      <div>
        <label htmlFor={l} className="mb-1 block text-base text-muted-foreground">{T("ed.length_m")}</label>
        <Input id={l} type="number" inputMode="decimal" step={0.1} min={0} className={FIELD} onChange={read} />
      </div>
    </div>
  );
}

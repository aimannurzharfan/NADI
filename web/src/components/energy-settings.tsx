// Energy settings: the values the waste figures are worked out from, as one full-width card of five tiles like the
// KPI row (label, value, unit). Everyone reads them, with who changed them last; an admin edits the tiles in place. A save lists every change first and applies from that second: earlier
// figures keep the earlier values (the server costs each stretch at the values in force while it ran).
import { useQueryClient } from "@tanstack/react-query";
import { History, Pencil, Plus, X } from "lucide-react";
import { useId, useState } from "react";

import { EXPANDED, ShowMore, useShowMore } from "@/components/list-limit";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, putJSON, useEnergySettings } from "@/lib/api";
import { dateTimeYear, hhmmss } from "@/lib/format";
import { LANG, T } from "@/lib/i18n";
import type { EnergyChanges, EnergyField, EnergySettings, EnergyValues } from "@/lib/types";
import { cn } from "@/lib/utils";

export const FIELDS: { key: EnergyField; label: string; unit: string; value: string; digits: number }[] = [
  { key: "tariff_rm_per_kwh", label: "es.tariff", unit: "es.unit_tariff", value: "es.val_tariff", digits: 4 },
  { key: "ac_kw", label: "es.ac_kw", unit: "es.unit_kw", value: "es.val_kw", digits: 2 },
  { key: "ac_on_below_c", label: "es.ac_on_below", unit: "es.unit_c", value: "es.val_c", digits: 1 },
  { key: "waste_after_min", label: "es.waste_after", unit: "es.unit_min", value: "es.val_min", digits: 1 },
  { key: "co2_kg_per_kwh", label: "es.co2", unit: "es.unit_co2", value: "es.val_co2", digits: 3 },
];
const FIELD = Object.fromEntries(FIELDS.map((f) => [f.key, f])) as Record<EnergyField, (typeof FIELDS)[number]>;
const ROOM = "ac_kw_rooms.";

/** 0.35, 10, 26.5: at most `digits` decimals, no trailing zeros. */
const plain = (x: number, digits: number) => String(Number(x.toFixed(digits)));

/** "RM 0.2983 per kWh", "10 kW", "26 °C", "10 minutes", "0.75 kg per kWh". */
export function valueText(key: EnergyField, x: number): string {
  if (key === "waste_after_min" && x === 1) return T("es.val_min_one");
  if (key === "ac_on_below_c") return T("es.val_c", { x: x.toFixed(1) });
  return T(FIELD[key].value, { x: plain(x, FIELD[key].digits) });
}

/** One line per changed value: "Electricity tariff: RM 0.2983 per kWh → RM 0.35 per kWh". A room's own power that
 *  was not set, or is removed, reads "building value". */
export function changeLines(changes: EnergyChanges, nameOf: (id: string) => string): string[] {
  return Object.entries(changes).map(([key, [before, after]]) => {
    const room = key.startsWith(ROOM) ? key.slice(ROOM.length) : null;
    const field: EnergyField = room != null ? "ac_kw" : (key as EnergyField);
    if (!FIELD[field]) return `${key}: ${before} → ${after}`;
    const text = (x: number | null) => (x == null ? T("es.not_set") : valueText(field, x));
    return T("es.change", { label: room != null ? T("es.room_kw_label", { name: nameOf(room) }) : T(FIELD[field].label),
      old: text(before), new: text(after) });
  });
}

type Form = Record<EnergyField, string> & { rooms: { id: string; value: string }[] };

export function formOf(s: EnergyValues): Form {
  const numbers = Object.fromEntries(FIELDS.map((f) => [f.key, plain(s[f.key], f.digits)])) as Record<EnergyField, string>;
  return { ...numbers, rooms: Object.entries(s.ac_kw_rooms).map(([id, v]) => ({ id, value: plain(v, 2) })) };
}

const parse = (text: string) => (/^\s*-?(\d+\.?\d*|\.\d+)\s*$/.test(text) ? Number(text) : NaN);

/** The same checks as the server (its limits come with the settings): {field: message}, and the values when valid. */
export function checkForm(form: Form, limits: EnergySettings["limits"], nameOf: (id: string) => string) {
  const errors: Record<string, string> = {};
  const values = { ac_kw_rooms: {} } as EnergyValues;
  const check = (key: string, text: string, field: EnergyField, label: string) => {
    const [min, max] = limits[field];
    const n = parse(text);
    if (Number.isNaN(n)) errors[key] = T("es.err_number", { label });
    else if (n < min || n > max) errors[key] = T("es.err_range", { label, min, max, unit: T(FIELD[field].unit) });
    return n;
  };
  for (const f of FIELDS) values[f.key] = check(f.key, form[f.key], f.key, T(f.label));
  for (const r of form.rooms) values.ac_kw_rooms[r.id] = check(ROOM + r.id, r.value, "ac_kw", nameOf(r.id));
  return { errors, values: Object.keys(errors).length ? null : values };
}

/** What differs between the values in force and the form, in the server's shape. */
export function diffOf(old: EnergyValues, next: EnergyValues): EnergyChanges {
  const out: EnergyChanges = {};
  const differs = (a: number, b: number) => Math.abs(a - b) > 1e-9;
  for (const f of FIELDS) if (differs(old[f.key], next[f.key])) out[f.key] = [old[f.key], next[f.key]];
  for (const id of [...new Set([...Object.keys(old.ac_kw_rooms), ...Object.keys(next.ac_kw_rooms)])].sort()) {
    const a = old.ac_kw_rooms[id] ?? null, b = next.ac_kw_rooms[id] ?? null;
    if (a == null || b == null ? a !== b : differs(a, b)) out[ROOM + id] = [a, b];
  }
  return out;
}

const INPUT = "h-10 w-full min-w-0 text-base tabular-nums";
const SELECT = "h-10 min-w-0 rounded-md border border-input bg-background px-3 text-base text-foreground";

/** The value of a tile without its unit: 0.2983, 10, 26.0, 10, 0.75. */
const plainValue = (key: EnergyField, x: number) => (key === "ac_on_below_c" ? x.toFixed(1) : plain(x, FIELD[key].digits));

/** The rule with the live values, for the foot of the card. */
export const ruleLine = (s: EnergyValues) => T("es.rule_line", {
  temp: s.ac_on_below_c.toFixed(1), delay: plain(s.waste_after_min, 1), kw: plain(s.ac_kw, 2),
  rate: plain(s.tariff_rm_per_kwh, 4), factor: plain(s.co2_kg_per_kwh, 3) });

export function EnergySettingsCard({ admin, rooms, className }: {
  /** an admin gets the Edit button */
  admin: boolean;
  /** every room that can have its own power: {room ID: name} */
  rooms: Record<string, string>;
  className?: string;
}) {
  const query = useEnergySettings();
  const qc = useQueryClient();
  const data = query.data;
  const [form, setForm] = useState<Form | null>(null);  // null: read-only
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<{ values: EnergyValues; changes: EnergyChanges } | null>(null);  // the confirmation
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState("");
  const [adding, setAdding] = useState("");
  const [perRoom, setPerRoom] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const uid = useId();
  const history = useShowMore(data?.history ?? []);
  const nameOf = (id: string) => rooms[id] ?? id;
  const free = Object.keys(rooms).filter((id) => !form?.rooms.some((r) => r.id === id))
    .sort((a, b) => nameOf(a).localeCompare(nameOf(b), undefined, { numeric: true }));
  const addId = free.includes(adding) ? adding : free[0] ?? "";

  function edit() {
    if (!data) return;
    setForm(formOf(data.settings));
    setErrors({});
    setNotice("");
    setFailure("");
  }

  function cancel() {
    setForm(null);
    setErrors({});
    setFailure("");
  }

  function review(e?: React.FormEvent) {
    e?.preventDefault();
    if (!data || !form) return;
    const checked = checkForm(form, data.limits, nameOf);
    setErrors(checked.errors);
    setFailure("");
    if (Object.keys(checked.errors).some((k) => k.startsWith("ac_kw_rooms."))) setPerRoom(true);  // show the problem
    if (!checked.values) return;
    const changes = diffOf(data.settings, checked.values);
    if (!Object.keys(changes).length) {
      setForm(null);
      setNotice(T("es.nothing"));
      return;
    }
    setPending({ values: checked.values, changes });
  }

  async function save() {
    if (!pending) return;
    setBusy(true);
    try {
      const out = await putJSON<EnergySettings & { changed: boolean }>(`/api/energy/settings?lang=${LANG}`, pending.values);
      qc.setQueryData(["energy-settings"], out);
      for (const key of ["energy", "info", "rooms", "audit"]) qc.invalidateQueries({ queryKey: [key] });
      setNotice(out.changed && out.effective_from ? T("es.saved", { time: hhmmss(out.effective_from) }) : T("es.nothing"));
      setForm(null);
      setErrors({});
    } catch (err) {
      if (err instanceof ApiError && err.errors) {
        setErrors(err.errors);  // each message lands under its tile
        if (Object.keys(err.errors).some((k) => k.startsWith("ac_kw_rooms."))) setPerRoom(true);
      } else setFailure(err instanceof ApiError && err.status === 503 ? err.message
        : T("es.err_save", { reason: err instanceof Error ? err.message : String(err) }));
    } finally {
      setBusy(false);
      setPending(null);
    }
  }

  const error = (key: string) => errors[key] && <p id={`${uid}-${key}-error`} role="alert" className="mt-1 text-base text-crit">{errors[key]}</p>;
  const input = (key: string, value: string, unit: string, label: string, onChange: (v: string) => void) => (
    <span className="flex items-center gap-2">
      <Input id={`${uid}-${key}`} name={key} type="text" inputMode="decimal" autoComplete="off" value={value} className={INPUT}
        aria-label={label} aria-invalid={errors[key] ? true : undefined}
        aria-describedby={cn(`${uid}-${key}-unit`, errors[key] && `${uid}-${key}-error`)}
        onChange={(e) => onChange(e.target.value)} />
      <span id={`${uid}-${key}-unit`} className="shrink-0 whitespace-nowrap text-base text-muted-foreground">{unit}</span>
    </span>
  );
  const source = !data ? null
    : data.source === "last_known" ? { text: T("es.last_known"), warn: true }
    : data.source === "defaults" && !data.database ? { text: T("es.cold_defaults"), warn: true }
    : data.effective_from != null && data.changed_by != null
      ? { text: T("es.changed_by", { who: data.changed_by, date: dateTimeYear(data.effective_from) }), warn: false }
      : { text: T("es.defaults"), warn: false };
  const ownRooms = data ? Object.entries(data.settings.ac_kw_rooms).sort((a, b) => nameOf(a[0]).localeCompare(nameOf(b[0]), undefined, { numeric: true })) : [];
  const roomCount = form ? form.rooms.length : ownRooms.length;
  const titleId = `${uid}-title`;

  return (
    <section aria-labelledby={titleId} data-energy-settings={form ? "edit" : "read"}
      className={cn("flex min-w-0 flex-col rounded-lg border bg-card shadow-panel", className)}>
      <header className="flex min-h-11 flex-wrap items-center gap-x-4 gap-y-1 border-b px-4 py-2">
        <h2 id={titleId} className="text-md font-semibold text-heading">{T("es.title")}</h2>
        {source && (
          <p data-settings-source={data!.source} className={cn("min-w-0 text-base", source.warn ? "font-medium text-warn" : "text-muted-foreground")}>{source.text}</p>
        )}
        <div className="ml-auto flex items-center gap-2">
          {data && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} aria-haspopup="dialog" data-open-history>
              <History aria-hidden />{T("es.history_link")}
            </Button>
          )}
          {admin && data && !form && (
            <Button type="button" variant="outline" size="sm" onClick={edit} data-edit-settings><Pencil aria-hidden />{T("es.edit")}</Button>
          )}
          {form && (
            <>
              <Button type="button" variant="outline" size="sm" onClick={cancel}>{T("es.cancel")}</Button>
              <Button type="submit" size="sm" form={`${uid}-form`} disabled={busy}>{T("es.save")}</Button>
            </>
          )}
        </div>
      </header>

      {query.isLoading && <div className="p-4"><Skeleton className="h-16 w-full" /></div>}
      {query.error && !data && <p role="alert" className="px-4 py-3 text-base text-crit">{T("common.load_failed")}</p>}
      {data && (
        <form id={`${uid}-form`} onSubmit={review} noValidate>
          <div className="grid grid-cols-2 border-b md:grid-cols-3 2xl:grid-cols-5" data-settings-tiles>
            {FIELDS.map((f) => (
              <div key={f.key} data-setting={f.key} className="flex min-w-0 flex-col gap-1 border-r px-4 py-3 last:border-r-0">
                {form ? (
                  <label htmlFor={`${uid}-${f.key}`} className="truncate text-base text-muted-foreground">{T(f.label)}</label>
                ) : (
                  <p className="truncate text-base text-muted-foreground">{T(f.label)}</p>
                )}
                {form ? (
                  <>
                    {input(f.key, form[f.key], T(f.unit), T(f.label), (v) => setForm({ ...form, [f.key]: v }))}
                    {error(f.key)}
                  </>
                ) : (
                  <p className="whitespace-nowrap text-2xl font-semibold leading-8 tabular-nums">
                    <span data-value>{plainValue(f.key, data.settings[f.key])}</span>
                    <span className="ml-1.5 text-base font-medium text-muted-foreground">{T(f.unit)}</span>
                  </p>
                )}
                {f.key === "ac_kw" && (roomCount > 0 || form) && (
                  <button type="button" onClick={() => setPerRoom((v) => !v)} aria-expanded={perRoom} aria-controls={`${uid}-rooms`}
                    data-per-room className="self-start text-base font-medium text-primary underline underline-offset-2 hover:text-heading">
                    {T("es.per_room", { n: roomCount })}
                  </button>
                )}
              </div>
            ))}
          </div>

          {perRoom && (
            <div id={`${uid}-rooms`} data-own-rooms className="border-b px-4 py-3 text-base">
              <p className="mb-2 font-medium">{T("es.rooms_own")}</p>
              {!form && (
                ownRooms.length ? (
                  <ul className="flex flex-wrap gap-x-6 gap-y-1">
                    {ownRooms.map(([id, kw]) => (
                      <li key={id} data-setting={ROOM + id}><span className="text-muted-foreground">{nameOf(id)}</span> <b className="tabular-nums">{valueText("ac_kw", kw)}</b></li>
                    ))}
                  </ul>
                ) : <p className="text-muted-foreground">{T("es.rooms_none")}</p>
              )}
              {form && (
                <>
                  {!form.rooms.length && <p className="text-muted-foreground">{T("es.rooms_none")}</p>}
                  <ul className="grid gap-x-6 gap-y-2 md:grid-cols-2 2xl:grid-cols-3">
                    {form.rooms.map((r, i) => (
                      <li key={r.id}>
                        <div className="flex items-center gap-2">
                          <label htmlFor={`${uid}-${ROOM}${r.id}`} className="w-32 shrink-0 truncate">{nameOf(r.id)}</label>
                          {input(ROOM + r.id, r.value, T("es.unit_kw"), nameOf(r.id),
                            (v) => setForm({ ...form, rooms: form.rooms.map((x, j) => (j === i ? { ...x, value: v } : x)) }))}
                          <Button type="button" variant="ghost" size="icon" aria-label={T("es.remove_room", { name: nameOf(r.id) })}
                            title={T("es.remove_room", { name: nameOf(r.id) })}
                            onClick={() => setForm({ ...form, rooms: form.rooms.filter((_, j) => j !== i) })}><X aria-hidden /></Button>
                        </div>
                        {error(ROOM + r.id)}
                      </li>
                    ))}
                  </ul>
                  {error("ac_kw_rooms")}
                  {free.length > 0 && form.rooms.length < data.max_rooms && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <label htmlFor={`${uid}-add`} className="sr-only">{T("es.add_room_pick")}</label>
                      <select id={`${uid}-add`} value={addId} onChange={(e) => setAdding(e.target.value)} className={SELECT} data-add-room>
                        {free.map((id) => <option key={id} value={id}>{nameOf(id)}</option>)}
                      </select>
                      <Button type="button" variant="outline" size="sm"
                        onClick={() => setForm({ ...form, rooms: [...form.rooms, { id: addId, value: form.ac_kw }] })}>
                        <Plus aria-hidden />{T("es.add_room")}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </form>
      )}
      {failure && <p role="alert" className="border-b px-4 py-2 text-base text-crit">{failure}</p>}
      {notice && !form && <p role="status" data-settings-notice className="border-b px-4 py-2 text-base font-medium">{notice}</p>}
      {data && <p data-rule-line className="px-4 py-2 text-base text-muted-foreground">{ruleLine(data.settings)}</p>}

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl" data-settings-history>
          <SheetHeader>
            <SheetTitle>{T("es.history")}</SheetTitle>
            <SheetDescription>{T("es.history_hint")}</SheetDescription>
          </SheetHeader>
          {data && (!data.history.length ? <p className="mt-4 text-base text-muted-foreground">{T("es.history_none")}</p> : (
            <div className="mt-4">
              <div id={`${uid}-history-rows`} className={cn(history.expanded && EXPANDED)}>
                <table className="w-full text-base">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th scope="col" className="py-2 pr-3 font-medium">{T("es.col_when")}</th>
                      <th scope="col" className="py-2 pr-3 font-medium">{T("es.col_who")}</th>
                      <th scope="col" className="py-2 font-medium">{T("es.col_what")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.shown.map((h) => (
                      <tr key={h.id} className="border-b align-top last:border-b-0">
                        <td className="whitespace-nowrap py-2 pr-3 tabular-nums">{dateTimeYear(h.effective_from)}</td>
                        <td className="py-2 pr-3 font-medium">{h.changed_by}</td>
                        <td className="py-2"><ul>{changeLines(h.changes, nameOf).map((line) => <li key={line}>{line}</li>)}</ul></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ShowMore hidden={history.hidden} expanded={history.expanded} onToggle={history.toggle} controls={`${uid}-history-rows`} />
            </div>
          ))}
        </SheetContent>
      </Sheet>

      <Dialog open={!!pending} onOpenChange={(open) => { if (!open && !busy) setPending(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{T("es.confirm_title")}</DialogTitle>
            <DialogDescription>{T("es.confirm_note")}</DialogDescription>
          </DialogHeader>
          <ul className="list-disc space-y-1 pl-5 text-base" data-settings-changes>
            {pending && changeLines(pending.changes, nameOf).map((line) => <li key={line}>{line}</li>)}
          </ul>
          <DialogFooter className="mt-2">
            <Button type="button" variant="outline" onClick={() => setPending(null)} disabled={busy}>{T("es.cancel")}</Button>
            <Button type="button" onClick={save} disabled={busy} data-confirm-save>{T("es.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

export type Waste = { since: number; minutes: number; rm: number; kwh?: number };

export type Room = {
  room_id: string;
  name: string;
  headcount: number | null; // 0 to 1000
  at_least: boolean; // the count is a minimum (CSI's "3 or more")
  counter?: "csi" | "count"; // "count": an exact counter (phase 2, simulated in the demo), never Wi-Fi sensing
  count_ts: number | null;
  temp_c: number | null;
  humidity: number | null;
  live: boolean;
  waste: Waste | null;
};

export type AlertKind = "emergency" | "waste" | "info" | "sensor" | "drill";

export type Alert = {
  id: string;
  ts: number;
  kind: AlertKind;
  severity: "critical" | "warning" | "info";
  via: string;
  subject: string;
  message: string;
  ack?: { by: string; ts: number } | null;
  drill?: boolean;
};

/** A warden's mark on a room during an emergency or drill. */
export type Mark = { status: "clear" | "help"; by: string; ts: number };

export type Emergency = { on: boolean; since: number | null; drill?: boolean; id?: string | null };

export type RoomsState = {
  now: number;
  stale_s: number;
  rooms: Room[];
  waste_today_rm: number;
  /** the same waste as energy (from the server, so it stays right when the tariff changes) */
  waste_today_kwh?: number;
  emergency: Emergency;
  accountability?: Record<string, Mark>;
  alerts: Alert[];
  offline: Partial<Record<"redis" | "mysql" | "mqtt", number | null>>;
  stale_ts: number | null;
  demo: { on: boolean; t: number | null; length?: number };
  clock?: { offset_s: number; checked: number } | null;
};

export type Info = {
  mode: "local" | "huawei";
  built_with: string[];
  chat_model: string;
  /** who would word an answer right now: the rules alone, or a language model that rephrases the checked answer */
  chat_source?: "rules" | "ollama" | "maas";
  building: string;
  level: string;
  room_names: Record<string, string>;
  /** every room drawn on a real floor: which floor, and its nearest exit by name */
  room_floors?: Record<string, string>;
  room_exits?: Record<string, string | null>;
  admin: "token" | "localhost" | "refused";
  headcount_source: string;
  /** what is counting people right now, and the trained model's own facts (null: no model file) */
  detector?: { mode: "rule" | "model"; threshold: number | null; model: ModelFacts | null };
  waste_minutes: number;
  /** colder than this = air conditioning counts as on (the live energy setting) */
  ac_on_below_c?: number;
  demo: boolean;
  emergency_number: string | null; // EMERGENCY_NUMBER from .env, or null for the default in the page's language
  timezone: string;
};

/** Sensor uptime today: per room, the seconds its sensor was reporting out of the seconds since its first report
 *  today. Offline time is counted by the rule that shows "offline" on the dashboard (no report for stale_s). */
export type Uptime = {
  now: number;
  since: number;
  stale_s: number;
  rooms: Record<string, { first_ts: number | null; up_s: number; expected_s: number }>;
  pct: number | null;
};

export type History = { now: number; bucket_s: number | null; rooms: Record<string, [number, number][]>;
  /** with room=: the buckets in which that room was empty and colder than the "counts as on" temperature */
  waste?: number[] };

/** One room for the people chart (GET /api/history?room=&view=people): [bucket start, peak count, minutes with
 *  someone inside]; buckets with no report are left out (gaps). since: whether the latest stored report has someone
 *  inside and when that unbroken state began (ts null: unchanged for 30 days); null when the room never reported. */
export type People = { now: number; bucket_s: number; room_id: string; people: [number, number, number][];
  since: { occupied: boolean; ts: number | null } | null };

export type Amounts = { rm: number; kwh: number; co2_kg: number };
/** One period of air conditioning waste. previous: the period of the same length before, null when nothing was
 *  reported then. Points before the first report (and hours still to come today) have rm null. */
export type EnergyPeriod = {
  id: "today" | "7d" | "30d"; days: number; total: Amounts; previous: Amounts | null;
  /** hours: empty with the air conditioning on (the room's kWh divided by its air conditioner's power) */
  by_room: { room_id: string; name: string; rm: number; kwh: number; hours: number }[];
  series: { unit: "hour"; points: { ts: number; rm: number | null }[] } | { unit: "day"; points: { day: string; rm: number | null }[] };
  /** the room the series is of, or null for the building */
  series_room: string | null;
  first_ts: number | null;
};
export type Energy = {
  now: number;
  today: Amounts;
  week: Amounts;
  previous_week: Amounts;
  yesterday: Amounts;
  by_room: { room_id: string; name: string; rm_today: number; rm_week: number }[];
  daily: { day: string; rm: number }[];
  /** the period chosen on the Energy page (GET /api/energy?range=) */
  range: EnergyPeriod;
  tariff_rm_per_kwh: number;
  ac_kw: number;
  co2_kg_per_kwh: number;
  /** saves of the energy settings in the last 14 days, oldest first: figures before them used the earlier values */
  rate_changes?: { ts: number; by: string }[];
  stale_ts: number | null;
};

/** The values the waste figures are worked out from (GET /api/energy/settings). */
export type EnergyValues = {
  tariff_rm_per_kwh: number;
  ac_kw: number;
  /** rooms whose air conditioner has its own power: {room ID: kW} */
  ac_kw_rooms: Record<string, number>;
  ac_on_below_c: number;
  waste_after_min: number;
  co2_kg_per_kwh: number;
};
export type EnergyField = Exclude<keyof EnergyValues, "ac_kw_rooms">;
/** {field: [old, new]}; a room's own power is "ac_kw_rooms.<room ID>", with null for "not set" */
export type EnergyChanges = Record<string, [number | null, number | null]>;
export type EnergySettings = {
  now: number;
  settings: EnergyValues;
  effective_from: number | null;
  changed_by: string | null;
  /** "defaults": the server configuration; "last_known": the database is offline, the values read earlier apply */
  source: "database" | "defaults" | "last_known";
  database: boolean;
  limits: Record<EnergyField, [number, number]>;
  max_rooms: number;
  history: { id: number; effective_from: number; changed_by: string; settings: EnergyValues; changes: EnergyChanges }[];
  history_total: number;
};

export type Device = {
  device_id: string;
  service: "csi" | "climate" | "count" | null;
  room_id: string | null;
  rooms: string[];
  retired: boolean;
  name: string | null;
  last_seen: number | null;
  online: boolean;
  simulator: boolean;
  fw_version: string | null;
  uptime_s: number | null;
  wifi_rssi: number | null;
  free_heap: number | null;
  dropped: number | null;
  n_packets: number | null;
};
export type Devices = { now: number; devices: Device[]; report_interval_s: number; retired_hidden: number };

export type Me = {
  admin: boolean; who: string | null; rule: Info["admin"]; status?: number; viewer: boolean; viewer_required: boolean;
};

export type Page<K extends string, T> = Record<K, T[]> & { total: number; limit: number; offset: number };

export type AuditEntry = {
  ts: number;
  action: "start" | "end" | "room_clear" | "room_help" | "room_reset" | "delete_all" | "energy_settings"
    | "plan_save" | "plan_restore" | "site_add" | "site_rename" | "plan_image";
  /** plan and site changes: the floor, and the version a save or restore made */
  floor?: string;
  version?: number;
  by: string;
  ip: string;
  /** plan_save: the rooms whose capacity changed, as [room, old, new] (null: not set) */
  capacity?: [string, number | null, number | null][];
  /** energy_settings: every changed value, old and new */
  changes?: EnergyChanges;
  started?: number;
  drill?: boolean;
  room?: string;
};

export type IncidentSummary = {
  id: string; kind: "real" | "drill"; started: number; ended: number; duration_s: number; started_by: string;
  ended_by: string; start_total: number; start_at_least: boolean; demo: boolean; marked: number; offline_rooms: number;
};

export type Incidents = {
  incidents: IncidentSummary[];
  active: { id: string; drill: boolean; since: number; snapshots: number; last_snapshot: number | null } | null;
};

export type ReportRoom = {
  room_id: string; name: string; start_count: number | null; start_at_least: boolean; start_live: boolean;
  empty_at_start: boolean; zero_ts: number | null; to_zero_s: number | null; end_count: number | null; end_at_least?: boolean; end_live: boolean;
  status: Mark | null;
};

export type Report = Omit<IncidentSummary, "marked" | "offline_rooms"> & {
  building: string; level: string; start_unknown: string[]; rooms: ReportRoom[];
  offline: { room_id: string; name: string; periods: [number, number | null][] }[];
  alerts: (Omit<Alert, "via">)[]; snapshots: number[];
};

/** source "fallback": the checked answer as the rules built it; "ollama" / "maas": a model reworded it. */
export type ChatAnswer = { answer: string; source: string; model: string;
  /** what the answer covers: one floor or the whole building (locked during an emergency or drill) */
  scope?: { kind: "floor" | "building"; floor_id: string | null; label: string; locked: boolean; reason: string | null } };

export type LabelView = {
  recent: { room_id: string; name: string; start_ts: number; end_ts: number | null; headcount: number }[];
  open: Record<string, { headcount: number; start_ts: number }>;
};

export type BoardSetup = { ip: string | null; port: number; configured_ip: string | null; mismatch: boolean };

/** One stored CSI report of a room: the motion figure and the headcount it was given. */
export type SignalPoint = { ts: number; motion_std: number; headcount: number };

/** GET /api/rooms/{id}/signal. threshold is null while a trained model is counting (there is no single line to draw). */
export type Signal = {
  now: number; room_id: string; minutes: number; threshold: number | null; points: SignalPoint[]; last_report_ts: number | null;
};

/** GET /api/signals: every sensing room's signal in one answer (the overview asks once per poll, not once per room). */
export type Signals = { now: number; minutes: number; threshold: number | null; rooms: Record<string, Signal>; truncated: boolean };

/** One stored report that fell inside a label segment: what the person counted and what the sensor measured. */
export type DetectorPoint = { ts: number; headcount_label: number; motion_std: number };

/** What the trained model file says about itself (written by ml/train.py), and whether it is counting now. */
export type ModelFacts = {
  framework: string | null; platform: string | null; trained_on: string | null; accuracy: number | null;
  threshold_accuracy: number | null; trained_at: number | null; n_train: number | null; n_test: number | null; active: boolean;
};

/** GET /api/detector. mode "model" only while a trained model file is loaded; threshold only in rule mode. */
export type Detector = {
  now: number; mode: "rule" | "model"; threshold: number | null; report_interval_s: number;
  rooms: Record<string, DetectorPoint[]>; model: ModelFacts | null;
};

/** A recorded stretch of per-packet signal strength between a room's two boards (web/public/recordings). */
export type Recording = {
  room_id: string; name: string; kind: string; date: string; distance_m: number | null;
  packets: number; duration_ms: number; std_db: number; mean_dbm: number;
  /** [milliseconds since the start, RSSI in dBm] per packet */
  points: [number, number][];
};

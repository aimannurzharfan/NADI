// Calls to the NADI server. Admin features send the token kept for this browser tab (sessionStorage); on the server
// computer itself no token is needed when ADMIN_TOKEN is empty (local mode).
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { LANG } from "./i18n";
import { cleanRecording, isRecordingFile } from "./recordings";
import type {
  AuditEntry, BoardSetup, Detector, Devices, Energy, EnergySettings, History, Incidents, Info, LabelView, Me, Page, People, Recording, Report, RoomsState, Signal, Signals, Uptime, Alert,
} from "./types";

const TOKEN_KEY = "nadiAdminToken";
const VIEWER_KEY = "nadiViewerToken";
const TIMEOUT_MS = 6000;

export function adminToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setAdminToken(token: string) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token.trim());
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the token lasts until the page is closed */
  }
}

export function viewerToken(): string {
  try {
    return sessionStorage.getItem(VIEWER_KEY) || "";
  } catch {
    return "";
  }
}

export function setViewerToken(token: string) {
  try {
    if (token) sessionStorage.setItem(VIEWER_KEY, token.trim());
    else sessionStorage.removeItem(VIEWER_KEY);
  } catch {
    /* private mode */
  }
}

export class ApiError extends Error {
  /** errors: a message per field, when the server refused a form (422) */
  constructor(public status: number, message: string, public errors?: Record<string, string>, public errorList?: unknown[]) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown, timeoutMs = TIMEOUT_MS): Promise<T> {
  const headers: Record<string, string> = { "X-Admin-Token": adminToken(), "X-Viewer-Token": viewerToken() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs) });
  } catch (e) {
    throw new ApiError(0, e instanceof Error ? e.message : String(e));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `HTTP ${res.status}`;
    // a form's refusal: a message per field (energy settings), or a list of problems (floor plans)
    const list = Array.isArray(data?.errors) ? (data.errors as unknown[]) : undefined;
    const errors = !list && data?.errors && typeof data.errors === "object" ? (data.errors as Record<string, string>) : undefined;
    throw new ApiError(res.status, detail, errors, list);
  }
  return data as T;
}

export const getJSON = <T,>(url: string) => request<T>("GET", url);
export const postJSON = <T,>(url: string, body?: unknown, timeoutMs?: number) => request<T>("POST", url, body ?? {}, timeoutMs);
export const putJSON = <T,>(url: string, body: unknown) => request<T>("PUT", url, body);

// ---------- hooks ----------

export const useRooms = () =>
  useQuery({ queryKey: ["rooms", LANG], queryFn: () => getJSON<RoomsState>(`/api/rooms?lang=${LANG}`), refetchInterval: 5000 });

export const useInfo = () =>
  useQuery({ queryKey: ["info", LANG], queryFn: () => getJSON<Info>(`/api/info?lang=${LANG}`), refetchInterval: 60000 });

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: () => getJSON<Me>("/api/me"), refetchInterval: 30000 });

export const useHistory = (minutes: number, room?: string, opts: { enabled?: boolean; refetchMs?: number } = {}) =>
  useQuery({
    queryKey: ["history", minutes, room ?? ""],
    queryFn: () => getJSON<History>(`/api/history?minutes=${minutes}${room ? `&room=${encodeURIComponent(room)}` : ""}`),
    refetchInterval: opts.refetchMs ?? (minutes <= 60 ? 20000 : 60000),
    enabled: opts.enabled ?? true,
  });

/** One room's people over time, with since when it has been empty or occupied (the people card). */
export const usePeople = (room: string, minutes: number, opts: { enabled?: boolean; refetchMs?: number } = {}) =>
  useQuery({
    queryKey: ["people", room, minutes],
    queryFn: () => getJSON<People>(`/api/history?minutes=${minutes}&room=${encodeURIComponent(room)}&view=people`),
    refetchInterval: opts.refetchMs ?? 60000,
    enabled: (opts.enabled ?? true) && !!room,
    placeholderData: (before) => (before && before.room_id === room ? before : undefined),
  });

export const useClimate = (room: string, minutes: number) =>
  useQuery({
    queryKey: ["climate", room, minutes],
    queryFn: () => getJSON<{ points: [number, number | null, number | null][] }>(
      `/api/rooms/${encodeURIComponent(room)}/climate?minutes=${minutes}`),
    refetchInterval: 60000,
    enabled: !!room,
  });

/** The motion figure of one room's last reports (the live signal chart and the room's sparkline share one request). */
export const useSignal = (room: string, minutes = 5, enabled = true) =>
  useQuery({
    queryKey: ["signal", room, minutes],
    queryFn: () => getJSON<Signal>(`/api/rooms/${encodeURIComponent(room)}/signal?minutes=${minutes}`),
    refetchInterval: 5000,
    enabled: enabled && !!room,
  });

/** Every sensing room's last minutes in ONE request: the overview's tiles, sensing lines and live signal chart all
 *  read from it, so the number of rooms never multiplies the number of requests. */
export const useSignals = (enabled = true) =>
  useQuery({ queryKey: ["signals"], queryFn: () => getJSON<Signals>("/api/signals?minutes=5"), refetchInterval: 5000, enabled });

/** Sensor uptime today (the server works it out from the gaps between the stored reports). */
export const useUptime = () =>
  useQuery({ queryKey: ["uptime"], queryFn: () => getJSON<Uptime>("/api/uptime"), refetchInterval: 30000 });

/** room: the Energy page's room filter (the period's chart is then that room's; the figures stay the building's). */
export const useEnergy = (range: "today" | "7d" | "30d" = "7d", room = "") =>
  useQuery({ queryKey: ["energy", range, room],
    queryFn: () => getJSON<Energy>(`/api/energy?range=${range}${room ? `&room=${encodeURIComponent(room)}` : ""}`), refetchInterval: 30000,
    placeholderData: (before) => before });

/** The energy settings in force, their limits and the change history. Everyone may read them. */
export const useEnergySettings = () =>
  useQuery({ queryKey: ["energy-settings"], queryFn: () => getJSON<EnergySettings>("/api/energy/settings"), refetchInterval: 30000 });

export const ALERTS_PAGE = 50;

export const useAlerts = (page = 0) =>
  useQuery({
    queryKey: ["alerts", LANG, page],
    queryFn: () => getJSON<Page<"alerts", Alert>>(`/api/alerts?lang=${LANG}&limit=${ALERTS_PAGE}&offset=${page * ALERTS_PAGE}`),
    refetchInterval: 10000,
  });

export const useDevices = (enabled: boolean, retired = false) =>
  useQuery({ queryKey: ["devices", retired], queryFn: () => getJSON<Devices>(`/api/devices${retired ? "?retired=true" : ""}`),
    refetchInterval: 10000, enabled });

export const useAudit = (enabled: boolean) =>
  useQuery({ queryKey: ["audit"], queryFn: () => getJSON<Page<"audit", AuditEntry>>("/api/audit?limit=100"), refetchInterval: 15000, enabled });

export const useBoardSetup = (enabled: boolean) =>
  useQuery({ queryKey: ["board-setup"], queryFn: () => getJSON<BoardSetup>("/api/board-setup"), enabled, retry: false });

export const useLabels = (enabled: boolean) =>
  useQuery({ queryKey: ["labels"], queryFn: () => getJSON<LabelView>("/api/labels"), enabled });

/** What is counting right now and the labelled reports, for the calibration page (admin). */
export const useDetector = (enabled: boolean) =>
  useQuery({ queryKey: ["detector"], queryFn: () => getJSON<Detector>("/api/detector"), refetchInterval: 15000, enabled });

/** The recorded waves of one room: static files that ship with the console. None is the normal case. */
export const useRecordings = (room: string, enabled = true) =>
  useQuery({
    queryKey: ["recordings", room],
    queryFn: async (): Promise<Recording[]> => {
      const index = await getJSON<{ recordings?: { room_id?: string; file?: string }[] }>("/recordings/index.json");
      const files = (Array.isArray(index.recordings) ? index.recordings : [])
        .filter((r) => r && r.room_id === room && isRecordingFile(r.file)).slice(0, 4);
      const all = await Promise.all(files.map((f) => getJSON<unknown>(`/recordings/${f.file}`).catch(() => null)));
      return all.map((r) => cleanRecording(r, room)).filter((r): r is Recording => r !== null);
    },
    enabled: enabled && !!room, staleTime: Infinity, retry: false,
  });

export const useIncidents = () =>
  useQuery({ queryKey: ["incidents"], queryFn: () => getJSON<Incidents>("/api/incidents"), refetchInterval: 15000 });

export const useReport = (id: string) =>
  useQuery({ queryKey: ["report", id, LANG], queryFn: () => getJSON<Report>(`/api/incidents/${encodeURIComponent(id)}?lang=${LANG}`),
    enabled: !!id, retry: false });

/** A saved snapshot page from the server, opened in a new tab (fetched with the tokens, so it works with VIEWER_TOKEN). */
export async function openSnapshot(id: string, ts: number | "latest" = "latest") {
  const tab = window.open("", "_blank");
  const res = await fetch(`/api/incidents/${encodeURIComponent(id)}/snapshot?ts=${ts}&lang=${LANG}`,
    { headers: { "X-Admin-Token": adminToken(), "X-Viewer-Token": viewerToken() } });
  if (!res.ok) {
    tab?.close();
    throw new ApiError(res.status, `HTTP ${res.status}`);
  }
  const url = URL.createObjectURL(new Blob([await res.text()], { type: "text/html" }));
  if (tab) tab.location.href = url;
  else window.location.href = url;
}

/** After signing in or out, every admin view refreshes. */
export function useRefreshAdmin() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["me", "devices", "audit", "board-setup", "labels", "alerts", "detector"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

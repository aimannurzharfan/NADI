// The people chart's time range: the last hour (a point a minute), 24 hours (30 minutes), 7 days (3 hours) or 30 days
// (a day). The choice is kept in the address (?range=, with ?room=) and in this browser (localStorage, which may be
// blocked: then it is simply not kept). An older stored choice that no longer exists ("5m") falls back to the default.
export const PEOPLE_RANGES = ["1h", "24h", "7d", "30d"] as const;
export type PeopleRange = (typeof PEOPLE_RANGES)[number];
/** A new install and a live demonstration have minutes of data, not days: the hour shows a walk in within a minute. */
export const DEFAULT_RANGE: PeopleRange = "1h";
export const RANGE_KEY = "nadiSignalRange";

export const PEOPLE_MINUTES: Record<PeopleRange, number> = { "1h": 60, "24h": 24 * 60, "7d": 7 * 24 * 60, "30d": 30 * 24 * 60 };
/** Seconds per point, as the server answers them (GET /api/history?view=people). */
export const PEOPLE_BUCKET_S: Record<PeopleRange, number> = { "1h": 60, "24h": 1800, "7d": 3 * 3600, "30d": 86400 };

export const isRange = (v: string | null | undefined): v is PeopleRange => !!v && (PEOPLE_RANGES as readonly string[]).includes(v);

export function storedRange(): PeopleRange | null {
  try {
    const v = localStorage.getItem(RANGE_KEY);
    return isRange(v) ? v : null;
  } catch {
    return null;
  }
}

export function storeRange(r: PeopleRange) {
  try {
    localStorage.setItem(RANGE_KEY, r);
  } catch {
    /* not kept */
  }
}

/** The address first, then this browser's last choice, then the last hour. */
export const pickRange = (fromUrl: string | null, stored: PeopleRange | null): PeopleRange =>
  isRange(fromUrl) ? fromUrl : stored ?? DEFAULT_RANGE;

/** How often a people chart asks again: every 20 s on the hour (the count beside it is live), otherwise no faster
 *  than one of its points and at most every 5 minutes. */
export const peopleRefetchMs = (range: PeopleRange) => (range === "1h" ? 20 : Math.min(300, PEOPLE_BUCKET_S[range])) * 1000;

// The Energy page's period: today, the last 7 days or the last 30 days. It drives the figures at the top and both
// charts. Kept in the address (?range=) and in this browser (localStorage, which may be blocked: then not kept).
export const ENERGY_RANGES = ["today", "7d", "30d"] as const;
export type EnergyRange = (typeof ENERGY_RANGES)[number];
export const DEFAULT_ENERGY_RANGE: EnergyRange = "7d";
export const ENERGY_RANGE_KEY = "nadiEnergyRange";

export const isEnergyRange = (v: string | null | undefined): v is EnergyRange =>
  !!v && (ENERGY_RANGES as readonly string[]).includes(v);

export function storedEnergyRange(): EnergyRange | null {
  try {
    const v = localStorage.getItem(ENERGY_RANGE_KEY);
    return isEnergyRange(v) ? v : null;
  } catch {
    return null;
  }
}

export function storeEnergyRange(r: EnergyRange) {
  try {
    localStorage.setItem(ENERGY_RANGE_KEY, r);
  } catch {
    /* not kept */
  }
}

/** The address first, then this browser's last choice, then 7 days. */
export const pickEnergyRange = (fromUrl: string | null, stored: EnergyRange | null): EnergyRange =>
  isEnergyRange(fromUrl) ? fromUrl : stored ?? DEFAULT_ENERGY_RANGE;

/** "+RM 0.40 vs yesterday", or "Same as yesterday" when the difference rounds to nothing. */
export function changeText(delta: number, range: EnergyRange, t: (key: string) => string): string {
  if (Math.abs(delta) < 0.005) return t(`energy.same_${range}`);
  return `${delta > 0 ? "+" : "−"}RM ${Math.abs(delta).toFixed(2)} ${t(`energy.vs_${range}`)}`;
}

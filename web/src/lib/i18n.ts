// All wording comes from dashboard/strings.json (English and Malay), bundled at build time so the console works offline.
// ?lang=ms shows the Malay interface. Room names and alert text from the server are always shown as text, never HTML.
import strings from "@strings";

type Entry = { en: string; ms: string };
const S = strings as unknown as Record<string, Entry>;

export type Lang = "en" | "ms";
export const LANG: Lang =
  typeof location !== "undefined" && new URLSearchParams(location.search).get("lang") === "ms" ? "ms" : "en";

export type Vars = Record<string, string | number>;

/** T("plan.title", { level: "Level 4" }) gives "Level 4 floor plan". A missing key shows the key itself. */
export function T(key: string, vars?: Vars, lang: Lang = LANG): string {
  const entry = S[key];
  const text = entry ? entry[lang] : key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : text;
}

export function hasKey(key: string) {
  return key in S;
}

/** The same page in the other language. */
export function otherLangHref(): string {
  const params = new URLSearchParams(location.search);
  if (LANG === "ms") params.delete("lang");
  else params.set("lang", "ms");
  const q = params.toString();
  return location.pathname + (q ? `?${q}` : "");
}

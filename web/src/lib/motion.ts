// When the overview may move. Animation is data-driven: something animates once when its data changes and is still
// otherwise. With "reduce motion" on, or during an emergency or drill, nothing animates at all.
import { useEffect, useRef, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches;
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(QUERY);
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduced;
}

/** How many newer reports have arrived since this component first rendered. `ts` is a report time: only a time later
 *  than every one seen before counts, so a late or repeated answer (two requests poll independently) never replays an
 *  animation, and the first time to appear is page load, not news. */
export function useNewer(ts: number | null | undefined): number {
  const seen = useRef<{ max: number | null; n: number }>({ max: ts ?? null, n: 0 });
  if (ts != null && (seen.current.max == null || ts > seen.current.max)) {
    seen.current = { max: ts, n: seen.current.n + (seen.current.max == null ? 0 : 1) };
  }
  return seen.current.n;
}

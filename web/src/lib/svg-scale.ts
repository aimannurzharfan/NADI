// Drawn text never below 14 px on screen. A plan is an SVG scaled to its box, so a label's size in drawing units is
// raised to MIN_PX divided by that scale (measured, and again whenever the box changes size).
import { useLayoutEffect, useState, type RefObject } from "react";

export const MIN_PX = 14.25;

/** On-screen pixels per drawing unit of the svg (1 until measured, and in tests where nothing has a size). */
export function useSvgScale(ref: RefObject<SVGSVGElement>, width: number) {
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const measure = () => {
      const w = svg.getBoundingClientRect().width;
      if (w > 0) setScale(w / width);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(svg);
    return () => ro.disconnect();
  }, [ref, width]);
  return scale;
}

/** The size in drawing units for `px`, never under 14.25 px on screen. */
export const atLeast = (px: number, scale: number) => Math.max(px, MIN_PX / scale);

// Adapted from Magic UI's "Number Ticker" (magicui.design, MIT licence): a number that rolls to its new value.
// Changes for NADI: it starts at the current value (no count-up on page load), rolls only when the value changes,
// takes a formatter ("3+", "100+"), and with `still` it changes instantly.
import { useMotionValue, useSpring } from "motion/react";
import { useEffect, useRef } from "react";

type NumberTickerProps = {
  value: number;
  format?: (n: number) => string;
  still?: boolean;
  className?: string;
};

export function NumberTicker({ value, format = String, still = false, className }: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const formatRef = useRef(format);
  formatRef.current = format;
  const first = useRef(format(value));  // React writes the text once; after that only the spring (or `still`) does
  const target = useMotionValue(value);
  const spring = useSpring(target, { damping: 28, stiffness: 170 });

  const last = useRef(value);
  useEffect(() => {
    const changed = last.current !== value;
    last.current = value;
    if (still) {
      target.jump(value);
      spring.jump(value);
      if (ref.current) ref.current.textContent = formatRef.current(value);
    } else if (changed) {
      target.set(value);  // the spring follows and writes each step
    } else if (ref.current && !spring.isAnimating()) {
      ref.current.textContent = formatRef.current(value);  // same number, new wording ("3" to "3+")
    }
  });

  useEffect(() => spring.on("change", (latest: number) => {
    if (ref.current) ref.current.textContent = formatRef.current(Math.round(latest));
  }), [spring]);

  return <span ref={ref} aria-hidden className={className}>{first.current}</span>;
}

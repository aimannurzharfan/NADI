// The sensing pair of one room as a picture: the sender, the receiver and the Wi-Fi signal between them.
//   calm       even waves: the latest report is below the threshold
//   disturbed  a person in the path and choppy, scattered waves: the latest report is above it
//   offline    a grey, still, dashed line: the sensor is not reporting
//   waiting    a plain line: the sensor is live but no report is in the window yet
// It is an illustration, not a measurement; which picture shows comes only from the room's latest real report, which
// the caption under it gives. The waves travel once when a new report arrives and are still otherwise; never during an emergency or
// drill, or with "reduce motion".
import { useId } from "react";

import { T } from "@/lib/i18n";
import { useNewer } from "@/lib/motion";
import type { Room, Signal } from "@/lib/types";

export type PairState = "calm" | "disturbed" | "offline" | "waiting";

export function pairState(room: Pick<Room, "live">, signal: Signal | undefined): PairState {
  if (!room.live) return "offline";
  const last = signal?.points[signal.points.length - 1];
  if (!signal || !last) return "waiting";
  // a trained model has no single threshold: the picture follows the count that report was given
  return (signal.threshold != null ? last.motion_std > signal.threshold : last.headcount > 0) ? "disturbed" : "calm";
}

export function pairCaption(state: PairState, signal: Signal | undefined): string {
  const last = signal?.points[signal.points.length - 1];
  if (state === "offline") return T("sig.offline");
  if (state === "waiting" || !last) return T("sig.waiting", { minutes: signal?.minutes ?? 5 });
  const x = last.motion_std.toFixed(2);
  if (signal?.threshold == null) return T(state === "calm" ? "sig.calm_model" : "sig.disturbed_model", { x });
  return T(state === "calm" ? "sig.calm" : "sig.disturbed", { x, t: signal.threshold.toFixed(2) });
}

const W = 400, H = 110, Y = 55, LEFT = 64, RIGHT = 336, MID = 200, PERIOD = 34;
const BRAND = "hsl(var(--brand))";
const OFF = "hsl(var(--off))";

/** A wave from x0 to x1 as a path. shape(x) is the height at x; step is how finely it is drawn. */
function wave(x0: number, x1: number, shape: (x: number) => number, step: number): string {
  let d = "";
  for (let x = x0; x <= x1 + 1e-6; x += step) d += `${d ? "L" : "M"}${x.toFixed(1)} ${(Y - shape(x)).toFixed(1)}`;
  return d;
}

const TURN = (2 * Math.PI) / PERIOD;
const even = (x: number) => 11 * Math.sin(TURN * x);
// three waves on top of one another, drawn with straight strokes: uneven, and it still repeats every PERIOD
const choppy = (x: number) => 8 * Math.sin(TURN * x) + 7 * Math.sin(2 * TURN * x + 1.3) + 5 * Math.sin(3 * TURN * x + 0.5);

function Board({ x, colour }: { x: number; colour: string }) {
  return (
    <g stroke={colour} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round">
      <rect x={x - 14} y={Y - 21} width={28} height={42} rx={4} className="fill-card" />
      <rect x={x - 7} y={Y - 5} width={14} height={14} rx={2} />
      <path d={`M${x - 6} ${Y - 13}h12`} />
      <path d={`M${x - 9} ${Y + 21}v5M${x} ${Y + 21}v5M${x + 9} ${Y + 21}v5`} />
    </g>
  );
}

export function SignalDiagram({ state, caption, reportTs, still }: {
  state: PairState; caption: string;
  /** time of the room's latest report: the waves travel once each time it moves on */
  reportTs: number | null | undefined; still: boolean;
}) {
  const id = useId();
  const reports = useNewer(state === "calm" || state === "disturbed" ? reportTs : null);
  const moving = !still && reports > 0 && (state === "calm" || state === "disturbed");
  const colour = state === "offline" ? OFF : "hsl(var(--foreground))";
  const travel = moving ? "wave-travel" : undefined;
  return (
    <div data-pair={state} data-moving={moving || undefined}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[110px] w-full" role="img" aria-label={caption}>
        <defs>
          <clipPath id={`${id}-all`}><rect x={LEFT} y={0} width={RIGHT - LEFT} height={H} /></clipPath>
          <clipPath id={`${id}-before`}><rect x={LEFT} y={0} width={MID - 18 - LEFT} height={H} /></clipPath>
          <clipPath id={`${id}-after`}><rect x={MID + 18} y={0} width={RIGHT - MID - 18} height={H} /></clipPath>
        </defs>
        {state === "offline" && <path d={`M${LEFT} ${Y}H${RIGHT}`} stroke={OFF} strokeWidth={2} strokeDasharray="7 6" fill="none" />}
        {state === "waiting" && <path d={`M${LEFT} ${Y}H${RIGHT}`} stroke="hsl(var(--muted-foreground))" strokeWidth={1.5} fill="none" />}
        {state === "calm" && (
          <g clipPath={`url(#${id}-all)`}>
            <path key={reports} className={travel} d={wave(LEFT - PERIOD, RIGHT, even, 2)} stroke={BRAND} strokeWidth={2.5} fill="none" strokeLinecap="round" />
          </g>
        )}
        {state === "disturbed" && (
          <>
            <g clipPath={`url(#${id}-before)`}>
              <path key={reports} className={travel} d={wave(LEFT - PERIOD, MID, even, 2)} stroke={BRAND} strokeWidth={2.5} fill="none" strokeLinecap="round" />
            </g>
            <g clipPath={`url(#${id}-after)`}>
              <path key={reports} className={travel} d={wave(MID - PERIOD, RIGHT, choppy, 3.4)} stroke={BRAND} strokeWidth={2.5} fill="none" strokeLinejoin="bevel" />
            </g>
            {/* what the body throws off the straight path */}
            <g stroke={BRAND} strokeWidth={2} fill="none" strokeLinecap="round" data-scatter>
              <path d={`M${MID + 16} 24q9 -9 20 -9`} /><path d={`M${MID + 20} 12q7 -6 15 -6`} />
              <path d={`M${MID + 16} 88q9 9 20 9`} /><path d={`M${MID - 16} 22q-8 -8 -18 -8`} />
            </g>
            <g className="fill-foreground" data-person>
              <circle cx={MID} cy={26} r={7.5} />
              <path d={`M${MID - 11} 47q0 -9 11 -9q11 0 11 9v22h-4.5v24h-5v-22h-3v22h-5v-24h-4.5z`} />
            </g>
          </>
        )}
        <Board x={32} colour={colour} />
        <Board x={W - 32} colour={colour} />
      </svg>
      <div className="flex justify-between text-base font-medium" aria-hidden>
        <span className={state === "offline" ? "text-off" : undefined}>{T("sig.sender")}</span>
        <span className={state === "offline" ? "text-off" : undefined}>{T("sig.receiver")}</span>
      </div>
      <p data-pair-caption className={state === "offline" ? "mt-2 text-base font-medium text-off" : "mt-2 text-base font-medium"}>{caption}</p>
    </div>
  );
}

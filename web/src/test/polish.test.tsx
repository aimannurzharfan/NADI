// Part 28 rules (docs/design/POLISH_AUDIT.md): time ticks on whole local steps, and drawn plan text never under 14 px
// on screen however small the plan is drawn.
import { render } from "@testing-library/react";

import { ChartLegend, ClimateChart, TICK_GAP, fromFirstDay, percentTicks, tempScale, timeLabel, timeTicks } from "@/components/charts";
import { FloorPlan } from "@/components/floor-plan";
import { TooltipProvider } from "@/components/ui/tooltip";
import { hhmm } from "@/lib/format";
import { MIN_PX, atLeast } from "@/lib/svg-scale";

const MIDNIGHT = 1_794_412_800;  // Thursday 12 Nov 2026, 00:00 Malaysia time

describe("time ticks", () => {
  it("fall on whole local hours, not on the first data point", () => {
    const ticks = timeTicks(MIDNIGHT + 1800, MIDNIGHT + 6 * 3600 + 1800);  // 00:30 to 06:30
    expect(ticks.map(hhmm)).toEqual(["01:00", "02:00", "03:00", "04:00", "05:00", "06:00"]);
  });

  it("take a longer step when the span is long, and a short one when it is short", () => {
    expect(timeTicks(MIDNIGHT, MIDNIGHT + 24 * 3600).map(hhmm)).toEqual(["00:00", "06:00", "12:00", "18:00", "00:00"]);
    expect(timeTicks(MIDNIGHT + 3600, MIDNIGHT + 3600 + 50 * 60).map(hhmm)).toEqual(["01:00", "01:10", "01:20", "01:30", "01:40", "01:50"]);
  });
});

describe("chart rules (final review U10)", () => {
  it("gives the temperature axis five or six whole-degree ticks, and humidity the same number on 0 to 100%", () => {
    for (const values of [[23.9, 24.0, 24.1], [18.2, 31.7], [22, 28], [20, 26], [16.5, 33], [-3, 41], [24]]) {
      const s = tempScale(values);
      expect([5, 6]).toContain(s.ticks.length);
      expect(s.lo).toBeLessThanOrEqual(Math.min(...values));
      expect(s.hi).toBeGreaterThanOrEqual(Math.max(...values));
      expect(s.ticks.every(Number.isInteger)).toBe(true);
      const h = percentTicks(s.ticks.length);
      expect(h).toHaveLength(s.ticks.length);  // both axes sit on the same grid lines
      expect([h[0], h[h.length - 1]]).toEqual([0, 100]);
      expect(new Set(h.slice(1).map((v, i) => v - h[i])).size).toBe(1);  // even steps: 0, 25, 50, 75, 100 or 0, 20, ... 100
    }
  });

  it("keeps tick labels 8 px from the plot and names two series in a legend of swatches and normal text", () => {
    expect(TICK_GAP).toBe(8);
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    const { container } = render(<ClimateChart points={[[MIDNIGHT, 24, 60], [MIDNIGHT + 600, 24.4, 62]]} />);
    const legend = container.querySelector("[data-chart-legend]") as HTMLElement;
    expect([...legend.querySelectorAll("li")].map((li) => li.textContent)).toEqual(["Temperature", "Humidity"]);
    expect(legend.className).toContain("text-foreground");            // the words are never in the series colour
    expect(legend.querySelectorAll("li svg line")).toHaveLength(2);    // a swatch each
    vi.unstubAllGlobals();
    const one = render(<ChartLegend items={[{ label: "A", color: "#000" }]} />);
    expect(one.container.querySelector("line")).not.toHaveAttribute("stroke-dasharray");
  });

  it("labels time by the span: the time within a day, the weekday within a week, the date beyond", () => {
    expect(timeLabel(3600)(MIDNIGHT + 3600)).toBe("01:00");
    expect(timeLabel(7 * 86400)(MIDNIGHT)).toBe("Thu 12");
    expect(timeLabel(30 * 86400)(MIDNIGHT)).toBe("12 Nov");
  });

  it("drops the days before the first one with data from a day chart, and leaves the hours of today whole", () => {
    const days = { unit: "day" as const, points: [{ day: "2026-11-10", rm: null }, { day: "2026-11-11", rm: null }, { day: "2026-11-12", rm: 0 }, { day: "2026-11-13", rm: 1.2 }] };
    expect(fromFirstDay(days)).toEqual({ series: { unit: "day", points: days.points.slice(2) }, dataFrom: "2026-11-12" });
    const full = { unit: "day" as const, points: days.points.slice(2) };
    expect(fromFirstDay(full)).toEqual({ series: full, dataFrom: null });
    const hours = { unit: "hour" as const, points: [{ ts: MIDNIGHT, rm: null }, { ts: MIDNIGHT + 3600, rm: 0.1 }] };
    expect(fromFirstDay(hours)).toEqual({ series: hours, dataFrom: null });
    const none = { unit: "day" as const, points: [{ day: "2026-11-12", rm: null }] };
    expect(fromFirstDay(none).series.points).toHaveLength(1);  // nothing reported yet: the chart is left as it is
  });
});

describe("drawn plan text", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is raised so it is at least 14 px on screen when the plan is drawn small", () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    const width = vi.spyOn(SVGElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 500, height: 280 } as DOMRect);
    const { container } = render(<TooltipProvider><FloorPlan rooms={[]} now={120} onSelect={() => {}} /></TooltipProvider>);
    const scale = 500 / 1000;  // the plan is 1000 units wide
    const sizes = [...container.querySelectorAll("text")].map((t) => parseFloat((t as SVGTextElement).style.fontSize)).filter((n) => n > 0);
    expect(sizes.length).toBeGreaterThan(5);
    for (const s of sizes) expect(s * scale).toBeGreaterThanOrEqual(MIN_PX - 1e-6);
    width.mockRestore();
  });

  it("keeps its own size when the plan is drawn large enough", () => {
    expect(atLeast(15, 1.2)).toBe(15);
    expect(atLeast(13, 0.5)).toBeCloseTo(28.5);
  });
});

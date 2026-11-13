import { fireEvent, render, screen } from "@testing-library/react";

import { FloorPlan } from "@/components/floor-plan";
import { Kpi } from "@/components/kpi";
import { SimCounter } from "@/components/status";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Room } from "@/lib/types";

const rooms: Room[] = [
  { room_id: "room1", name: "Lab 2", headcount: 0, at_least: false, count_ts: 100, temp_c: 22, humidity: 60, live: true, waste: { since: 1, minutes: 12, rm: 0.4 } },
  { room_id: "room2", name: "Hall A", headcount: 3, at_least: true, count_ts: 100, temp_c: 24, humidity: 60, live: true, waste: null },
  { room_id: "room3", name: "Room 3", headcount: 1, at_least: false, count_ts: 40, temp_c: 27, humidity: 60, live: false, waste: null },
];

describe("FloorPlan", () => {
  it("labels every room for screen readers and opens one with the keyboard", () => {
    const onSelect = vi.fn();
    render(<TooltipProvider><FloorPlan rooms={rooms} now={120} onSelect={onSelect} /></TooltipProvider>);
    const hall = screen.getByRole("button", { name: /Hall A: 3\+ people, Occupied/ });
    expect(screen.getByRole("button", { name: /Lab 2: 0 people, Empty, A\/C on/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Room 3: count unknown, Offline/ })).toBeInTheDocument();
    fireEvent.keyDown(hall, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("room2");
  });

  it("says 'No sensor' for a room that never reported, and 'No report yet' only where a sensor pair is drawn", () => {
    // the plan draws a sensor pair in room1 only
    const { container } = render(<TooltipProvider><FloorPlan rooms={[]} now={120} onSelect={() => {}} /></TooltipProvider>);
    expect(screen.getByRole("button", { name: "Lab 2: no report yet" })).toHaveTextContent("No report yet");
    expect(screen.getByRole("button", { name: "Hall A: no sensor" })).toHaveTextContent("No sensor");
    expect(screen.getByRole("button", { name: "Room 3: no sensor" })).toBeInTheDocument();
    expect(container.textContent).not.toContain("No data yet");
    // grey and dashed, like an offline room: never a plain empty room
    expect([...container.querySelectorAll("rect[stroke-dasharray]")].length).toBeGreaterThanOrEqual(3);
  });

  it("uses the same words in the emergency view", () => {
    const { container } = render(<FloorPlan rooms={[]} now={120} emergency ranked={[]} />);
    expect(screen.getByRole("img", { name: "Hall A: no sensor" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Lab 2: no report yet" })).toBeInTheDocument();
    expect(container.textContent).toContain("No sensor");
  });

  it("writes the status under the count in words, so the fill is never the only cue", () => {
    const { container } = render(<TooltipProvider><FloorPlan rooms={rooms} now={120} onSelect={() => {}} /></TooltipProvider>);
    const subs = [...container.querySelectorAll("[data-room-sub]")].map((t) => t.textContent!.replace(/\s/g, " "));
    expect(subs).toEqual(["Occupied · 24.0 °C", "Empty 12 min, A/C on", "last known 1"]);  // in the plan's order: Hall A, Lab 2, Room 3
  });

  it("numbers the rooms to check in emergency mode, names their nearest exit, draws no route and is not clickable", () => {
    const { container } = render(<FloorPlan rooms={rooms} now={120} emergency ranked={[rooms[1], rooms[2]]} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    const numbers = [...container.querySelectorAll("circle + text")].map((t) => t.textContent);
    expect(numbers).toEqual(["1", "2"]);
    expect(container.querySelector("path[stroke-dasharray='2 6']")).toBeNull();  // no route line
    expect([...container.querySelectorAll("[data-room-exit]")].map((t) => t.textContent)).toEqual(["Nearest exit: Stair A", "Nearest exit: Stair A"]);  // Hall A and Room 3 both leave by Stair A
    expect(container.textContent).toContain("last known 1");
    expect(container.textContent).not.toContain("Room 31");  // an offline room shows "?", never its old count
  });
});

describe("Kpi", () => {
  it("colours a change by whether it is good news", () => {
    render(<Kpi label="Waste" value="RM 3.40" delta={0.8} deltaText="+RM 0.80" better="down" />);
    expect(screen.getByText("+RM 0.80").className).toContain("text-crit");
  });
  it("says when there is nothing to compare with", () => {
    render(<Kpi label="People" value="4" delta={null} />);
    expect(screen.getByText("No earlier data to compare")).toBeInTheDocument();
  });
});

describe("simulated counter label", () => {
  it("appears for a count from the count service, on the plan and as a tag, and never for CSI", () => {
    const counted: Room[] = [{ ...rooms[1], headcount: 120, at_least: false, counter: "count" }, { ...rooms[0], counter: "csi" }];
    render(<TooltipProvider><FloorPlan rooms={counted} now={120} onSelect={() => {}} /></TooltipProvider>);
    expect(screen.getAllByText("Simulated counter (phase 2)")).toHaveLength(1);
    render(<><SimCounter room={counted[0]} /><SimCounter room={counted[1]} /><SimCounter room={undefined} /></>);
    expect(screen.getAllByText("Simulated counter (phase 2)")).toHaveLength(2);
  });
});

import { Pencil } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { FloorPlan, PlanLegend } from "@/components/floor-plan";
import { PageHeader, Panel } from "@/components/panel";
import { ExampleNote } from "@/components/site-switcher";
import { RoomDrawer } from "@/components/room-drawer";
import { Button } from "@/components/ui/button";
import { useInfo, useMe, useRooms } from "@/lib/api";
import { T } from "@/lib/i18n";
import { usePlan, useSite } from "@/lib/site";

export function FloorPage() {
  const rooms = useRooms();
  const info = useInfo();
  const PLAN = usePlan();
  const { floor, floorId, example, site } = useSite();
  const admin = !!useMe().data?.admin;
  const [params, setParams] = useSearchParams();
  const selected = params.get("room");
  const data = rooms.data;
  const room = data?.rooms.find((r) => r.room_id === selected) ?? null;
  // a room drawn on the plan that has never reported: its panel says there is no sensor
  const noSensor = data && !room && selected && selected in PLAN.rooms
    ? { id: selected, name: info.data?.room_names[selected] ?? PLAN.rooms[selected].name ?? selected, linked: !!PLAN.rooms[selected].link } : null;
  const select = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("room", id);
    else next.delete("room");
    next.delete("section");
    setParams(next, { replace: true });
  };
  return (
    <>
      <PageHeader title={T("plan.title", { level: floor?.name ?? info.data?.level ?? "" })} description={T("floor.description")}
        actions={admin && site?.editor && !example ? (
          <Button asChild variant="outline"><Link to={`/floor/edit?floor=${encodeURIComponent(floorId)}`} data-edit-plan><Pencil aria-hidden />{T("ed.open")}</Link></Button>
        ) : undefined} />
      <ExampleNote />
      <Panel loading={rooms.isLoading} error={!data && rooms.error} bodyClassName="p-4 lg:p-6">
        {data && (
          <div className="space-y-3">
            <FloorPlan rooms={data.rooms} now={data.now} selected={selected} onSelect={(id) => select(id)} />
            <PlanLegend />
          </div>
        )}
      </Panel>
      <RoomDrawer room={room} noSensor={noSensor} now={data?.now ?? 0} onClose={() => select(null)} section={params.get("section")} />
    </>
  );
}

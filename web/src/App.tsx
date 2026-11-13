import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ViewerGate } from "@/components/admin";
import { EmergencyTakeover } from "@/components/emergency";
import { AppShell } from "@/components/shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { T } from "@/lib/i18n";
import { SiteProvider } from "@/lib/site";
import { AlertsPage } from "@/pages/alerts";
import { DesignPage } from "@/pages/design";
import { EnergyPage } from "@/pages/energy";
import { ExportPage } from "@/pages/export";
import { FloorPage } from "@/pages/floor";
import { PlanEditorPage } from "@/pages/plan-editor";
import { CalibrationPage } from "@/pages/calibration";
import { OverviewPage } from "@/pages/overview";
import { ReportPage } from "@/pages/report";
import { RoomsPage } from "@/pages/rooms";
import { SensorsPage } from "@/pages/sensors";
import { SummaryPage } from "@/pages/summary";

const shell = (page: React.ReactNode) => <AppShell>{page}</AppShell>;

export default function App() {
  document.title = T("ui.page_title");
  return (
    <TooltipProvider delayDuration={200}>
      <ViewerGate>
      <SiteProvider>
      <Routes>
        <Route path="/" element={<AppShell fill><OverviewPage /></AppShell>} />
        <Route path="/summary" element={shell(<SummaryPage />)} />
        <Route path="/floor" element={shell(<FloorPage />)} />
        <Route path="/floor/edit" element={shell(<PlanEditorPage />)} />
        <Route path="/rooms" element={shell(<RoomsPage />)} />
        <Route path="/sensors" element={shell(<SensorsPage />)} />
        <Route path="/energy" element={shell(<EnergyPage />)} />
        <Route path="/alerts" element={shell(<AlertsPage />)} />
        <Route path="/design" element={shell(<DesignPage />)} />
        <Route path="/calibration" element={shell(<CalibrationPage />)} />
        <Route path="/label" element={<Navigate to={`/calibration${location.search}`} replace />} />
        <Route path="/export" element={<ExportPage />} />
        <Route path="/report/:id" element={<ReportPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <EmergencyTakeoverOutsidePrint />
      </SiteProvider>
      </ViewerGate>
    </TooltipProvider>
  );
}

/** The takeover shows on every screen of the console; the printable pages (export, report) stay as they are. */
function EmergencyTakeoverOutsidePrint() {
  const { pathname } = useLocation();
  if (pathname.startsWith("/export") || pathname.startsWith("/report")) return null;
  return <EmergencyTakeover />;
}

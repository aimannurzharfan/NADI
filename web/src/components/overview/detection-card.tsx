// Detection: what is counting people right now, and the true state of the trained model. The live detector is named
// for what the server says is counting ("rule" or "model"); MindSpore is named as the detector only while a trained
// model is active.
import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";

import { modelStatus } from "@/components/calibration-charts";
import { Section } from "@/components/overview/section";
import { Skeleton } from "@/components/ui/skeleton";
import { T } from "@/lib/i18n";
import type { Info } from "@/lib/types";

export function DetectionCard({ detector, loading, className }: { detector: Info["detector"] | undefined; loading?: boolean; className?: string }) {
  const m = detector?.model ?? null;
  return (
    <Section title={T("det.title")} className={className} bodyClassName="overflow-y-auto px-4 py-2.5 text-base"
      action={(
        <Link to="/calibration" data-open-calibration className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-2 hover:text-heading">
          {T("det.open")}<ArrowUpRight className="size-[1.1em]" aria-hidden />
        </Link>
      )}>
      {!detector ? (loading ? <div className="space-y-2" aria-busy="true"><Skeleton className="h-5 w-48 animate-none" /><Skeleton className="h-5 w-56 animate-none" /></div>
        : <p className="text-muted-foreground">{T("det.unknown")}</p>) : (
        <dl className="space-y-2.5" data-detection={detector.mode}>
          <div>
            <dt className="text-muted-foreground">{T("det.live")}</dt>
            <dd className="font-semibold" data-live-detector>
              {detector.mode === "model" ? T("det.model") : detector.threshold != null ? T("det.rule", { x: detector.threshold.toFixed(2) }) : T("det.rule_plain")}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{T("det.training")}</dt>
            <dd>
              <span className="block font-semibold">{T("det.framework")}</span>
              <span data-model-status className="block text-muted-foreground" title={modelStatus(m)}>{modelStatus(m)}</span>
            </dd>
          </div>
        </dl>
      )}
    </Section>
  );
}

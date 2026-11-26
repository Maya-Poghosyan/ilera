import { ArrowUpRight, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { APP_STATUS_LABELS, STAGE_LABELS, type ApplicationEntry } from "@/features/applications/types";
import { PROGRAM_BENEFITS } from "@/features/cases/program-benefits";
import type { EligibilityStatus } from "@/features/cases/types";

const MATCH_LABELS: Record<EligibilityStatus, string> = {
  likely: "Likely",
  possible: "Moderate",
  unlikely: "Unlikely",
  needs_info: "Information Needed",
};

export const APPLICATION_GROUPS = {
  likely: "Likely matches",
  unlikely: "Unlikely matches",
  archived: "Archived",
};
export type ApplicationGroup = keyof typeof APPLICATION_GROUPS;

export function applicationGroup(app: ApplicationEntry): ApplicationGroup {
  if (app.status === "archived") return "archived";
  return app.eligibility_status === "unlikely" ? "unlikely" : "likely";
}

export function ApplicationList({ apps, onStart }: {
  apps: ApplicationEntry[];
  onStart: (program: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {apps.map((app) => {
        const match = app.eligibility_status ?? "needs_info";
        return (
          <Card key={app.program}>
            <CardHeader>
              <CardTitle className="text-2xl">{app.program}</CardTitle>
              <CardAction>
                <Button variant="outline" size="sm" aria-label={`Open ${app.program} application`} onClick={() => onStart(app.program)}>
                  Open <ArrowUpRight aria-hidden="true" />
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-4 text-base">
              <ul className="list-disc space-y-2 pl-5">
                {PROGRAM_BENEFITS[app.program] && <li><strong>Program Overview</strong><p>{PROGRAM_BENEFITS[app.program]}</p></li>}
                <li>
                  <strong>Program Match Level</strong>
                  <span className="ml-2 inline-flex items-center gap-1.5">
                    {match === "needs_info" && <TriangleAlert aria-hidden="true" className="size-4 text-amber-600" />}
                    {MATCH_LABELS[match]}
                  </span>
                </li>
                <li><strong>Stage</strong> <span className="ml-2">{["completed", "pending_determination", "accepted", "archived"].includes(app.status) ? APP_STATUS_LABELS[app.status] : STAGE_LABELS[app.stage]}</span></li>
              </ul>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

import { ArrowUpRight, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { APP_STATUS_LABELS, STAGE_LABELS, type ApplicationEntry } from "@/features/applications/types";
import { PROGRAM_BENEFITS, PROGRAM_WEBSITES } from "@/features/cases/program-benefits";
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

export const EMPTY_GROUP_MESSAGES: Record<ApplicationGroup, string> = {
  likely: "No likely matches.",
  unlikely: "No unlikely matches.",
  archived: "No archived applications.",
};

export function applicationGroup(app: ApplicationEntry): ApplicationGroup {
  if (app.determination || ["archived", "accepted", "denied"].includes(app.status)) return "archived";
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
        const decision = app.determination ?? (app.status === "accepted" ? "approved" : app.status === "denied" ? "denied" : null);
        return (
          <Card key={app.program} className="gap-3">
            <CardHeader>
              <CardTitle className="text-2xl text-primary">
                {app.program}{decision && ` (${decision})`}
                {PROGRAM_WEBSITES[app.program] && (
                  <a href={PROGRAM_WEBSITES[app.program]} target="_blank" rel="noopener noreferrer"
                    className="ml-3 whitespace-nowrap font-sans text-sm font-normal text-muted-foreground underline underline-offset-2 hover:text-primary">
                    Official website<span className="sr-only"> for {app.program} (opens in a new tab)</span>
                  </a>
                )}
              </CardTitle>
              <CardAction>
                <Button variant="outline" size="sm" aria-label={`Open ${app.program} application`} onClick={() => onStart(app.program)}>
                  Open <ArrowUpRight aria-hidden="true" />
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="text-base">
              <ul className="space-y-3 [&_strong]:text-primary">
                {PROGRAM_BENEFITS[app.program] && <li><strong>Program Overview</strong> <span className="ml-2">{PROGRAM_BENEFITS[app.program]}</span></li>}
                <li>
                  <strong>Program Match Level</strong>
                  <span className="ml-2 inline-flex items-center gap-1.5">
                    {match === "needs_info" && <TriangleAlert aria-hidden="true" className="size-4 text-amber-600" />}
                    {MATCH_LABELS[match]}
                  </span>
                </li>
                <li><strong>Stage</strong> <span className="ml-2">{["completed", "pending_determination", "accepted", "denied", "archived"].includes(app.status) ? APP_STATUS_LABELS[app.status] : STAGE_LABELS[app.stage]}</span></li>
              </ul>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

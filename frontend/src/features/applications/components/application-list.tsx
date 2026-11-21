import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AppStatus, ApplicationEntry } from "@/features/applications/types";
import type { EligibilityStatus } from "@/features/cases/types";

const ELIGIBILITY_COLOR: Record<EligibilityStatus, string> = {
  likely: "border-transparent bg-emerald-500 text-white",
  possible: "border-transparent bg-amber-500 text-white",
  unlikely: "border-transparent bg-rose-500 text-white",
  needs_info: "border-transparent bg-sky-600 text-white",
};

const APP_STATUS_LABELS: Record<AppStatus, string> = {
  open: "Open", in_progress: "In progress", needs_info: "Needs info", completed: "Completed",
};

function Detail({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="font-medium">{label}</p>
      <ul className="list-disc pl-5 text-muted-foreground">
        {items.map((i) => <li key={i}>{i}</li>)}
      </ul>
    </div>
  );
}

export function ApplicationList({ apps, onStatus, onStart }: {
  apps: ApplicationEntry[];
  onStatus: (program: string, status: AppStatus) => void;
  onStart: (program: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {apps.map((app) => (
        <Card key={app.program} className="gap-3">
          <CardHeader className="gap-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-base">{app.program}</CardTitle>
              {app.eligibility_status && (
                <Badge className={ELIGIBILITY_COLOR[app.eligibility_status]}>{app.eligibility_status.replace("_", " ")}</Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{app.rationale}</p>
          </CardHeader>

          <CardContent className="space-y-2.5 text-xs">
            {app.roadblocks.length > 0 && <Detail label="Roadblocks" items={app.roadblocks} />}
            {app.required_documents.length > 0 && <Detail label="Required documents" items={app.required_documents} />}
            {app.next_steps.length > 0 && <Detail label="Next steps" items={app.next_steps} />}
            {app.sources.length > 0 && <p className="text-[11px] text-muted-foreground">Sources: {app.sources.join(", ")}</p>}

            <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
              <div className="flex items-center gap-2">
                <select
                  className="h-7 rounded-md border bg-transparent px-2 text-xs"
                  value={app.status}
                  onChange={(e) => onStatus(app.program, e.target.value as AppStatus)}
                >
                  {Object.entries(APP_STATUS_LABELS).map(([val, label]) => <option key={val} value={val}>{label}</option>)}
                </select>
                {app.has_forms && (
                  <span className="text-[11px] text-muted-foreground">
                    {app.form_ids.length} form{app.form_ids.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
              {app.has_forms ? (
                <Button size="sm" onClick={() => onStart(app.program)}>
                  {app.status === "completed" ? "Re-fill" : app.status === "in_progress" ? "Continue" : "Fill forms"}
                </Button>
              ) : (
                <span className="text-[11px] text-muted-foreground italic">No forms mapped yet</span>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

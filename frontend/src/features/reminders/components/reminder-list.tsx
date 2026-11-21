import { CalendarDays } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FREQ_LABELS, KIND_LABELS, WEEKDAY_LABELS } from "@/features/reminders/labels";
import type { Reminder } from "@/features/reminders/types";

function formatRun(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function ReminderList({ reminders, onEdit, onToggle, onDelete }: {
  reminders: Reminder[];
  onEdit: (r: Reminder) => void;
  onToggle: (r: Reminder) => void;
  onDelete: (id: string) => void;
}) {
  if (reminders.length === 0) return null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-primary">
        <CalendarDays className="size-4" />
        <h3 className="text-sm">Saved Reminders</h3>
      </div>
      <p className="text-xs text-muted-foreground">Reminders are saved only. Automatic delivery is unavailable.</p>
      {reminders.map((r) => (
        <Card key={r.id}>
          <CardHeader className="flex flex-row items-center justify-between py-4">
            <div className="flex items-center gap-2">
              <CardTitle className="text-base">{KIND_LABELS[r.kind]}</CardTitle>
              <Badge variant={r.active ? "default" : "secondary"}>{r.active ? "Active" : "Paused"}</Badge>
              <Badge variant="outline">
                {FREQ_LABELS[r.schedule.freq]}
                {r.schedule.freq === "weekly" && r.schedule.weekday != null ? ` (${WEEKDAY_LABELS[r.schedule.weekday]})` : ""}
                {" at "}
                {r.schedule.time}
              </Badge>
            </div>
            <div className="flex gap-1">
              <Button variant="outline" size="sm" onClick={() => onEdit(r)}>Edit</Button>
              <Button variant="outline" size="sm" onClick={() => onToggle(r)}>{r.active ? "Pause" : "Resume"}</Button>
              <Button variant="destructive" size="sm" onClick={() => onDelete(r.id)}>Delete</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-1 py-0 pb-4">
            <p className="text-sm">
              {r.kind === "daily_care_log" && !r.message
                ? "Built-in care-log prompt (hours, meals, meds, mood)"
                : r.message || "No message"}
            </p>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>Next: {formatRun(r.next_run)}</span>
              {r.last_sent_at && <span>Last sent: {formatRun(r.last_sent_at)}</span>}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

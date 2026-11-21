import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FREQ_LABELS, KIND_LABELS, WEEKDAY_LABELS } from "@/features/reminders/labels";
import type { ReminderKind, ScheduleFreq } from "@/features/reminders/types";
import type { ReminderDraft } from "@/features/reminders/use-reminders";

export function ReminderForm({ draft, onChange, onSave, onCancel }: {
  draft: ReminderDraft;
  onChange: (patch: Partial<ReminderDraft>) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{draft.id ? "Edit Reminder" : "New Reminder"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label>Type</Label>
          <div className="flex gap-2">
            {(Object.keys(KIND_LABELS) as ReminderKind[]).map((k) => (
              <Button key={k} variant={draft.kind === k ? "default" : "outline"} size="sm" onClick={() => onChange({ kind: k })}>
                {KIND_LABELS[k]}
              </Button>
            ))}
          </div>
        </div>

        {draft.kind === "daily_care_log" ? (
          <p className="text-sm text-muted-foreground">
            A saved reminder to record daily care. Automatic text check-ins are unavailable.
          </p>
        ) : (
          <div className="space-y-1">
            <Label htmlFor="msg">Message</Label>
            <Input id="msg" value={draft.message} onChange={(e) => onChange({ message: e.target.value })} placeholder="Reminder details" />
          </div>
        )}

        <div className="flex flex-wrap gap-4">
          <div className="space-y-1">
            <Label>Frequency</Label>
            <div className="flex gap-2">
              {(["daily", "weekly", "once"] as ScheduleFreq[]).map((f) => (
                <Button key={f} variant={draft.freq === f ? "default" : "outline"} size="sm" onClick={() => onChange({ freq: f })}>
                  {FREQ_LABELS[f]}
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="time">Time (your local time)</Label>
            <Input id="time" type="time" value={draft.time} onChange={(e) => onChange({ time: e.target.value })} className="w-32" />
          </div>

          {draft.freq === "weekly" && (
            <div className="space-y-1">
              <Label>Day</Label>
              <div className="flex gap-1">
                {WEEKDAY_LABELS.map((d, i) => (
                  <Button key={d} variant={draft.weekday === i ? "default" : "outline"} size="sm" onClick={() => onChange({ weekday: i })}>
                    {d}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {draft.freq === "once" && (
            <div className="space-y-1">
              <Label htmlFor="date">Date</Label>
              <Input id="date" type="date" value={draft.date} onChange={(e) => onChange({ date: e.target.value })} className="w-40" />
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <Button onClick={onSave}>{draft.id ? "Update" : "Create"}</Button>
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
        </div>
      </CardContent>
    </Card>
  );
}

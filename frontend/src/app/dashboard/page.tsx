import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const events = [
  { title: "Dr. Patel — cardiology follow-up", date: "Mon, Jun 23 · 10:00 AM", kind: "Appointment" },
  { title: "County social worker visit", date: "Wed, Jun 25 · 2:00 PM", kind: "Visit" },
  { title: "IHSS timesheet due", date: "Fri, Jun 27", kind: "Deadline" },
];

export default function CalendarPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Care Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Agents can scan email (via Poke) to auto-create events and text reminders.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">+ Appointment</Button>
          <Button variant="outline" size="sm">+ Visit</Button>
          <Button variant="outline" size="sm">+ Deadline</Button>
        </div>
      </div>

      <div className="space-y-3">
        {events.map((e) => (
          <Card key={e.title}>
            <CardHeader className="flex flex-row items-center justify-between py-4">
              <CardTitle className="text-base">{e.title}</CardTitle>
              <span className="text-xs text-muted-foreground">{e.kind}</span>
            </CardHeader>
            <CardContent className="py-0 pb-4 text-sm text-muted-foreground">{e.date}</CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const timekeeping = [
  { date: "Jun 20", hours: "6.0 hrs", note: "Bathing, meals, medication, mobility" },
  { date: "Jun 19", hours: "5.5 hrs", note: "Meals, medication, doctor transport" },
];

const journal = [
  { date: "Jun 20", text: "Mom had a small fall in the bathroom this morning. No injury but shaken." },
  { date: "Jun 18", text: "Good day. Ate well and went for a short walk." },
];

export default function RecordsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Records &amp; Renewal</h1>
        <span className="text-sm font-medium text-muted-foreground">Renewal due: Sep 1, 2026</span>
      </div>

      <Card className="border-amber-300 bg-amber-50">
        <CardContent className="flex items-start gap-3 py-4 text-sm">
          <span aria-hidden>🚩</span>
          <p>
            You logged <strong>a fall</strong> on <strong>Jun 20</strong>. Create a state incident
            report?{" "}
            <a className="font-medium underline" href="/dashboard/documents">
              Go to Documents
            </a>
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Timekeeping</h2>
            <Button size="sm" variant="outline">+ Entry</Button>
          </div>
          {timekeeping.map((t) => (
            <Card key={t.date}>
              <CardHeader className="flex flex-row items-center justify-between py-3">
                <CardTitle className="text-sm">{t.date}</CardTitle>
                <span className="text-xs text-muted-foreground">{t.hours}</span>
              </CardHeader>
              <CardContent className="py-0 pb-3 text-sm text-muted-foreground">{t.note}</CardContent>
            </Card>
          ))}
          <Button size="sm">Submit timesheet to IHSS portal</Button>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Care journal</h2>
            <Button size="sm" variant="outline">+ Entry</Button>
          </div>
          {journal.map((j) => (
            <Card key={j.date}>
              <CardHeader className="py-3">
                <CardTitle className="text-sm">{j.date}</CardTitle>
              </CardHeader>
              <CardContent className="py-0 pb-3 text-sm text-muted-foreground">{j.text}</CardContent>
            </Card>
          ))}
        </section>
      </div>
    </div>
  );
}

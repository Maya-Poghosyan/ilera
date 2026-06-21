import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const features = [
  {
    title: "Eligibility Navigation",
    body: "A short, progressive intake builds a shared CaseProfile and routes your case to the right specialist agents.",
  },
  {
    title: "Determination & Optimization",
    body: "Specialist agents (IHSS, Medi-Cal, PFL, VA…) coordinate over official docs to rank programs and your best strategy.",
  },
  {
    title: "Application Completion",
    body: "Agents autofill government PDFs from your profile, ask only what's missing, and stitch everything to download.",
  },
  {
    title: "Caregiver Support",
    body: "A care calendar, timekeeping & journal, and a document store — with agentic SMS reminders and portal automation.",
  },
];

export default function Home() {
  return (
    <main className="flex flex-1 flex-col">
      <section className="mx-auto flex max-w-3xl flex-1 flex-col items-center justify-center gap-6 px-6 py-20 text-center">
        <span className="rounded-full border px-3 py-1 text-xs text-muted-foreground">
          Agentic assistance for caregivers
        </span>
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Ilera</h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Unpaid caregivers spend hours navigating fragmented benefits programs. Ilera finds
          what you qualify for, optimizes your strategy, and completes the applications for you.
        </p>
        <div className="flex gap-3">
          <Button size="lg" render={<Link href="/intake" />}>
            Start intake
          </Button>
          <Button size="lg" variant="outline" render={<Link href="/dashboard" />}>
            View dashboard
          </Button>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-4 px-6 pb-20 sm:grid-cols-2">
        {features.map((f) => (
          <Card key={f.title}>
            <CardHeader>
              <CardTitle className="text-lg">{f.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{f.body}</CardContent>
          </Card>
        ))}
      </section>
    </main>
  );
}

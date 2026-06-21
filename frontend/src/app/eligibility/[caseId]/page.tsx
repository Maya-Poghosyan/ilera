"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Logo } from "@/components/logo";
import { determineEligibility } from "@/lib/api";
import type { EligibilityResponse, EligibilityStatus } from "@/lib/types";

const statusColor: Record<EligibilityStatus, string> = {
  likely: "border-transparent bg-primary text-primary-foreground",
  possible: "border-transparent bg-amber-500 text-white",
  unlikely: "border-transparent bg-rose-500 text-white",
  needs_info: "border-transparent bg-sky-600 text-white",
};

export default function EligibilityPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [data, setData] = useState<EligibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    determineEligibility(caseId).then(setData).catch(() => setError("Could not reach the API."));
  }, [caseId]);

  if (error) {
    return (
      <main className="mx-auto max-w-xl px-6 py-20 text-center">
        <p className="text-muted-foreground">{error} Is the backend running on :8000?</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
        <h1 className="text-xl font-semibold">Determining eligibility…</h1>
        <p className="text-sm text-muted-foreground">
          The routing agent is activating specialist agents and grounding their answers in
          official program documentation.
        </p>
      </main>
    );
  }

  return (
    <>
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Logo />
          <Button variant="outline" size="sm" render={<Link href="/intake" />}>
            Edit intake
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 space-y-6 px-6 py-12">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Your benefits strategy</h1>
        <p className="text-sm text-muted-foreground">Ranked by eligibility confidence.</p>
      </div>

      {data.strategy_notes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Strategy notes</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {data.strategy_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {data.results.map((r) => {
          const pct = Math.round(r.confidence * 100);
          return (
            <Card key={r.program} size="sm" className="gap-3">
              <CardHeader className="gap-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">{r.program}</CardTitle>
                  <Badge className={statusColor[r.status]}>
                    {r.status.replace("_", " ")}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold tabular-nums text-muted-foreground">
                    {pct}%
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-2.5 text-xs">
                <p className="text-muted-foreground">{r.rationale}</p>
                {r.roadblocks.length > 0 && (
                  <Detail label="Roadblocks" items={r.roadblocks} />
                )}
                <Detail label="Required documents" items={r.required_documents} />
                {r.next_steps.length > 0 && (
                  <Detail label="Next steps" items={r.next_steps} />
                )}
                {r.sources.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Sources: {r.sources.join(", ")}
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Button render={<Link href="/dashboard/applications" />}>
        Continue to applications
        <ArrowRight />
      </Button>
      </main>
    </>
  );
}

function Detail({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="font-medium">{label}</p>
      <ul className="list-disc pl-5 text-muted-foreground">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}

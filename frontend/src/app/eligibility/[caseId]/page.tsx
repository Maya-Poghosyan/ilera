"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { determineEligibility } from "@/lib/api";
import type { EligibilityResponse, EligibilityStatus } from "@/lib/types";

const statusColor: Record<EligibilityStatus, string> = {
  likely: "bg-green-100 text-green-800",
  possible: "bg-yellow-100 text-yellow-800",
  unlikely: "bg-red-100 text-red-700",
  needs_info: "bg-blue-100 text-blue-800",
};

const LOADING_MESSAGES = [
  "Activating specialist agents…",
  "Grounding answers in official program documentation…",
  "Matching you to Medicaid, IHSS, Paid Family Leave, and VA programs…",
  "Ranking programs by eligibility confidence…",
];

export default function EligibilityPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [data, setData] = useState<EligibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    determineEligibility(caseId).then(setData).catch(() => setError("Could not reach the API."));
  }, [caseId]);

  useEffect(() => {
    if (data || error) return;
    const id = setInterval(() => {
      setMessageIndex((i) => (i + 1) % LOADING_MESSAGES.length);
    }, 2200);
    return () => clearInterval(id);
  }, [data, error]);

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
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-foreground" />
        <h1 className="text-xl font-semibold">Determining eligibility…</h1>
        <p
          key={messageIndex}
          className="min-h-10 max-w-sm text-sm text-muted-foreground animate-in fade-in duration-700"
        >
          {LOADING_MESSAGES[messageIndex]}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 space-y-6 px-6 py-12">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold">Your benefits strategy</h1>
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

      <div className="space-y-4">
        {data.results.map((r) => (
          <Card key={r.program}>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">{r.program}</CardTitle>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {Math.round(r.confidence * 100)}%
                </span>
                <Badge className={statusColor[r.status]}>{r.status.replace("_", " ")}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p className="text-muted-foreground">{r.rationale}</p>
              {r.roadblocks.length > 0 && (
                <Detail label="Roadblocks" items={r.roadblocks} />
              )}
              <Detail label="Required documents" items={r.required_documents} />
              {r.next_steps.length > 0 && <Detail label="Next steps" items={r.next_steps} />}
              {r.sources.length > 0 && (
                <p className="text-xs text-muted-foreground">Sources: {r.sources.join(", ")}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {data.followups.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">A few follow-up questions</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {data.followups.map((q) => (
                <li key={q.id}>
                  <span className="font-medium">{q.prompt}</span>
                  {q.why && <span className="block text-xs text-muted-foreground">{q.why}</span>}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Button render={<Link href="/dashboard" />}>Continue to dashboard</Button>
    </main>
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

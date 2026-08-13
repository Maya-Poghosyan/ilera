"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadFailure } from "@/components/load-failure";
import { Logo } from "@/components/logo";
import { determineEligibility, getEligibility } from "@/lib/api";
import type { EligibilityResponse, MatchLevel } from "@/lib/types";

const matchColor: Record<MatchLevel, string> = {
  very_likely: "border-transparent bg-primary text-primary-foreground",
  likely: "border-transparent bg-emerald-600 text-white",
  medium: "border-transparent bg-amber-500 text-white",
  low: "border-transparent bg-orange-500 text-white",
  none: "border-transparent bg-muted text-muted-foreground",
};

const matchLabel: Record<MatchLevel, string> = {
  very_likely: "very likely",
  likely: "likely",
  medium: "medium",
  low: "low",
  none: "no match",
};

const LOADING_MESSAGES = [
  "Spinning up the specialist agents in your case room…",
  "Each specialist is grounding its answer in official program documentation…",
  "Specialists are checking your state and county rules…",
  "Coordinating cross-program eligibility between specialists…",
  "The routing agent is synthesizing your application strategy…",
];

const POLL_MS = 3000;
// A Band run takes a while, so a poll that fails mid-run shouldn't discard it — the analysis
// keeps going server-side. Give up only once the API has been unreachable for this many polls.
const MAX_POLL_FAILURES = 5;

export default function EligibilityPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [data, setData] = useState<EligibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messageIndex, setMessageIndex] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let active = true;
    let failures = 0;

    const poll = () => {
      getEligibility(caseId)
        .then((res) => {
          if (!active) return;
          failures = 0;
          setData(res);
          if (res.status === "idle" || res.status === "processing") {
            timer.current = setTimeout(poll, POLL_MS);
          }
        })
        .catch(() => {
          if (!active) return;
          failures++;
          if (failures >= MAX_POLL_FAILURES) {
            setError("We lost contact while reviewing your programs.");
          } else {
            timer.current = setTimeout(poll, POLL_MS);
          }
        });
    };

    // Kick off the Band eligibility run (idempotent), then poll for results.
    determineEligibility(caseId)
      .then((res) => {
        if (!active) return;
        setError(null);
        setData(res);
        if (res.status === "idle" || res.status === "processing") {
          timer.current = setTimeout(poll, POLL_MS);
        }
      })
      .catch(() => {
        if (active) setError("We couldn't start reviewing your programs just now.");
      });

    return () => {
      active = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [caseId, attempt]);

  const processing = !data || data.status === "idle" || data.status === "processing";

  useEffect(() => {
    if (error || !processing) return;
    const id = setInterval(() => {
      setMessageIndex((i) => (i + 1) % LOADING_MESSAGES.length);
    }, 2600);
    return () => clearInterval(id);
  }, [error, processing]);

  if (error) {
    return (
      <LoadFailure message={error} onRetry={() => setAttempt((n) => n + 1)} />
    );
  }

  if (data && data.status === "error") {
    return (
      <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <h1 className="text-xl font-semibold text-rose-600">Eligibility could not be completed</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          {data.error || "The specialist agents did not return a result. Please try again."}
        </p>
        <Button variant="outline" render={<Link href="/intake" />}>
          Back to intake
        </Button>
      </main>
    );
  }

  if (processing) {
    const done = data?.completed.length ?? 0;
    const total = data?.expected.length ?? 0;
    return (
      <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
        <h1 className="text-xl font-semibold text-primary">Determining eligibility…</h1>
        <p
          key={messageIndex}
          className="min-h-10 max-w-sm text-sm text-foreground animate-in fade-in duration-700"
        >
          {LOADING_MESSAGES[messageIndex]}
        </p>
        {total > 0 && (
          <p className="text-xs text-muted-foreground">
            {done} of {total} specialists have responded
          </p>
        )}
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
          <h1 className="text-2xl font-bold tracking-tight">Your eligibility results</h1>
          <p className="text-sm text-muted-foreground">
            Match levels determined by each program specialist.
          </p>
        </div>

        {data.strategy && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Application strategy</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">{data.strategy}</p>
            </CardContent>
          </Card>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {data.results.map((r) => (
            <Card key={r.program} size="sm" className="gap-3">
              <CardHeader className="gap-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">{r.program}</CardTitle>
                  <Badge className={matchColor[r.match_level]}>{matchLabel[r.match_level]}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-2.5 text-xs">
                <p className="text-muted-foreground">{r.rationale}</p>
                {r.sources.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Sources: {r.sources.join(", ")}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        <Button render={<Link href="/dashboard/applications" />}>
          Continue to applications
          <ArrowRight />
        </Button>
      </main>
    </>
  );
}

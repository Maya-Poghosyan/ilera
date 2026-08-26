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
import { useAuth } from "@/lib/auth-context";
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
  "Reading your answers…",
  "Checking the rules in your county…",
  "Consulting official program documents…",
  "Comparing programs you may qualify for…",
  "Putting your plan together…",
];

/** The strategy is stored as one bullet per line; older cases hold a paragraph or two. */
function strategyBullets(strategy: string): string[] {
  return strategy
    .split("\n")
    .map((line) => line.replace(/^\s*(?:[-*•–—]|\(?\d+[.)])\s+/, "").trim())
    .filter(Boolean);
}

const POLL_MS = 3000;

export default function EligibilityPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<EligibilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messageIndex, setMessageIndex] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let active = true;

    const poll = () => {
      getEligibility(caseId)
        .then((res) => {
          if (!active) return;
          setData(res);
          if (res.status === "idle" || res.status === "processing") {
            timer.current = setTimeout(poll, POLL_MS);
          }
        })
        .catch(() => {
          if (active) setError("We lost contact while reviewing your programs.");
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
          {data.error || "We couldn't finish reviewing your programs. Please try again."}
        </p>
        <Button variant="outline" render={<Link href="/intake" />}>
          Back to intake
        </Button>
      </main>
    );
  }

  if (processing) {
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
            How well each program matches your situation.
          </p>
        </div>

        {data.strategy && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Your plan</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {strategyBullets(data.strategy).map((bullet) => (
                  <li key={bullet} className="flex gap-2.5 text-sm">
                    <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
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

        {authLoading ? null : user ? (
          <Button render={<Link href="/dashboard/applications" />}>
            Continue to applications
            <ArrowRight />
          </Button>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Keep this plan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Create an account with your email and phone number to save these results, start
                your applications, and get reminders. Your answers are already saved here.
              </p>
              <Button render={<Link href="/signup" />}>
                Create an account
                <ArrowRight />
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadFailure } from "@/components/load-failure";
import { SiteHeader } from "@/components/site-header";
import { useAuth } from "@/features/accounts/auth-context";
import { determineEligibility, getEligibility } from "@/features/cases/api";
import type { EligibilityResponse } from "@/features/cases/types";

const PROGRAM_BENEFITS: Record<string, string> = {
  "IHSS": "Pays for eligible in-home help with daily care.",
  "Medi-Cal": "Health coverage that can include long-term services and supports.",
  "Medicare": "Health coverage that can help pay for hospital care, medical visits, and prescriptions.",
  "Paid Family Leave": "Replaces part of your wages while you take time away from work to care for a family member.",
  "VA Caregiver Support": "Offers caregiver education and support, and a stipend for some eligible caregivers.",
  "Caregiver Tax Relief": "Tax credits and other tax savings for eligible caregiving expenses.",
};

const LOADING_MESSAGES = [
  "Reading your answers…",
  "Checking the rules in your county…",
  "Consulting program documents…",
  "Comparing programs you may qualify for…",
];

function resultsReady(data: EligibilityResponse) {
  return data.status === "complete" || (data.status === "processing" && data.results.length > 0);
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

    const shouldKeepPolling = (res: EligibilityResponse) =>
      res.status !== "error" && !resultsReady(res);

    const poll = () => {
      getEligibility(caseId)
        .then((res) => {
          if (!active) return;
          setData(res);
          if (shouldKeepPolling(res)) {
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
        if (shouldKeepPolling(res)) {
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

  const processing = !data || (data.status !== "error" && !resultsReady(data));

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
        <h1 className="page-title text-rose-600">Eligibility could not be completed</h1>
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
        <h1 className="page-title">Determining eligibility…</h1>
        <p
          key={messageIndex}
          className="min-h-10 max-w-sm text-sm text-foreground animate-in fade-in duration-700"
        >
          {messageIndex === 1 && data?.county ? `Checking county rules for ${data.county}…` : LOADING_MESSAGES[messageIndex]}
        </p>
      </main>
    );
  }

  return (
    <>
      <SiteHeader
        actions={<Button variant="outline" size="sm" render={<Link href="/intake" />}> Edit intake </Button>}
      />
      <main className="mx-auto w-full max-w-5xl flex-1 space-y-6 px-6 py-12">
        <h1 className="page-title">Your eligibility results</h1>
        {[
          { title: "Likely", open: true, programs: data.results.filter(({ status }) => status === "likely" || status === "possible") },
          { title: "Unlikely or needs more information", open: false, programs: data.results.filter(({ status }) => status === "unlikely" || status === "needs_info") },
        ].filter(({ programs }) => programs.length > 0).map(({ title, open, programs }) => (
          <details key={title} open={open} className="rounded-xl border bg-card px-5">
            <summary className="cursor-pointer py-4 text-xl">{title}</summary>
            <ul className="divide-y">
              {programs.map(({ program, status }) => (
                <li key={program} className="space-y-1 py-4">
                  <h2 className="text-xl">{program}{status === "possible" && <span className="ml-2 font-sans text-xs text-muted-foreground">Possible</span>}{status === "needs_info" && <span className="ml-2 font-sans text-xs text-muted-foreground">Needs more information</span>}</h2>
                  {PROGRAM_BENEFITS[program] && <p className="text-sm text-muted-foreground">{PROGRAM_BENEFITS[program]}</p>}
                </li>
              ))}
            </ul>
          </details>
        ))}

        {authLoading ? null : user ? (
          <Button render={<Link href="/dashboard/applications" />}>
            Continue to applications
            <ArrowRight />
          </Button>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Save your results</CardTitle>
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

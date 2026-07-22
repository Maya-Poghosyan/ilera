"use client";

import Link from "next/link";
import {
  ArrowRight,
  ClipboardCheck,
  Compass,
  HeartHandshake,
  Scale,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth-context";

const features = [
  {
    icon: Compass,
    title: "Eligibility Navigation",
    body: "A short, progressive intake builds a shared CaseProfile and routes your case to the right specialist agents.",
  },
  {
    icon: Scale,
    title: "Determination & Optimization",
    body: "Specialist agents (IHSS, Medi-Cal, PFL, VA…) coordinate over official docs to rank programs and your best strategy.",
  },
  {
    icon: ClipboardCheck,
    title: "Application Completion",
    body: "Agents autofill government PDFs from your profile, ask only what's missing, and stitch everything to download.",
  },
  {
    icon: HeartHandshake,
    title: "Caregiver Support",
    body: "A care calendar, timekeeping & journal, and a document store — with agentic SMS reminders and portal automation.",
  },
];

export default function Home() {
  const { user, loading } = useAuth();

  return (
    <main className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Logo />
          <div className="flex items-center gap-2">
            {!loading && user ? (
              <Button render={<Link href="/dashboard" />}>Dashboard</Button>
            ) : (
              <>
                <Button variant="outline" render={<Link href="/login" />}>
                  Sign in
                </Button>
                <Button render={<Link href="/signup" />}>Get started</Button>
              </>
            )}
          </div>
        </div>
      </header>

      <section className="mx-auto flex max-w-3xl flex-1 flex-col items-center justify-center gap-6 px-6 py-24 text-center">
        <h1 className="text-balance text-4xl font-bold tracking-tight text-primary sm:text-5xl">
          Benefits navigation that works for caregivers
        </h1>
        <p className="max-w-xl text-pretty text-lg text-muted-foreground">
          Unpaid caregivers spend hours navigating fragmented benefits programs. Ilera finds
          what you qualify for, optimizes your strategy, and completes the applications for you.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          {!loading && user ? (
            <Button size="lg" render={<Link href="/dashboard" />}>
              Go to dashboard
              <ArrowRight />
            </Button>
          ) : (
            <>
              <Button size="lg" render={<Link href="/signup" />}>
                Get started
                <ArrowRight />
              </Button>
              <Button size="lg" variant="outline" render={<Link href="/login" />}>
                Sign in
              </Button>
            </>
          )}
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-4 px-6 pb-24 sm:grid-cols-2">
        {features.map((f) => (
          <Card key={f.title} className="gap-3 transition-shadow hover:shadow-md">
            <CardHeader>
              <span className="mb-1 inline-flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <f.icon className="size-[18px]" />
              </span>
              <CardTitle className="text-lg">{f.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{f.body}</CardContent>
          </Card>
        ))}
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-5xl flex-col items-center justify-between gap-3 px-6 py-8 text-sm text-muted-foreground sm:flex-row">
          <Logo size="sm" />
          <p>Built for caregivers. Grounded in official program documentation.</p>
        </div>
      </footer>
    </main>
  );
}

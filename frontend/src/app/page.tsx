"use client";

import Link from "next/link";
import {
  ClipboardCheck,
  Compass,
  HeartHandshake,
  Scale,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { UncurlingArrow } from "@/components/uncurling-arrow";

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
    body: "A care calendar, timekeeping & journal, and a document store to keep care organized.",
  },
];

export default function Home() {
  return (
    <main className="flex flex-1 flex-col">
      <SiteHeader />

      <section className="mx-auto flex max-w-3xl flex-1 flex-col items-center justify-center gap-6 px-6 py-24 text-center">
        <h1 className="text-balance text-4xl sm:text-5xl">
          Benefits navigation that works for caregivers
        </h1>
        <p className="max-w-xl text-pretty text-lg text-muted-foreground">
          Unpaid caregivers spend hours navigating fragmented benefits programs. Ilera finds
          what you qualify for, optimizes your strategy, and completes the applications for you.
        </p>
        <Button size="lg" className="hover:pr-7" render={<Link href="/intake" />}>
          Discover programs
          <UncurlingArrow />
        </Button>
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

      <SiteFooter />
    </main>
  );
}

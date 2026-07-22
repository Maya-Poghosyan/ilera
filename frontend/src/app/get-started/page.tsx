"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  ExternalLink,
  MessageCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth-context";

const POKE_RECIPE_URL = "https://poke.com/r/DsatCoA1all";

type Step = "poke" | "done";

export default function GetStartedPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState<Step>("poke");

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/signup");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return null;
  }

  return (
    <main className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Logo />
        </div>
      </header>

      <section className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
        {/* Progress indicators */}
        <div className="flex items-center gap-3">
          <StepDot active={false} done={true} label="1" />
          <div className="h-px w-8 bg-border" />
          <StepDot active={step === "poke"} done={step === "done"} label="2" />
          <div className="h-px w-8 bg-border" />
          <StepDot active={step === "done"} done={false} label="3" />
        </div>

        {/* Step: Connect Poke */}
        {step === "poke" && (
          <Card className="w-full">
            <CardHeader className="text-center">
              <div className="mx-auto mb-2 flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                <MessageCircle className="size-5" />
              </div>
              <CardTitle className="text-xl">Connect Poke</CardTitle>
              <p className="text-sm text-muted-foreground">
                Poke delivers care reminders, appointment nudges, and benefit renewal
                alerts straight to your messages.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-brand-subtle bg-brand-subtle/30 p-4 space-y-3">
                <p className="text-sm font-medium">What you get with Poke:</p>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    Daily care-log check-ins via text
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    Appointment and renewal deadline reminders
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    Works with iMessage, WhatsApp, Telegram, or RCS
                  </li>
                  <li className="flex items-start gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    Email scanning for medical events (optional)
                  </li>
                </ul>
              </div>

              <a
                href={POKE_RECIPE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="block"
              >
                <Button className="w-full gap-1.5">
                  Set up Poke
                  <ExternalLink className="size-3.5" />
                </Button>
              </a>

              <button
                onClick={() => setStep("done")}
                className="w-full text-center text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                Skip for now
              </button>
            </CardContent>
          </Card>
        )}

        {/* Step: Done — proceed to intake */}
        {step === "done" && (
          <Card className="w-full min-w-[28rem] px-8 py-6">
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Check className="size-6" />
              </div>
              <CardTitle className="text-2xl">You&apos;re all set!</CardTitle>
              <p className="text-base text-muted-foreground">
                Welcome, {user.name}. Now let&apos;s figure out which benefits you qualify for.
              </p>
            </CardHeader>
            <CardContent>
              <Button className="w-full py-3 text-base" render={<Link href="/intake" />}>
                Start benefits intake
                <ArrowRight className="size-4" />
              </Button>
            </CardContent>
          </Card>
        )}
      </section>
    </main>
  );
}

function StepDot({
  active,
  done,
  label,
}: {
  active: boolean;
  done: boolean;
  label: string;
}) {
  return (
    <div
      className={`flex size-8 items-center justify-center rounded-full text-xs font-semibold transition-colors ${
        done
          ? "bg-primary text-primary-foreground"
          : active
            ? "border-2 border-primary text-primary"
            : "border border-border text-muted-foreground"
      }`}
    >
      {done ? <Check className="size-3.5" /> : label}
    </div>
  );
}

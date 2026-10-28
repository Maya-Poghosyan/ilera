"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  ArrowRight,
  Check,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SiteHeader } from "@/components/site-header";
import { useAuth } from "@/lib/auth-context";

export default function GetStartedPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  // This confirmation is the last step of onboarding, after the account
  // exists — anyone who lands here without one belongs in the intake.
  useEffect(() => {
    if (!loading && !user) router.replace("/intake");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center px-6 py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-foreground" />
      </main>
    );
  }

  const nextHref = user.case_id ? `/eligibility/${user.case_id}` : "/intake";

  return (
    <main className="flex flex-1 flex-col">
      <SiteHeader actions={null} />

      <section className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
          <Card className="w-full px-8 py-6">
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Check className="size-6" />
              </div>
              <CardTitle className="text-2xl">You&apos;re all set!</CardTitle>
              <p className="text-base text-muted-foreground">
                {user.case_id
                  ? "Your answers are saved to your account. Here are the programs you qualify for."
                  : "Let\u2019s figure out which benefits you qualify for."}
              </p>
            </CardHeader>
            <CardContent>
              <Button size="lg" className="w-full" render={<Link href={nextHref} />}>
                {user.case_id ? "See my results" : "Start benefits intake"}
                <ArrowRight className="size-4" />
              </Button>
            </CardContent>
          </Card>
      </section>
    </main>
  );
}

"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle, XCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Logo } from "@/components/logo";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      setErrorMessage("This verification link is invalid. Please sign up again.");
      return;
    }

    fetch("/api/auth/verify-email", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(
            body?.detail ?? "Verification failed. The link may have expired or already been used.",
          );
        }
        setStatus("success");
        // Hard navigation so AuthProvider re-initialises with the new session cookie.
        window.location.href = "/get-started";
      })
      .catch((err: unknown) => {
        setStatus("error");
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Verification failed. Please try signing up again.",
        );
      });
  }, [searchParams]);

  return (
    <main className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Logo />
        </div>
      </header>

      <section className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
        <Card className="w-full text-center">
          {status === "verifying" && (
            <>
              <CardHeader>
                <CardTitle className="text-xl">Verifying your email…</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">Just a moment.</p>
              </CardContent>
            </>
          )}

          {status === "success" && (
            <>
              <CardHeader>
                <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-green-100">
                  <CheckCircle className="size-6 text-green-600" />
                </div>
                <CardTitle className="text-xl">Email verified</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">Taking you to your account…</p>
              </CardContent>
            </>
          )}

          {status === "error" && (
            <>
              <CardHeader>
                <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-destructive/10">
                  <XCircle className="size-6 text-destructive" />
                </div>
                <CardTitle className="text-xl">Verification failed</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{errorMessage}</p>
                <p className="text-sm">
                  <a href="/signup" className="text-primary hover:underline">
                    Back to sign up
                  </a>
                </p>
              </CardContent>
            </>
          )}
        </Card>
      </section>
    </main>
  );
}

// useSearchParams requires a Suspense boundary in Next.js App Router.
export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailContent />
    </Suspense>
  );
}

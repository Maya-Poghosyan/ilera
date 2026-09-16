"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth-context";
import { clearPendingCaseId, getPendingCaseId } from "@/lib/pending-case";

export default function LoginPage() {
  const router = useRouter();
  const { login, verifyLoginOtp, updateUser } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"credentials" | "otp">("credentials");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      setStep("otp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await verifyLoginOtp(email, code);
      const pending = getPendingCaseId();
      if (!pending) {
        router.push("/dashboard");
        return;
      }
      try {
        await updateUser({ case_id: pending });
        router.push(`/eligibility/${pending}`);
      } catch {
        router.push("/dashboard");
      } finally {
        clearPendingCaseId();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setSubmitting(false);
    }
  };

  const header = (
    <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
        <Logo />
      </div>
    </header>
  );

  return (
    <main className="flex flex-1 flex-col">
      {header}
      <section className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
        <Card className="w-full">
          {step === "credentials" ? (
            <>
              <CardHeader className="text-center">
                <CardTitle className="text-xl">Sign in to Ilera</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Enter your email and password to continue.
                </p>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleCredentials} className="space-y-4">
                  {error && (
                    <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {error}
                    </div>
                  )}
                  <div className="space-y-1">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      required
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Your password"
                      required
                    />
                  </div>
                  <Button className="w-full" type="submit" disabled={submitting}>
                    {submitting ? "Checking..." : "Continue"}
                    <ArrowRight className="size-4" />
                  </Button>
                </form>
                <p className="mt-4 text-center text-sm text-muted-foreground">
                  Don&apos;t have an account?{" "}
                  <Link href="/signup" className="text-primary hover:underline">
                    Sign up
                  </Link>
                </p>
              </CardContent>
            </>
          ) : (
            <>
              <CardHeader className="text-center">
                <CardTitle className="text-xl">Check your email</CardTitle>
                <p className="text-sm text-muted-foreground">
                  We sent a 6-digit code to{" "}
                  <span className="font-medium text-foreground">{email}</span>.
                </p>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleOtp} className="space-y-4">
                  {error && (
                    <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {error}
                    </div>
                  )}
                  <div className="space-y-1">
                    <Label htmlFor="code">Login code</Label>
                    <Input
                      id="code"
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]{6}"
                      maxLength={6}
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                      placeholder="000000"
                      required
                      autoFocus
                    />
                  </div>
                  <Button className="w-full" type="submit" disabled={submitting || code.length !== 6}>
                    {submitting ? "Verifying..." : "Sign in"}
                    <ArrowRight className="size-4" />
                  </Button>
                </form>
                <p className="mt-4 text-center text-sm text-muted-foreground">
                  Wrong email?{" "}
                  <button
                    className="text-primary hover:underline"
                    onClick={() => { setStep("credentials"); setError(""); setCode(""); }}
                  >
                    Go back
                  </button>
                </p>
              </CardContent>
            </>
          )}
        </Card>
      </section>
    </main>
  );
}

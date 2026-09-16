"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth-context";
import { clearPendingCaseId, getPendingCaseId } from "@/lib/pending-case";

export default function SignupPage() {
  const { signup } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [verificationSent, setVerificationSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setSubmitting(true);
    try {
      await signup({ name, email, phone, password, case_id: getPendingCaseId() });
      clearPendingCaseId();
      setVerificationSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
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

  if (verificationSent) {
    return (
      <main className="flex flex-1 flex-col">
        {header}
        <section className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
          <Card className="w-full">
            <CardHeader className="text-center">
              <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-primary/10">
                <Mail className="size-6 text-primary" />
              </div>
              <CardTitle className="text-xl">Check your email</CardTitle>
              <p className="text-sm text-muted-foreground">
                We sent a verification link to{" "}
                <span className="font-medium text-foreground">{email}</span>.
                Click it to activate your account.
              </p>
            </CardHeader>
            <CardContent className="space-y-3 text-center text-sm text-muted-foreground">
              <p>The link expires in 1 hour. Check your spam folder if you don&apos;t see it.</p>
              <p>
                Wrong email?{" "}
                <button
                  className="text-primary hover:underline"
                  onClick={() => setVerificationSent(false)}
                >
                  Go back
                </button>
              </p>
            </CardContent>
          </Card>
        </section>
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col">
      {header}

      <section className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
        <Card className="w-full">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Create your account</CardTitle>
            <p className="text-sm text-muted-foreground">
              Save your plan, start your applications, and get reminders.
            </p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}
              <div className="space-y-1">
                <Label htmlFor="name">Your name</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="First name"
                  required
                />
              </div>
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
                <Label htmlFor="phone">Phone number</Label>
                <Input
                  id="phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="(555) 555-0123"
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
                  placeholder="At least 6 characters"
                  required
                  minLength={6}
                />
              </div>
              <Button
                className="w-full"
                type="submit"
                disabled={submitting || !name.trim() || !email.trim() || !phone.trim()}
              >
                {submitting ? "Creating account..." : "Create account"}
                <ArrowRight className="size-4" />
              </Button>
            </form>
            <p className="mt-4 text-center text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link href="/login" className="text-primary hover:underline">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

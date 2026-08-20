"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth-context";
import { clearPendingCaseId, getPendingCaseId } from "@/lib/pending-case";

export default function SignupPage() {
  const router = useRouter();
  const { signup, updateUser } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [hasPendingCase, setHasPendingCase] = useState(false);

  useEffect(() => {
    setHasPendingCase(getPendingCaseId() !== null);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setSubmitting(true);
    try {
      await signup(name, email, password);
      const pending = getPendingCaseId();
      if (pending) {
        // The case is claimed here; a stale id someone else already owns is refused, and
        // there is nothing the new account can do with it.
        try {
          await updateUser({ case_id: pending });
        } catch {
          /* the account still works without it */
        } finally {
          clearPendingCaseId();
        }
      }
      router.push("/get-started");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Logo />
        </div>
      </header>

      <section className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-8 px-6 py-16">
        <Card className="w-full">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">Create your account</CardTitle>
            <p className="text-sm text-muted-foreground">
              {hasPendingCase
                ? "Save your answers and see the programs you qualify for."
                : "Set up your Ilera caregiver profile to get started."}
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
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
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
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
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
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                  placeholder="At least 6 characters"
                  required
                  minLength={6}
                />
              </div>
              <Button className="w-full" type="submit" disabled={submitting || !name.trim() || !email.trim()}>
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

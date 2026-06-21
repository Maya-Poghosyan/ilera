"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { QuestionField } from "@/components/intake/question-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getIntakeSchema, submitIntakeAnswers } from "@/lib/api";
import {
  type Answers,
  type AnswerValue,
  type IntakeSchema,
  type MiniModule,
  type Question,
  type Screen,
  evalCondition,
  recipientName,
  validateQuestions,
} from "@/lib/intake-schema";

type Step =
  | { kind: "screen"; screen: Screen }
  | { kind: "module"; module: MiniModule };

export default function IntakePage() {
  const router = useRouter();
  const [schema, setSchema] = useState<IntakeSchema | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getIntakeSchema()
      .then(setSchema)
      .catch(() => setLoadError("Could not load the intake form. Is the backend running on :8000?"));
  }, []);

  // The active step list = all base screens + any triggered mini-modules (A–F).
  // Recomputed from answers so modules appear/disappear as the user responds.
  const steps: Step[] = useMemo(() => {
    if (!schema) return [];
    const base: Step[] = schema.screens.map((screen) => ({ kind: "screen" as const, screen }));
    const modules: Step[] = schema.mini_modules
      .filter((m) => evalCondition(m.trigger, answers))
      .map((module) => ({ kind: "module" as const, module }));
    return [...base, ...modules];
  }, [schema, answers]);

  if (loadError) {
    return (
      <main className="mx-auto max-w-xl px-6 py-20 text-center">
        <p className="text-muted-foreground">{loadError}</p>
      </main>
    );
  }

  if (!schema) {
    return (
      <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-foreground" />
        <p className="text-sm text-muted-foreground">Loading the intake form…</p>
      </main>
    );
  }

  const name = recipientName(answers, schema);

  if (!started) {
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 py-16">
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{schema.welcome.header}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <p className="text-sm text-muted-foreground">{schema.welcome.body}</p>
            <Button onClick={() => setStarted(true)}>{schema.welcome.button}</Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  const safeIndex = Math.min(stepIndex, steps.length - 1);
  const step = steps[safeIndex];
  const title = step.kind === "screen" ? step.screen.title : step.module.title;
  const introText = step.kind === "screen" ? step.screen.intro_text : undefined;
  const allQuestions: Question[] = step.kind === "screen" ? step.screen.questions : step.module.questions;
  // Apply per-question show_when within the current step.
  const visibleQuestions = allQuestions.filter((q) => evalCondition(q.show_when, answers));

  const pct = ((safeIndex + 1) / steps.length) * 100;
  const isLast = safeIndex === steps.length - 1;

  function setAnswer(fieldId: string, value: AnswerValue) {
    setAnswers((prev) => ({ ...prev, [fieldId]: value }));
    setErrors((prev) => {
      if (!prev[fieldId]) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  }

  function validateCurrent(): boolean {
    const errs = validateQuestions(visibleQuestions, answers);
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function next() {
    if (!validateCurrent()) return;
    if (isLast) {
      void finish();
      return;
    }
    setStepIndex((s) => Math.min(s + 1, steps.length - 1));
    setErrors({});
    if (typeof window !== "undefined") window.scrollTo({ top: 0 });
  }

  function back() {
    setStepIndex((s) => Math.max(s - 1, 0));
    setErrors({});
    if (typeof window !== "undefined") window.scrollTo({ top: 0 });
  }

  async function finish() {
    setSubmitting(true);
    try {
      const created = await submitIntakeAnswers(answers);
      router.push(`/eligibility/${created.id}`);
    } catch {
      setSubmitting(false);
      alert("Could not reach the API. Is the backend running on :8000?");
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 py-12">
      <div className="space-y-2">
        <Progress value={pct} />
        <p className="text-sm text-muted-foreground">
          Step {stepIndex + 1} of {steps.length}: {title}
          {step.kind === "module" && (
            <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs">
              Follow-up for programs that may fit
            </span>
          )}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {introText && (
            <p className="text-sm text-muted-foreground">{introText.replaceAll("[recipient name]", name)}</p>
          )}
          {visibleQuestions.map((q) => (
            <QuestionField
              key={q.field_id}
              question={q}
              value={answers[q.field_id] ?? null}
              name={name}
              error={errors[q.field_id]}
              onChange={(v) => setAnswer(q.field_id, v)}
            />
          ))}
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Button variant="outline" disabled={stepIndex === 0} onClick={back}>
          Back
        </Button>
        <Button onClick={next} disabled={submitting}>
          {submitting ? "Submitting…" : isLast ? schema.submit_button : "Next"}
        </Button>
      </div>
    </main>
  );
}

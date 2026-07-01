"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { QuestionField } from "@/components/intake/question-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { RequireAuth } from "@/components/require-auth";
import { useAuth } from "@/lib/auth-context";
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

const MAX_PER_PAGE = 2;

interface Page {
  key: string;
  title: string;
  isModule: boolean;
  introText?: string;
  showIntro: boolean;
  questions: Question[];
}

// Split a screen's visible questions into balanced pages of at most MAX_PER_PAGE
// (the spec groups up to 6 questions on a screen, but no page may show > 5).
function paginate(questions: Question[]): Question[][] {
  if (questions.length <= MAX_PER_PAGE) return questions.length ? [questions] : [];
  const pageCount = Math.ceil(questions.length / MAX_PER_PAGE);
  const perPage = Math.ceil(questions.length / pageCount);
  const out: Question[][] = [];
  for (let i = 0; i < questions.length; i += perPage) {
    out.push(questions.slice(i, i + perPage));
  }
  return out;
}

export default function IntakePage() {
  return (
    <RequireAuth>
      <IntakeContent />
    </RequireAuth>
  );
}

function IntakeContent() {
  const router = useRouter();
  const { updateUser } = useAuth();
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

  // The active flow = all base screens + any triggered mini-modules (A–F), each
  // split into pages of ≤5 visible questions. Recomputed from answers so
  // conditional questions and mini-modules appear/disappear as the user responds.
  const pages: Page[] = useMemo(() => {
    if (!schema) return [];
    const sections: { id: string; title: string; intro?: string; isModule: boolean; questions: Question[] }[] = [
      ...schema.screens.map((s: Screen) => ({
        id: s.id,
        title: s.title,
        intro: s.intro_text,
        isModule: false,
        questions: s.questions,
      })),
      ...schema.mini_modules
        .filter((m: MiniModule) => evalCondition(m.trigger, answers))
        .map((m: MiniModule) => ({ id: m.id, title: m.title, isModule: true, questions: m.questions })),
    ];

    const out: Page[] = [];
    for (const section of sections) {
      const visible = section.questions.filter((q) => evalCondition(q.show_when, answers));
      const chunks = paginate(visible);
      chunks.forEach((chunk, i) => {
        out.push({
          key: `${section.id}-${i}`,
          title: section.title,
          isModule: section.isModule,
          introText: section.intro,
          showIntro: i === 0,
          questions: chunk,
        });
      });
    }
    return out;
  }, [schema, answers]);

  if (loadError) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-20 text-center">
        <p className="text-muted-foreground">{loadError}</p>
      </main>
    );
  }

  if (!schema) {
    return (
      <main className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-foreground" />
        <p className="text-sm text-muted-foreground">Loading the intake form…</p>
      </main>
    );
  }

  const name = recipientName(answers, schema);

  if (!started) {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-16">
        <div className="space-y-6">
          <h1 className="text-xl font-semibold">{schema.welcome.header}</h1>
          <p className="text-sm text-muted-foreground">{schema.welcome.body}</p>
          <Button onClick={() => setStarted(true)}>{schema.welcome.button}</Button>
        </div>
      </main>
    );
  }

  const safeIndex = Math.min(stepIndex, pages.length - 1);
  const page = pages[safeIndex];
  const visibleQuestions = page.questions;

  const pct = ((safeIndex + 1) / pages.length) * 100;
  const isLast = safeIndex === pages.length - 1;

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
    setStepIndex((s) => Math.min(s + 1, pages.length - 1));
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
      localStorage.setItem("ilera_case_id", created.id);
      await updateUser({ case_id: created.id });
      router.push(`/eligibility/${created.id}`);
    } catch {
      setSubmitting(false);
      alert("Could not reach the API. Is the backend running on :8000?");
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-12">
      <div className="space-y-2">
        <Progress value={pct} />
        <p className="text-sm text-muted-foreground">
          Step {safeIndex + 1} of {pages.length}: {page.title}
          {page.isModule && (
            <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs">
              Follow-up for programs that may fit
            </span>
          )}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{page.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {page.showIntro && page.introText && (
            <p className="text-sm text-muted-foreground">{page.introText.replaceAll("[recipient name]", name)}</p>
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

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QuestionField } from "@/components/intake/question-field";
import { LoadFailure } from "@/components/load-failure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/lib/auth-context";
import { ApiError, getIntakeSchema, lookupCounty, submitIntakeAnswers } from "@/lib/api";
import { setPendingCaseId } from "@/lib/pending-case";
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
// Answers only reach the server on the final submit, so keep a local copy in the
// meantime — a refresh mid-intake shouldn't cost the user everything they typed.
const DRAFT_KEY = "ilera_intake_draft";
const HEAVY_OPTION_THRESHOLD = 5;

interface Draft {
  answers: Answers;
  stepIndex: number;
}

function readDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as Draft;
    if (!draft.answers || Object.keys(draft.answers).length === 0) return null;
    return { answers: draft.answers, stepIndex: draft.stepIndex ?? 0 };
  } catch {
    return null;
  }
}

interface Page {
  key: string;
  title: string;
  isModule: boolean;
  introText?: string;
  showIntro: boolean;
  questions: Question[];
}

function isHeavy(q: Question): boolean {
  return (q.options?.length ?? 0) > HEAVY_OPTION_THRESHOLD;
}

function paginate(questions: Question[]): Question[][] {
  if (questions.length === 0) return [];

  // Collect consecutive runs of questions sharing the same group tag.
  const runs: Question[][] = [];
  let i = 0;
  while (i < questions.length) {
    const g = questions[i].group;
    if (g) {
      const run: Question[] = [];
      while (i < questions.length && questions[i].group === g) {
        run.push(questions[i]);
        i++;
      }
      runs.push(run);
    } else {
      runs.push([questions[i]]);
      i++;
    }
  }

  const out: Question[][] = [];
  let buf: Question[] = [];
  for (const run of runs) {
    const heavy = run.length === 1 && isHeavy(run[0]);
    if (heavy) {
      if (buf.length) { out.push(buf); buf = []; }
      out.push(run);
    } else if (run.length > MAX_PER_PAGE) {
      // Group is bigger than a page — give it its own page.
      if (buf.length) { out.push(buf); buf = []; }
      out.push(run);
    } else if (buf.length + run.length > MAX_PER_PAGE) {
      // Won't fit — flush current buffer, start new page with this group.
      if (buf.length) { out.push(buf); buf = []; }
      buf.push(...run);
    } else {
      buf.push(...run);
    }
    if (buf.length >= MAX_PER_PAGE) { out.push(buf); buf = []; }
  }
  if (buf.length) out.push(buf);
  return out;
}

const INLINE_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
};

function renderQuestions(
  questions: Question[],
  name: string,
  answers: Answers,
  errors: Record<string, string>,
  setAnswer: (fieldId: string, value: AnswerValue) => void,
) {
  const elements: React.ReactNode[] = [];
  let i = 0;
  while (i < questions.length) {
    const cur = questions[i];
    if (cur.layout === "inline") {
      const inlineGroup: Question[] = [cur];
      const g = cur.group;
      let j = i + 1;
      while (j < questions.length && questions[j].layout === "inline" && questions[j].group === g) {
        inlineGroup.push(questions[j]);
        j++;
      }
      elements.push(
        <div
          key={`inline-${cur.field_id}`}
          className={`grid gap-4 ${INLINE_COLS[inlineGroup.length] ?? "grid-cols-2"}`}
        >
          {inlineGroup.map((iq) => (
            <QuestionField
              key={iq.field_id}
              question={iq}
              value={answers[iq.field_id] ?? null}
              name={name}
              error={errors[iq.field_id]}
              onChange={(v) => setAnswer(iq.field_id, v)}
            />
          ))}
        </div>,
      );
      i = j;
    } else {
      elements.push(
        <QuestionField
          key={cur.field_id}
          question={cur}
          value={answers[cur.field_id] ?? null}
          name={name}
          error={errors[cur.field_id]}
          onChange={(v) => setAnswer(cur.field_id, v)}
        />,
      );
      i++;
    }
  }
  return elements;
}

/**
 * Arrow that grows to the right on hover, pushing its head into the extra padding.
 * Rendered at 1 viewBox unit per px, so the head's translate matches the shaft's growth.
 */
function UncurlingArrow() {
  return (
    <svg
      viewBox="0 0 22 12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-3 w-[22px] overflow-visible"
    >
      {/* Drawn left to right: dashoffset trims the far end, so it extends rightwards. */}
      <path
        d="M1 6H21"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={0.4}
        className="transition-[stroke-dashoffset] duration-300 ease-out group-hover/button:[stroke-dashoffset:0]"
      />
      <path
        d="M9 2l4 4-4 4"
        className="transition-transform duration-300 ease-out group-hover/button:translate-x-[8px]"
      />
    </svg>
  );
}

export default function IntakePage() {
  const router = useRouter();
  const { user, updateUser } = useAuth();
  const [schema, setSchema] = useState<IntakeSchema | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [started, setStarted] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [animating, setAnimating] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  // Synchronous debounce: the `submitting` state only disables the button on the
  // next render, so a rapid double-click can call finish() twice before then. This
  // ref flips immediately, so the second call is dropped and only one intake POST
  // (and thus one Band room) is ever created.
  const submittingRef = useRef(false);
  // County values we filled in from a ZIP lookup, so a prefill can be replaced by a
  // later ZIP but anything the user typed themselves is left alone.
  const [prefilledCounties, setPrefilledCounties] = useState<Record<string, string>>({});

  const slide = useCallback((dir: "left" | "right", cb: () => void) => {
    const el = cardRef.current;
    if (!el) { cb(); return; }
    setAnimating(true);
    el.style.transition = "transform 250ms ease, opacity 250ms ease";
    el.style.transform = dir === "left" ? "translateX(-40px)" : "translateX(40px)";
    el.style.opacity = "0";
    const onEnd = () => {
      el.removeEventListener("transitionend", onEnd);
      cb();
      el.style.transition = "none";
      el.style.transform = dir === "left" ? "translateX(40px)" : "translateX(-40px)";
      el.style.opacity = "0";
      void el.offsetHeight;
      el.style.transition = "transform 250ms ease, opacity 250ms ease";
      el.style.transform = "translateX(0)";
      el.style.opacity = "1";
      const onIn = () => { el.removeEventListener("transitionend", onIn); setAnimating(false); };
      el.addEventListener("transitionend", onIn, { once: true });
    };
    el.addEventListener("transitionend", onEnd, { once: true });
  }, []);

  useEffect(() => {
    getIntakeSchema()
      .then((loaded) => {
        setLoadError(null);
        // Resume an interrupted intake. Restored alongside the schema so the first
        // render with questions already has the draft in hand.
        const draft = readDraft();
        if (draft) {
          setAnswers(draft.answers);
          setStepIndex(draft.stepIndex);
          setStarted(true);
        }
        setSchema(loaded);
      })
      .catch(() => setLoadError("We couldn't load the intake questions just now."));
  }, [loadAttempt]);

  useEffect(() => {
    if (!started) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ answers, stepIndex }));
  }, [started, answers, stepIndex]);

  // The active flow = all base screens + any triggered mini-modules (A–F), each
  // split into pages of ≤5 visible questions. Recomputed from answers so
  // conditional questions and mini-modules appear/disappear as the user responds.
  const pages: Page[] = useMemo(() => {
    if (!schema) return [];
    const contact = schema.contact_screen;
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
      { id: contact.id, title: contact.title, intro: contact.intro_text, isModule: false, questions: contact.questions },
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
      <LoadFailure message={loadError} onRetry={() => setLoadAttempt((n) => n + 1)} />
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
          {schema.welcome.body && (
            <p className="text-sm text-muted-foreground">{schema.welcome.body}</p>
          )}
          <Button
            size="lg"
            onClick={() => setStarted(true)}
            className="h-11 gap-1.5 px-3.5 text-base ring-primary/35 duration-300 ease-out hover:pr-6 active:ring-4"
          >
            {schema.welcome.button}
            <UncurlingArrow />
          </Button>
        </div>
      </main>
    );
  }

  const safeIndex = Math.min(stepIndex, pages.length - 1);
  const page = pages[safeIndex];
  const visibleQuestions = page.questions;

  function prefillCounty(zipFieldId: string, zip: AnswerValue) {
    const prefix = zipFieldId.slice(0, -"zip".length);
    const countyField = `${prefix}county`;
    const current = answers[countyField];
    if (current && current !== prefilledCounties[countyField]) return;
    if (typeof zip !== "string" || !/^\d{5}$/.test(zip)) return;
    const state = answers[`${prefix}state`];
    lookupCounty(zip, typeof state === "string" ? state : "")
      .then(({ county }) => {
        if (!county) return;
        setAnswers((prev) => ({ ...prev, [countyField]: county }));
        setPrefilledCounties((prev) => ({ ...prev, [countyField]: county }));
      })
      .catch(() => { /* leave the field for the user to fill in */ });
  }

  const pct = ((safeIndex + 1) / pages.length) * 100;
  const isLast = safeIndex === pages.length - 1;

  function setAnswer(fieldId: string, value: AnswerValue) {
    if (fieldId.endsWith(".address.zip")) {
      prefillCounty(fieldId, value);
    }
    setAnswers((prev) => {
      const next = { ...prev, [fieldId]: value };
      // Derive recipient.age from date_of_birth so mini-module triggers work
      if (fieldId === "recipient.date_of_birth" && typeof value === "string" && value) {
        try {
          const bd = new Date(value);
          const today = new Date();
          let age = today.getFullYear() - bd.getFullYear();
          if (today.getMonth() < bd.getMonth() || (today.getMonth() === bd.getMonth() && today.getDate() < bd.getDate())) {
            age--;
          }
          next["recipient.age"] = age;
        } catch { /* ignore invalid dates */ }
      }
      return next;
    });
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
    slide("left", () => {
      setStepIndex((s) => Math.min(s + 1, pages.length - 1));
      setErrors({});
      if (typeof window !== "undefined") window.scrollTo({ top: 0 });
    });
  }

  function back() {
    slide("right", () => {
      setStepIndex((s) => Math.max(s - 1, 0));
      setErrors({});
      if (typeof window !== "undefined") window.scrollTo({ top: 0 });
    });
  }

  async function finish() {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const created = await submitIntakeAnswers(answers);
      localStorage.removeItem(DRAFT_KEY);
      localStorage.setItem("ilera_case_id", created.id);
      if (user) {
        await updateUser({ case_id: created.id });
        router.push(`/eligibility/${created.id}`);
      } else {
        setPendingCaseId(created.id);
        router.push("/signup");
      }
    } catch (err) {
      // The draft is still in localStorage, so nothing they typed is lost — the button just
      // becomes pressable again.
      submittingRef.current = false;
      setSubmitting(false);
      const transient = err instanceof ApiError && err.isTransient;
      alert(
        transient
          ? "We couldn't save your answers just now — your place is saved, so please try again in a moment."
          : "Something went wrong saving your answers. Your place is saved, so please try again.",
      );
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-12">
      <div className="space-y-2">
        <Progress value={pct} />
      </div>

      <Card ref={cardRef} className="overflow-visible">
        <CardHeader>
          <CardTitle>{page.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6 overflow-visible">
          {page.showIntro && page.introText && (
            <p className="text-sm text-muted-foreground">{page.introText.replaceAll("[recipient name]", name)}</p>
          )}
          {renderQuestions(visibleQuestions, name, answers, errors, setAnswer)}
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

"use client";

import { useRouter } from "next/navigation";
import { ExternalLink } from "lucide-react";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { SuggestionPanel } from "@/components/intake/documents/suggestion-panel";
import { UploadCard } from "@/components/intake/documents/upload-card";
import { useIntakeDocuments } from "@/components/intake/documents/use-intake-documents";
import { QuestionField } from "@/components/intake/question-field";
import { LoadFailure } from "@/components/load-failure";
import { Button } from "@/components/ui/button";
import { UncurlingArrow } from "@/components/uncurling-arrow";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/lib/auth-context";
import { ApiError, getIntakeSchema, lookupCounty, submitIntakeAnswers } from "@/lib/api";
import { setPendingCaseId } from "@/lib/pending-case";
import {
  type Answers,
  type AnswerValue,
  type IntakeSchema,
  type Question,
  cleanAnswers,
  interpolateName,
  recipientName,
} from "@/lib/intake-schema";

import { buildPages, pageIndex, resumePage, intakeIssues } from "@/lib/intake-flow";

// Save responses and the current card automatically on this browser.
const DRAFT_KEY = "ilera_intake_draft";

interface Draft {
  answers: Answers;
  questionId: string | null;
  version?: string;
  review?: boolean;
}

function readDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as Draft;
    if (!draft.answers || Object.keys(draft.answers).length === 0) return null;
    return { answers: draft.answers, questionId: draft.questionId ?? null, version: draft.version, review: draft.review === true };
  } catch {
    return null;
  }
}

// Stacked on narrow screens, side by side once there's room for readable fields.
const INLINE_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-3",
};
const INLINE_COLS_FALLBACK = "grid-cols-1 sm:grid-cols-2";

function renderQuestions(
  questions: Question[],
  name: string,
  answers: Answers,
  errors: Record<string, string>,
  setAnswer: (fieldId: string, value: AnswerValue) => void,
  before: (question: Question) => React.ReactNode = () => null,
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
      for (const iq of inlineGroup) {
        const prefix = before(iq);
        if (prefix) elements.push(<div key={`before-${iq.field_id}`}>{prefix}</div>);
      }
      elements.push(
        <div
          key={`inline-${cur.field_id}`}
          className={`grid items-end gap-5 ${INLINE_COLS[inlineGroup.length] ?? INLINE_COLS_FALLBACK}`}
        >
          {inlineGroup.map((iq) => (
            <QuestionField
              key={iq.field_id}
              question={iq}
              answers={answers}
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
      const prefix = before(cur);
      if (prefix) elements.push(<div key={`before-${cur.field_id}`}>{prefix}</div>);
      elements.push(
        <QuestionField
          key={cur.field_id}
          question={cur}
          answers={answers}
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
 * The box is only as wide as the resting art; the growth overflows into that padding.
 */
export default function IntakePage() {
  const router = useRouter();
  const { user, updateUser } = useAuth();
  const [schema, setSchema] = useState<IntakeSchema | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [started, setStarted] = useState(false);
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [savedDraft, setSavedDraft] = useState<Draft | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [showReview, setShowReview] = useState(false);
  const documents = useIntakeDocuments();
  const pendingFocus = useRef<string | null>(null);
  // Synchronous debounce: the `submitting` state only disables the button on the
  // next render, so a rapid double-click can call finish() twice before then. This
  // ref flips immediately, so the second call is dropped and only one intake POST
  // (and thus one case) is ever created.
  const submittingRef = useRef(false);
  // County values we filled in from a ZIP lookup, so a prefill can be replaced by a
  // later ZIP but anything the user typed themselves is left alone.
  const [prefilledCounties, setPrefilledCounties] = useState<Record<string, string>>({});

  useEffect(() => {
    getIntakeSchema()
      .then((loaded) => {
        setLoadError(null);
        setSavedDraft(readDraft());
        setSchema(loaded);
      })
      .catch(() => setLoadError("We couldn't load the intake questions just now."));
  }, [loadAttempt]);

  const pages = useMemo(() => schema ? buildPages(schema, answers) : [], [schema, answers]);
  const issues = useMemo(() => intakeIssues(pages, answers), [pages, answers]);

  useEffect(() => {
    if (!started || !schema || submittingRef.current) return;
    const draft = { answers: cleanAnswers(schema, answers), questionId: activeQuestionId, version: schema.version, review: showReview };
    let cancelled = false;
    // Persist after this render, before the next browser event. Cancel obsolete
    // renders so they cannot overwrite newer responses or a completed submission.
    queueMicrotask(() => {
      if (cancelled || submittingRef.current) return;
      try {
        if (Object.keys(draft.answers).length) {
          localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
          setSaveMessage("Saved on this browser");
        } else {
          localStorage.removeItem(DRAFT_KEY);
          setSaveMessage(null);
        }
      } catch {
        setSaveMessage("Couldn’t save. Keep this tab open.");
      }
    });
    return () => { cancelled = true; };
  }, [started, schema, answers, activeQuestionId, showReview]);

  useEffect(() => {
    if (showReview) {
      document.getElementById('intake-review-title')?.focus();
    } else if (pendingFocus.current) {
      document.getElementById(`intake-${pendingFocus.current}`)?.focus();
      pendingFocus.current = null;
    }
  }, [showReview, activeQuestionId]);

  function startOver() {
    if (submittingRef.current) return;
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch {
      setSaveMessage("We couldn’t clear your saved progress on this browser. Your answers have been kept.");
      return;
    }
    setAnswers({});
    setActiveQuestionId(null);
    setErrors({});
    setShowReview(false);
    setPrefilledCounties({});
    documents.reset();
    setSavedDraft(null);
    setSaveMessage(null);
    setStarted(true);
    window.scrollTo({ top: 0 });
  }

  function continueSavedDraft() {
    if (!schema || !savedDraft) return;
    const restored = cleanAnswers(schema, savedDraft.answers);
    setAnswers(restored);
    setActiveQuestionId(resumePage(buildPages(schema, restored), savedDraft.questionId, restored));
    setShowReview(savedDraft.review === true);
    setStarted(true);
  }

  const onArrowNavigation = useEffectEvent((event: KeyboardEvent) => {
    if (!started || !schema || showReview || submittingRef.current || event.defaultPrevented || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const target = event.target;
    if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"], [role="combobox"], [role="listbox"], [role="menu"], [role="slider"], [role="spinbutton"], [role="grid"], [role="dialog"]')) return;
    if (event.key === 'ArrowRight' && isLast) return;
    event.preventDefault();
    if (event.key === 'ArrowLeft') back();
    else next();
  });
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => onArrowNavigation(event);
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

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
          <h1 className="text-xl">{schema.welcome.header}</h1>
          {schema.welcome.body && (
            <p className="text-sm text-muted-foreground">{schema.welcome.body}</p>
          )}
          {savedDraft && <p className="text-sm text-muted-foreground">You have saved progress on this browser. Continue where you left off or start over.</p>}
          <Button
            size="lg"
            onClick={() => savedDraft ? continueSavedDraft() : setStarted(true)}
            className="hover:pr-6"
          >
            {savedDraft ? "Continue saved progress" : schema.welcome.button}
            <UncurlingArrow />
          </Button>
          {savedDraft && <Button variant="ghost" onClick={startOver}>Start over</Button>}
          {saveMessage && <p role="status" className="text-sm text-muted-foreground">{saveMessage}</p>}
        </div>
      </main>
    );
  }

  const safeIndex = pageIndex(pages, activeQuestionId);
  const page = pages[safeIndex];
  const sectionTitle = pages.slice(0, safeIndex + 1).findLast((p) => p.kind === "intro")?.title;
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
        setAnswers((prev) => {
          if (prev[zipFieldId] !== zip || prev[`${prefix}state`] !== state) return prev;
          if (prev[countyField] && prev[countyField] !== prefilledCounties[countyField]) return prev;
          return cleanAnswers(schema!, { ...prev, [countyField]: county });
        });
        setPrefilledCounties((prev) => ({ ...prev, [countyField]: county }));
      })
      .catch(() => { /* leave the field for the user to fill in */ });
  }

  const pct = ((safeIndex + 1) / pages.length) * 100;
  const isLast = safeIndex === pages.length - 1;
  const showPageTitle = page.kind === "intro";

  function suggestionPanel(question: Question) {
    const pending = documents.pendingFor(question.field_id);
    return pending.length ? <SuggestionPanel pending={pending} answers={answers} recipientName={name} onApply={setAnswer} onDismiss={documents.dismiss} /> : null;
  }

  function setAnswer(fieldId: string, value: AnswerValue) {
    if (fieldId.endsWith(".address.zip")) {
      prefillCounty(fieldId, value);
    }
    setAnswers((prev) => {
      const next = { ...prev, [fieldId]: value };
      if (fieldId === 'recipient.coverage_and_benefits' && Array.isArray(value)) next['recipient.medicaid_covered'] = value.includes('Medicaid' as never);
      return cleanAnswers(schema!, next);
    });
    setErrors((prev) => {
      if (!prev[fieldId]) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  }

  function next() {
    if (isLast) {
      void finish();
      return;
    }
    setActiveQuestionId(pages[safeIndex + 1].key);
    setErrors({});
    window.scrollTo({ top: 0 });
  }

  function back() {
    if (safeIndex === 0) return;
    setActiveQuestionId(pages[safeIndex - 1].key);
    setErrors({});
    window.scrollTo({ top: 0 });
  }

  async function finish() {
    if (submittingRef.current) return;
    if (issues.length) {
      setErrors(Object.fromEntries(issues.map(issue => [issue.question.field_id, issue.message])));
      setShowReview(true);
      window.scrollTo({ top: 0 });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const created = await submitIntakeAnswers(cleanAnswers(schema!, answers));
      localStorage.removeItem(DRAFT_KEY);
      localStorage.setItem("ilera_case_id", created.id);
      // Straight to the results screen — an account is offered there, once there is a strategy
      // worth saving. The case id is parked so that signup can claim it.
      setPendingCaseId(created.id);
      router.push(`/eligibility/${created.id}`);
      if (user) {
        // Attaching the case to the account is not something to keep the caregiver waiting on.
        void updateUser({ case_id: created.id }).catch(() => {});
      }
    } catch (err) {
      // Keep the automatic draft after a failed submit.
      submittingRef.current = false;
      setSubmitting(false);
      const transient = err instanceof ApiError && err.isTransient;
      alert(
        transient
          ? "We couldn't submit your answers just now. They are still in this tab; please try again in a moment."
          : "Something went wrong submitting your answers. They are still in this tab; please try again.",
      );
    }
  }

  if (showReview) {
    const sections = [...new Set(issues.map(issue => issue.section))];
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-14">
        <h1 id="intake-review-title" tabIndex={-1} className="text-2xl">{issues.length ? "Complete your answers" : "Ready to submit"}</h1>
        {sections.map(section => (
          <Card key={section}>
            <CardHeader><CardTitle>{interpolateName(section, name)}</CardTitle></CardHeader>
            <CardContent>
              <ul className="space-y-4">
                {issues.filter(issue => issue.section === section).map(issue => (
                  <li key={issue.question.field_id}>
                    <a href={`#intake-${issue.question.field_id}`} className="text-primary underline underline-offset-4" onClick={event => {
                      event.preventDefault();
                      pendingFocus.current = issue.question.field_id;
                      setErrors(Object.fromEntries(issues.map(item => [item.question.field_id, item.message])));
                      setActiveQuestionId(issue.question.field_id);
                      setShowReview(false);
                      window.scrollTo({ top: 0 });
                    }}>{interpolateName(issue.question.text, name)}</a>
                    <p className="mt-1 text-sm text-destructive">{issue.message}</p>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
        <div className="flex justify-between gap-4">
          <Button variant="outline" disabled={submitting} onClick={() => setShowReview(false)}>Back to intake</Button>
          <Button disabled={submitting || issues.length > 0} onClick={() => void finish()}>{submitting ? "Submitting…" : schema.submit_button}</Button>
        </div>
        {saveMessage && <p role="status" className="text-sm text-muted-foreground">{saveMessage}</p>}
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-8 px-6 py-14">
      <div className="space-y-2">
        {page.kind === "questions" && <h2 className="text-2xl">{interpolateName(sectionTitle ?? page.title, name)}</h2>}
        <Progress value={pct} />
      </div>

      <Card key={page.key} className="overflow-visible text-base [--card-spacing:--spacing(7)]">
        {showPageTitle && <CardHeader>
          <CardTitle className="text-2xl">{interpolateName(page.title, name)}</CardTitle>
        </CardHeader>}
        <CardContent className={`space-y-7 overflow-visible ${showPageTitle ? "-mt-3" : ""}`}>
          {page.kind === "questions" && (page.helperText || page.helperLink) && <div className="space-y-2">
            {page.helperText && <p className="text-sm text-muted-foreground">{interpolateName(page.helperText, name)}</p>}
            {page.helperLink && <a href={page.helperLink.href} target="_blank" rel="noreferrer" className="group flex w-fit items-center gap-1.5 text-sm text-primary">
              <span className="relative after:absolute after:-bottom-0.5 after:left-0 after:h-px after:w-full after:origin-left after:scale-x-0 after:bg-current after:transition-transform after:duration-300 group-hover:after:scale-x-100 group-focus-visible:after:scale-x-100">{page.helperLink.text}</span>
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </a>}
          </div>}
          {page.kind === "intro" ? <div className="space-y-4 text-base text-muted-foreground">
            <p>{page.introEmphasis && page.introText?.includes(page.introEmphasis) ? <>{page.introText.slice(0, page.introText.indexOf(page.introEmphasis))}<strong className="font-semibold">{page.introEmphasis}</strong>{page.introText.slice(page.introText.indexOf(page.introEmphasis) + page.introEmphasis.length)}</> : page.introText}</p>
            {page.introDocuments && <table className="w-full table-fixed text-left text-sm sm:text-base">
              <thead className="text-foreground">
                <tr>
                  <th scope="col" className="w-[45%] pb-3 pr-6 font-medium">Document</th>
                  <th scope="col" className="pb-3 font-medium">Where to find it</th>
                </tr>
              </thead>
              <tbody>
                {page.introDocuments.map(item => <tr key={item.document} className="align-top">
                  <td className="py-2 pr-6">{item.document}</td>
                  <td className="py-2">{item.location}</td>
                </tr>)}
              </tbody>
            </table>}
            {page.introEmphasis && !page.introText?.includes(page.introEmphasis) && <p><strong className="font-semibold">{page.introEmphasis}</strong></p>}
          </div> : renderQuestions(visibleQuestions, name, answers, errors, setAnswer, suggestionPanel)}
        </CardContent>
      </Card>

      {page.uploadDocuments && <UploadCard
        suggested={page.uploadDocuments}
        limits={schema.document_upload}
        documents={documents.documents}
        onAdd={documents.add}
        onRemove={documents.remove}
      />}

      <div className="flex justify-between">
        <Button size="lg" variant="outline" disabled={safeIndex === 0 || submitting} onClick={back}>
          Back
        </Button>
        <Button size="lg" onClick={next} disabled={submitting}>
          {submitting ? "Submitting…" : isLast ? schema.submit_button : page.kind === "intro" ? "Continue" : "Next"}
        </Button>
      </div>
      <div className="space-y-2 border-t pt-4">
        <div className="flex items-center justify-between gap-3">
          <Button variant="ghost" disabled={submitting} onClick={startOver}>Start over</Button>
          <div className="flex items-center gap-1">
            {saveMessage && <span role="status" className="text-sm text-muted-foreground">{saveMessage}</span>}
            <Button variant="ghost" disabled={submitting} onClick={() => { setShowReview(true); window.scrollTo({ top: 0 }); }}>Review answers</Button>
          </div>
        </div>
      </div>
    </main>
  );
}

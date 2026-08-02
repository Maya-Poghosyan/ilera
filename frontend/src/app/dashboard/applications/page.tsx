"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { QuestionField } from "@/components/intake/question-field";
import {
  completeApplication,
  listApplications,
  previewApplication,
  startApplication,
  updateAppStatus,
} from "@/lib/api";
import {
  type Answers,
  type AnswerValue,
  type Question,
  validateQuestions,
} from "@/lib/intake-schema";
import type {
  AppQuestion,
  AppStatus,
  ApplicationEntry,
  EligibilityStatus,
} from "@/lib/types";

const eligibilityColor: Record<EligibilityStatus, string> = {
  likely: "border-transparent bg-emerald-500 text-white",
  possible: "border-transparent bg-amber-500 text-white",
  unlikely: "border-transparent bg-rose-500 text-white",
  needs_info: "border-transparent bg-sky-600 text-white",
};

const APP_STATUS_LABELS: Record<AppStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  needs_info: "Needs info",
  completed: "Completed",
};

type FlowStep = "list" | "loading" | "questions" | "completing" | "preview";

/** The inputs the backend put under one `group_id`: one thing a person knows. */
function groupQuestions(questions: AppQuestion[]): AppQuestion[][] {
  const groups: AppQuestion[][] = [];
  for (const question of questions) {
    const last = groups[groups.length - 1];
    if (last && question.group_id && last[0].group_id === question.group_id) {
      last.push(question);
    } else {
      groups.push([question]);
    }
  }
  return groups;
}

const INPUTS_PER_SCREEN = 6;

/**
 * Groups gathered onto screens, so a yes/no question doesn't get a page to itself.
 *
 * Neighbouring groups come from the same part of the form, so they read as one short
 * page of related questions. The packing is done before any answers are given and
 * never changes, so answering something can't shuffle the screens underneath you.
 */
function toScreens(groups: AppQuestion[][]): AppQuestion[][][] {
  const screens: AppQuestion[][][] = [];
  for (const group of groups) {
    const last = screens[screens.length - 1];
    const filled = last?.reduce((n, g) => n + g.length, 0) ?? 0;
    if (last && filled + group.length <= INPUTS_PER_SCREEN) {
      last.push(group);
    } else {
      screens.push([group]);
    }
  }
  return screens;
}

/**
 * Whether a follow-up screen is worth showing, given what has been answered.
 *
 * The backend sends the "if yes, ..." parts of a form with an `ask_when` naming the
 * answer they depend on, e.g. `past_ihss.received_ihss_before == "Yes"`. An unmet
 * condition skips the screen; an unreadable one shows it, since an unasked question is
 * a blank box on a government form.
 */
function shouldAsk(
  group: AppQuestion[],
  answers: Answers,
  screen: AppQuestion[][]
): boolean {
  const condition = group[0]?.ask_when;
  if (!condition) return true;
  const match = /^\s*([\w.]+)\s*(==|!=)\s*(.+?)\s*$/.exec(condition);
  if (!match) return true;
  const [, path, op, rawExpected] = match;
  const answer = answers[path];
  if (answer === undefined || answer === null || answer === "") {
    // The question it hangs off is on this screen and still blank: wait for it rather
    // than show a follow-up above the thing that decides whether it applies.
    return !screen.some((g) => g.some((q) => q.field_id === path));
  }
  const expected = rawExpected.replace(/^['"]|['"]$/g, "").toLowerCase();
  const given = (Array.isArray(answer) ? answer : [answer]).map((v) =>
    String(v).toLowerCase()
  );
  const matches = given.includes(expected);
  return op === "==" ? matches : !matches;
}

export default function ApplicationsPage() {
  const [apps, setApps] = useState<ApplicationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [caseId, setCaseId] = useState<string | null>(null);

  // Flow state
  const [flowStep, setFlowStep] = useState<FlowStep>("list");
  const [activeProgram, setActiveProgram] = useState<string | null>(null);
  const [questions, setQuestions] = useState<AppQuestion[]>([]);
  const [answers, setAnswers] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [autofilled, setAutofilled] = useState(0);
  const [totalFields, setTotalFields] = useState(0);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);

  // Screens, not questions: the backend puts the inputs making up one thing a person
  // knows (an address, an employer) under a shared group_id, and a handful of those
  // groups share a screen.
  const screens = toScreens(groupQuestions(questions))
    .map((screen) => screen.filter((group) => shouldAsk(group, answers, screen)))
    .filter((screen) => screen.length > 0);
  const currentScreen = screens[stepIndex] ?? [];
  const currentQuestions = currentScreen.flat();

  useEffect(() => {
    const stored =
      typeof window !== "undefined"
        ? localStorage.getItem("ilera_case_id")
        : null;
    if (stored) {
      setCaseId(stored);
      listApplications(stored)
        .then((data) => setApps(data.applications))
        .catch(() => setApps([]))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  function handleStatusChange(program: string, newStatus: AppStatus) {
    if (!caseId) return;
    updateAppStatus(caseId, program, newStatus).then(() => {
      setApps((prev) =>
        prev.map((a) =>
          a.program === program ? { ...a, status: newStatus } : a
        )
      );
    });
  }

  function handleStartApplication(program: string) {
    if (!caseId) return;
    setActiveProgram(program);
    setFlowStep("loading");
    setAnswers({});
    setErrors({});
    setStepIndex(0);

    startApplication(caseId, program).then((result) => {
      setAutofilled(result.autofilled);
      setTotalFields(result.total_fields);
      setQuestions(result.questions);
      if (result.questions.length === 0) {
        handleGeneratePreview(program, {});
      } else {
        setFlowStep("questions");
      }
    });
  }

  function setAnswer(fieldId: string, value: AnswerValue) {
    setAnswers((prev) => ({ ...prev, [fieldId]: value }));
    setErrors((prev) => {
      if (!prev[fieldId]) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  }

  function goToNextQuestion() {
    if (currentQuestions.length === 0) return;
    const errs = validateQuestions(currentQuestions as Question[], answers);
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    if (stepIndex >= screens.length - 1) {
      if (activeProgram) handleGeneratePreview(activeProgram, answers);
      return;
    }
    setStepIndex((i) => i + 1);
  }

  function goToPrevQuestion() {
    setErrors({});
    setStepIndex((i) => Math.max(0, i - 1));
  }

  function handleGeneratePreview(
    program: string,
    finalAnswers: Answers
  ) {
    if (!caseId) return;
    setFlowStep("completing");
    previewApplication(caseId, program, finalAnswers).then((blob) => {
      const url = URL.createObjectURL(blob);
      setPdfUrl(url);
      setFlowStep("preview");
    });
  }

  function handleExportAndReturn() {
    if (!caseId || !activeProgram || !pdfUrl) return;

    const a = document.createElement("a");
    a.href = pdfUrl;
    a.download = `${activeProgram.toLowerCase().replace(/\s+/g, "_")}_${caseId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    completeApplication(caseId, activeProgram).then(() => {
      setApps((prev) =>
        prev.map((app) =>
          app.program === activeProgram
            ? { ...app, status: "completed" }
            : app
        )
      );
      setFlowStep("list");
      setActiveProgram(null);
      setPdfUrl(null);
    });
  }

  function handleBackToList() {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    setFlowStep("list");
    setActiveProgram(null);
    setPdfUrl(null);
  }

  // -----------------------------------------------------------------------
  // LOADING step
  // -----------------------------------------------------------------------
  if (flowStep === "loading") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
        <h2 className="text-lg font-semibold">
          Auto-filling forms for {activeProgram}&hellip;
        </h2>
        <p className="text-sm text-muted-foreground">
          Resolving your profile against form templates.
        </p>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Q&A step
  // -----------------------------------------------------------------------
  if (flowStep === "questions" && activeProgram) {
    const isLastQuestion = stepIndex >= screens.length - 1;
    const pct = ((stepIndex + 1) / screens.length) * 100;
    return (
      <div className="mx-auto w-full max-w-2xl space-y-6">
        <Button variant="ghost" size="sm" onClick={handleBackToList}>
          &larr; Back to applications
        </Button>

        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">
            {activeProgram}
          </h1>
          <p className="text-sm text-muted-foreground">
            Filled {autofilled} of {totalFields} fields automatically. We need a
            few more answers to complete your forms.
          </p>
        </div>

        <div className="space-y-2">
          <Progress value={pct} />
          <p className="text-xs text-muted-foreground">
            Step {stepIndex + 1} of {screens.length}
          </p>
        </div>

        <Card>
          <CardContent className="divide-y pt-6">
            {currentScreen.map((group, g) => {
              // Inputs of a group tend to repeat one explanation ("the Primary Contact
              // must be 18 or older") under every box. It is said once, above them.
              const shared = group[0]?.why_this_matters ?? "";
              return (
                <div
                  key={group[0].group_id || group[0].field_id}
                  className={`space-y-4 pb-5 ${g === 0 ? "" : "pt-5"}`}
                >
                  {group[0].group_prompt && (
                    <div className="space-y-1">
                      <p className="text-base font-semibold">
                        {group[0].group_prompt}
                      </p>
                      {shared && (
                        <p className="text-xs text-muted-foreground">{shared}</p>
                      )}
                    </div>
                  )}
                  {group.map((question, i) => (
                    <QuestionField
                      key={question.field_id}
                      question={
                        (question.why_this_matters === shared ||
                        question.why_this_matters ===
                          group[i - 1]?.why_this_matters
                          ? { ...question, why_this_matters: "" }
                          : question) as Question
                      }
                      value={answers[question.field_id] ?? null}
                      name=""
                      error={errors[question.field_id]}
                      onChange={(v) => setAnswer(question.field_id, v)}
                    />
                  ))}
                </div>
              );
            })}
          </CardContent>
        </Card>

        <div className="flex justify-between">
          <Button
            variant="outline"
            disabled={stepIndex === 0}
            onClick={goToPrevQuestion}
          >
            Back
          </Button>
          <Button onClick={goToNextQuestion}>
            {isLastQuestion ? "Generate preview" : "Next"}
          </Button>
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // COMPLETING step (generating PDF)
  // -----------------------------------------------------------------------
  if (flowStep === "completing") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
        <h2 className="text-lg font-semibold">
          Generating combined PDF for {activeProgram}&hellip;
        </h2>
        <p className="text-sm text-muted-foreground">
          Filling remaining fields and stitching forms together.
        </p>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // PREVIEW step (show stitched PDF)
  // -----------------------------------------------------------------------
  if (flowStep === "preview" && pdfUrl && activeProgram) {
    return (
      <div className="flex flex-1 flex-col gap-4">
        <Button variant="ghost" size="sm" onClick={handleBackToList}>
          &larr; Back to applications
        </Button>

        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">
            {activeProgram} &mdash; Preview
          </h1>
          <p className="text-sm text-muted-foreground">
            Review the completed forms below, then export.
          </p>
        </div>

        <div className="flex-1 overflow-hidden rounded-lg border border-border">
          <iframe
            src={`${pdfUrl}#navpanes=0`}
            className="h-[75vh] w-full"
            title="PDF Preview"
          />
        </div>

        <div className="flex justify-end pb-4">
          <Button onClick={handleExportAndReturn}>
            Export &amp; return to dashboard
          </Button>
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // LIST VIEW — eligibility-style cards
  // -----------------------------------------------------------------------
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">
          Your applications
        </h1>
        <p className="text-sm text-muted-foreground">
          Programs ranked by eligibility. Click to fill and download the
          required forms.
        </p>
      </div>

      {!caseId && !loading && (
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground">
              Complete the intake wizard and eligibility assessment first.
            </p>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="flex items-center gap-3 py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">
            Loading applications&hellip;
          </p>
        </div>
      )}

      {apps.length === 0 && !loading && caseId && (
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground">
              No eligible programs found yet. Complete the eligibility
              assessment to see available applications.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {apps.map((app) => {
          return (
            <Card key={app.program} className="gap-3">
              <CardHeader className="gap-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">{app.program}</CardTitle>
                  {app.eligibility_status && (
                    <Badge className={eligibilityColor[app.eligibility_status]}>
                      {app.eligibility_status.replace("_", " ")}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">{app.rationale}</p>
              </CardHeader>

              <CardContent className="space-y-2.5 text-xs">

                {app.roadblocks.length > 0 && (
                  <Detail label="Roadblocks" items={app.roadblocks} />
                )}
                {app.required_documents.length > 0 && (
                  <Detail
                    label="Required documents"
                    items={app.required_documents}
                  />
                )}
                {app.next_steps.length > 0 && (
                  <Detail label="Next steps" items={app.next_steps} />
                )}
                {app.sources.length > 0 && (
                  <p className="text-[11px] text-muted-foreground">
                    Sources: {app.sources.join(", ")}
                  </p>
                )}

                {/* Application controls */}
                <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
                  <div className="flex items-center gap-2">
                    <select
                      className="h-7 rounded-md border bg-transparent px-2 text-xs"
                      value={app.status}
                      onChange={(e) =>
                        handleStatusChange(
                          app.program,
                          e.target.value as AppStatus
                        )
                      }
                    >
                      {Object.entries(APP_STATUS_LABELS).map(([val, label]) => (
                        <option key={val} value={val}>
                          {label}
                        </option>
                      ))}
                    </select>
                    {app.has_forms && (
                      <span className="text-[11px] text-muted-foreground">
                        {app.form_ids.length} form
                        {app.form_ids.length !== 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                  {app.has_forms ? (
                    <Button
                      size="sm"
                      onClick={() => handleStartApplication(app.program)}
                    >
                      {app.status === "completed"
                        ? "Re-fill"
                        : app.status === "in_progress"
                          ? "Continue"
                          : "Fill forms"}
                    </Button>
                  ) : (
                    <span className="text-[11px] text-muted-foreground italic">
                      No forms mapped yet
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Detail({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="font-medium">{label}</p>
      <ul className="list-disc pl-5 text-muted-foreground">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}

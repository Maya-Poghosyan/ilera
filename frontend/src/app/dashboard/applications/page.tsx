"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  completeApplication,
  listApplications,
  previewApplication,
  startApplication,
  updateAppStatus,
} from "@/lib/api";
import type {
  AppQuestion,
  AppStatus,
  ApplicationEntry,
  EligibilityStatus,
} from "@/lib/types";

const eligibilityColor: Record<EligibilityStatus, string> = {
  likely: "border-transparent bg-primary text-primary-foreground",
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

export default function ApplicationsPage() {
  const [apps, setApps] = useState<ApplicationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [caseId, setCaseId] = useState<string | null>(null);

  // Flow state
  const [flowStep, setFlowStep] = useState<FlowStep>("list");
  const [activeProgram, setActiveProgram] = useState<string | null>(null);
  const [questions, setQuestions] = useState<AppQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [autofilled, setAutofilled] = useState(0);
  const [totalFields, setTotalFields] = useState(0);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [questionPage, setQuestionPage] = useState(0);

  const QUESTIONS_PER_PAGE = 6;

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
    setQuestionPage(0);

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

  function handleGeneratePreview(
    program: string,
    finalAnswers: Record<string, string>
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

  // --- Q&A pagination ---
  const pageQuestions = questions.slice(
    questionPage * QUESTIONS_PER_PAGE,
    (questionPage + 1) * QUESTIONS_PER_PAGE
  );
  const totalPages = Math.ceil(questions.length / QUESTIONS_PER_PAGE);
  const isLastPage = questionPage >= totalPages - 1;

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

        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Questions {questionPage * QUESTIONS_PER_PAGE + 1}&ndash;
              {Math.min(
                (questionPage + 1) * QUESTIONS_PER_PAGE,
                questions.length
              )}{" "}
              of {questions.length}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {pageQuestions.map((q) => (
              <div key={q.field} className="space-y-1.5">
                <Label>{q.label}</Label>
                <Input
                  value={answers[q.field] ?? ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({
                      ...prev,
                      [q.field]: e.target.value,
                    }))
                  }
                  placeholder={`Enter ${q.label.toLowerCase()}`}
                />
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="flex justify-between">
          <Button
            variant="outline"
            disabled={questionPage === 0}
            onClick={() => setQuestionPage((p) => p - 1)}
          >
            Previous
          </Button>
          {isLastPage ? (
            <Button
              onClick={() => handleGeneratePreview(activeProgram, answers)}
            >
              Generate preview
            </Button>
          ) : (
            <Button onClick={() => setQuestionPage((p) => p + 1)}>Next</Button>
          )}
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
            src={pdfUrl}
            className="h-[600px] w-full"
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
          const pct = Math.round(app.confidence * 100);
          return (
            <Card key={app.program} size="sm" className="gap-3">
              <CardHeader className="gap-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">{app.program}</CardTitle>
                  <div className="flex items-center gap-2">
                    {app.eligibility_status && (
                      <Badge className={eligibilityColor[app.eligibility_status]}>
                        {app.eligibility_status.replace("_", " ")}
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold tabular-nums text-muted-foreground">
                    {pct}%
                  </span>
                </div>
              </CardHeader>

              <CardContent className="space-y-2.5 text-xs">
                <p className="text-muted-foreground">{app.rationale}</p>

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

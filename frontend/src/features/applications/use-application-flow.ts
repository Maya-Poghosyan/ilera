"use client";

import { useEffect, useState } from "react";

import { completeApplication, listApplications, previewApplication, startApplication, updateAppStatus } from "@/features/applications/api";
import { visibleScreens } from "@/features/applications/screens";
import type { AppQuestion, AppStatus, ApplicationEntry } from "@/features/applications/types";
import { type Answers, type AnswerValue, type Question, validateQuestions } from "@/features/intake/schema";

/** Where the caregiver is; each step carries exactly what it needs. */
export type Flow =
  | { step: "list" }
  | { step: "loading"; program: string }
  | { step: "questions"; program: string; questions: AppQuestion[]; autofilled: number; totalFields: number }
  | { step: "completing"; program: string }
  | { step: "preview"; program: string; pdfUrl: string };

/** A case's applications, and filling one program's forms: start, answer, preview, export. */
export function useApplicationFlow(caseId: string | null) {
  const [apps, setApps] = useState<ApplicationEntry[]>([]);
  const [loading, setLoading] = useState(caseId !== null);
  const [flow, setFlow] = useState<Flow>({ step: "list" });
  const [failure, setFailure] = useState("");
  const [answers, setAnswers] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!caseId) return;
    listApplications(caseId)
      .then((data) => setApps(data.applications))
      .catch(() => setApps([]))
      .finally(() => setLoading(false));
  }, [caseId]);

  const screens = flow.step === "questions" ? visibleScreens(flow.questions, answers) : [];
  const currentScreen = screens[stepIndex] ?? [];
  const markStatus = (program: string, status: AppStatus) =>
    setApps((prev) => prev.map((a) => (a.program === program ? { ...a, status } : a)));
  const fail = (message: string) => {
    setFailure(message);
    setFlow({ step: "list" });
  };

  const preview = (program: string, finalAnswers: Answers) => {
    if (!caseId) return;
    setFlow({ step: "completing", program });
    previewApplication(caseId, program, finalAnswers)
      .then((blob) => setFlow({ step: "preview", program, pdfUrl: URL.createObjectURL(blob) }))
      .catch(() => fail(`Could not build the ${program} forms. Please try again.`));
  };

  const start = (program: string) => {
    if (!caseId) return;
    setFailure("");
    setAnswers({});
    setErrors({});
    setStepIndex(0);
    setFlow({ step: "loading", program });
    startApplication(caseId, program)
      .then((r) => r.questions.length === 0
        ? preview(program, {})
        : setFlow({ step: "questions", program, questions: r.questions, autofilled: r.autofilled, totalFields: r.total_fields }))
      .catch(() => fail(`Could not start the ${program} application. Please try again.`));
  };

  const answer = (fieldId: string, value: AnswerValue) => {
    setAnswers((prev) => ({ ...prev, [fieldId]: value }));
    setErrors((prev) => {
      if (!prev[fieldId]) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  };

  const next = () => {
    if (flow.step !== "questions" || currentScreen.length === 0) return;
    const errs = validateQuestions(currentScreen.flat() as Question[], answers);
    if (Object.keys(errs).length > 0) return setErrors(errs);
    if (stepIndex >= screens.length - 1) return preview(flow.program, answers);
    setStepIndex((i) => i + 1);
  };

  const back = () => {
    setErrors({});
    setStepIndex((i) => Math.max(0, i - 1));
  };

  const close = () => {
    if (flow.step === "preview") URL.revokeObjectURL(flow.pdfUrl);
    setFlow({ step: "list" });
  };

  const exportAndClose = () => {
    if (!caseId || flow.step !== "preview") return;
    const a = document.createElement("a");
    a.href = flow.pdfUrl;
    a.download = `${flow.program.toLowerCase().replace(/\s+/g, "_")}_${caseId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    const { program } = flow;
    completeApplication(caseId, program).then(() => {
      markStatus(program, "completed");
      close();
    });
  };

  const setStatus = (program: string, status: AppStatus) => {
    if (caseId) updateAppStatus(caseId, program, status).then(() => markStatus(program, status));
  };

  return { apps, loading, flow, failure, answers, errors, stepIndex, screens, currentScreen,
           start, answer, next, back, close, exportAndClose, setStatus };
}

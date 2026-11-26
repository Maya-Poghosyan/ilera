"use client";

import { useEffect, useRef, useState } from "react";
import { completeApplication, listApplications, previewApplication, saveApplicationProgress, startApplication, updateAppStatus } from "@/features/applications/api";
import { visibleScreens } from "@/features/applications/screens";
import type { AppQuestion, ApplicationEntry, ApprovalDetails, AppStatus } from "@/features/applications/types";
import { type Answers, type AnswerValue, type Question, validateQuestions } from "@/features/intake/schema";

type Flow =
  | { step: "list" }
  | { step: "loading" | "documents" | "follow_up" | "status"; program: string }
  | { step: "questions"; program: string; questions: AppQuestion[] }
  | { step: "preview"; program: string; pdfUrl: string };

type Progress = Parameters<typeof saveApplicationProgress>[2];

export function useApplicationFlow(caseId: string | null) {
  const [apps, setApps] = useState<ApplicationEntry[]>([]);
  const [loadedCase, setLoadedCase] = useState<string | null>(null);
  const [flow, setFlow] = useState<Flow>({ step: "list" });
  const [failure, setFailure] = useState("");
  const [answers, setAnswers] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [stepIndex, setStepIndex] = useState(0);
  const [checked, setChecked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);

  useEffect(() => {
    if (!caseId) return;
    let active = true;
    listApplications(caseId)
      .then((data) => { if (active) setApps(data.applications); })
      .catch(() => { if (active) setFailure("Could not load applications. Refresh to try again."); })
      .finally(() => { if (active) setLoadedCase(caseId); });
    return () => { active = false; };
  }, [caseId]);

  const activeApp = flow.step === "list" ? undefined : apps.find((app) => app.program === flow.program);
  const pdfUrl = flow.step === "preview" ? flow.pdfUrl : null;
  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  const screens = flow.step === "questions" ? visibleScreens(flow.questions, answers) : [];
  const currentScreen = screens[stepIndex] ?? [];

  async function run(action: () => Promise<void>, message: string) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setFailure("");
    try {
      await action();
    } catch {
      setFailure(message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function save(program: string, progress: Progress) {
    if (!caseId) return;
    const saved = await saveApplicationProgress(caseId, program, progress);
    setApps((prev) => prev.map((app) => app.program === program ? {
      ...app,
      ...saved,
      ready_documents: progress.ready_documents ?? app.ready_documents,
      completed_follow_ups: progress.completed_follow_ups ?? app.completed_follow_ups,
    } : app));
  }

  async function showPreview(program: string) {
    if (!caseId) return;
    const blob = await previewApplication(caseId, program, {});
    setFlow({ step: "preview", program, pdfUrl: URL.createObjectURL(blob) });
  }

  function start(program: string) {
    const app = apps.find((item) => item.program === program);
    if (!caseId || !app) return;
    setAnswers({});
    setErrors({});
    setStepIndex(0);
    void run(async () => {
      if (["pending_determination", "accepted", "archived"].includes(app.status)) {
        setFlow({ step: "status", program });
      } else if (!app.has_forms || app.stage === "follow_up" || app.status === "completed") {
        setChecked(app.completed_follow_ups);
        setFlow({ step: "follow_up", program });
      } else if (app.stage === "review_forms") {
        await showPreview(program);
      } else if (app.stage === "gather_documents") {
        setChecked(app.ready_documents);
        setFlow({ step: "documents", program });
      } else {
        setFlow({ step: "loading", program });
        try {
          const result = await startApplication(caseId, program);
          if (result.error) throw new Error(result.error);
          if (result.questions.length) {
            setFlow({ step: "questions", program, questions: result.questions });
          } else {
            await save(program, { stage: "gather_documents" });
            setChecked(app.ready_documents);
            setFlow({ step: "documents", program });
          }
        } catch (error) {
          setFlow({ step: "list" });
          throw error;
        }
      }
    }, `Could not open the ${program} application. Please try again.`);
  }

  function answer(fieldId: string, value: AnswerValue) {
    setAnswers((prev) => ({ ...prev, [fieldId]: value }));
    setErrors((prev) => {
      if (!prev[fieldId]) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  }

  function next() {
    if (flow.step !== "questions") return;
    const invalid = validateQuestions(currentScreen.flat() as Question[], answers);
    if (Object.keys(invalid).length) return setErrors(invalid);
    if (stepIndex < screens.length - 1) return setStepIndex((index) => index + 1);
    const { program } = flow;
    const visibleAnswers = Object.fromEntries(screens.flat(2).filter((question) => question.field_id in answers)
      .map((question) => [question.field_id, answers[question.field_id]]));
    void run(async () => {
      await save(program, { stage: "gather_documents", answers: visibleAnswers });
      setChecked(activeApp?.ready_documents ?? []);
      setFlow({ step: "documents", program });
    }, "Could not save your answers. Please try again.");
  }

  function reviewForms() {
    if (!activeApp) return;
    const { program } = activeApp;
    void run(async () => {
      await save(program, { stage: "review_forms", ready_documents: checked });
      await showPreview(program);
    }, "Could not prepare your forms. Please try again.");
  }

  function download() {
    if (flow.step !== "preview") return;
    const link = document.createElement("a");
    link.href = flow.pdfUrl;
    link.download = `${flow.program.toLowerCase().replace(/\s+/g, "_")}.pdf`;
    link.click();
  }

  function followUp() {
    if (!activeApp) return;
    const { program, completed_follow_ups } = activeApp;
    void run(async () => {
      await save(program, { stage: "follow_up" });
      setChecked(completed_follow_ups);
      setFlow({ step: "follow_up", program });
    }, "Could not save your progress. Please try again.");
  }

  function saveFollowUps(complete = false) {
    if (!caseId || !activeApp) return;
    const { program } = activeApp;
    void run(async () => {
      await save(program, { stage: "follow_up", completed_follow_ups: checked });
      if (complete) {
        const saved = await completeApplication(caseId, program);
        setApps((prev) => prev.map((app) => app.program === program ? { ...app, status: saved.status } : app));
      }
      setFlow({ step: "list" });
    }, "Could not save your follow-up steps. Please try again.");
  }

  function updateStatus(status: AppStatus | "restore", approval?: ApprovalDetails) {
    if (!caseId || !activeApp) return;
    const { program } = activeApp;
    void run(async () => {
      const saved = await updateAppStatus(caseId, program, status, approval);
      setApps((prev) => prev.map((app) => app.program === program ? { ...app, ...saved } : app));
      setFlow({ step: "list" });
    }, "Could not update the application status. Please try again.");
  }

  return {
    apps, loading: Boolean(caseId && loadedCase !== caseId), activeApp, flow, failure, busy,
    answers, errors, stepIndex, screens, currentScreen, checked, setChecked,
    start, answer, next, reviewForms, download, followUp, saveFollowUps, updateStatus,
    openStatus: () => {
      if (activeApp) {
        setFailure("");
        setFlow({ step: "status", program: activeApp.program });
      }
    },
    reopenPreview: () => { if (activeApp) void run(() => showPreview(activeApp.program), "Could not open your forms. Please try again."); },
    back: () => { setErrors({}); setStepIndex((index) => Math.max(0, index - 1)); },
    close: () => { setFailure(""); setFlow({ step: "list" }); },
  };
}

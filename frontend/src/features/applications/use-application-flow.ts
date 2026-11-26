"use client";

import { useEffect, useRef, useState } from "react";
import { completeApplication, listApplications, previewApplication, readApplicationDocument, saveApplicationProgress, startApplication, updateAppStatus } from "@/features/applications/api";
import { visibleScreens } from "@/features/applications/screens";
import type { AppQuestion, ApplicationEntry, ApplicationStep, ApprovalDetails, AppStatus } from "@/features/applications/types";
import { applicationSteps } from "@/features/applications/types";
import { type Answers, type AnswerValue, type Question, validateQuestions } from "@/features/intake/schema";

type Flow =
  | { step: "list" }
  | { step: "loading" | "documents" | "follow_up" | "status"; program: string }
  | { step: "questions"; program: string; questions: AppQuestion[] }
  | { step: "preview"; program: string; pdfUrl: string };

type Progress = Parameters<typeof saveApplicationProgress>[2];

/** A document read to fill in answers. Kept in memory only. */
export type AppDocument = { id: string; name: string } & (
  | { status: "reading" }
  | { status: "read"; filled: number; kept: number }
  | { status: "failed"; message: string }
);

const PROFILE_SOURCE = "your profile";
const isBlank = (value: AnswerValue | undefined) => value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);

const FLOW_STEPS: Record<Exclude<Flow["step"], "list" | "loading">, ApplicationStep> = {
  questions: "update_information",
  documents: "gather_documents",
  preview: "review_forms",
  follow_up: "follow_up",
  status: "update_status",
};

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
  // Where a prefilled answer came from, until the caregiver changes it.
  const [filledFrom, setFilledFrom] = useState<Record<string, string>>({});
  const [documents, setDocuments] = useState<AppDocument[]>([]);
  // Step 1 opens on its autofill page, before the question pages.
  const [onAutofill, setOnAutofill] = useState(true);
  const pending = useRef(false);
  const answersRef = useRef(answers);
  useEffect(() => { answersRef.current = answers; }, [answers]);

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

  /** Loads the form questions, with any saved answers filled in. */
  async function openQuestions(app: ApplicationEntry) {
    if (!caseId) return;
    const { program } = app;
    setFlow({ step: "loading", program });
    try {
      const result = await startApplication(caseId, program);
      if (result.error) throw new Error(result.error);
      if (result.questions.length) {
        const known = result.profile_answers ?? {};
        setAnswers({ ...known, ...result.answers });
        setFilledFrom(Object.fromEntries(Object.keys(known).map((id) => [id, PROFILE_SOURCE])));
        setDocuments([]);
        setOnAutofill(true);
        setErrors({});
        setStepIndex(0);
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

  function start(program: string) {
    const app = apps.find((item) => item.program === program);
    if (!caseId || !app) return;
    setAnswers({});
    setErrors({});
    setStepIndex(0);
    void run(async () => {
      if (["pending_determination", "accepted", "denied", "archived"].includes(app.status)) {
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
        await openQuestions(app);
      }
    }, `Could not open the ${program} application. Please try again.`);
  }

  function answer(fieldId: string, value: AnswerValue) {
    setAnswers((prev) => ({ ...prev, [fieldId]: value }));
    setFilledFrom((prev) => {
      if (!(fieldId in prev)) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
    setErrors((prev) => {
      if (!prev[fieldId]) return prev;
      const next = { ...prev };
      delete next[fieldId];
      return next;
    });
  }

  /** Answers on the screens currently shown, ready to save. */
  function visibleAnswers() {
    return Object.fromEntries(screens.flat(2).filter((question) => question.field_id in answers)
      .map((question) => [question.field_id, answers[question.field_id]]));
  }

  function next() {
    if (flow.step !== "questions") return;
    const invalid = validateQuestions(currentScreen.flat() as Question[], answers);
    if (Object.keys(invalid).length) return setErrors(invalid);
    if (stepIndex >= screens.length - 1) return finishQuestions();
    // Each page is saved as it is finished, so leaving partway keeps what was entered.
    const { program } = flow;
    void run(async () => {
      await save(program, { stage: "update_information", answers: visibleAnswers() });
      setStepIndex((index) => index + 1);
    }, "Could not save your answers. Please try again.");
  }

  /** Reads documents and fills the blank answers they give; answers already given are kept. */
  function addDocuments(files: File[]) {
    if (!caseId || flow.step !== "questions") return;
    const { program } = flow;
    for (const file of files) {
      const id = crypto.randomUUID();
      setDocuments((prev) => [...prev, { id, name: file.name, status: "reading" }]);
      void readApplicationDocument(caseId, program, file).then((result) => {
        if (!result.ok) {
          setDocuments((prev) => prev.map((d) => d.id === id ? { id, name: d.name, status: "failed", message: result.message } : d));
          return;
        }
        const current = answersRef.current;
        const entries = Object.entries(result.answers);
        const blank = entries.filter(([field]) => isBlank(current[field]));
        const kept = entries.filter(([field, value]) => !isBlank(current[field]) && JSON.stringify(current[field]) !== JSON.stringify(value)).length;
        setAnswers((prev) => ({ ...prev, ...Object.fromEntries(blank.filter(([field]) => isBlank(prev[field]))) }));
        setFilledFrom((prev) => ({ ...prev, ...Object.fromEntries(blank.map(([field]) => [field, `${file.name}, page ${result.pages[field] ?? 1}`])) }));
        setErrors((prev) => Object.fromEntries(Object.entries(prev).filter(([field]) => !blank.some(([f]) => f === field))));
        setDocuments((prev) => prev.map((d) => d.id === id ? { id, name: d.name, status: "read", filled: blank.length, kept } : d));
      });
    }
  }

  /** Saves the answers and moves to documents, or shows the first screen with a missing answer. */
  function finishQuestions() {
    if (flow.step !== "questions") return;
    for (const [index, screen] of screens.entries()) {
      const invalid = validateQuestions(screen.flat() as Question[], answers);
      if (Object.keys(invalid).length) {
        setStepIndex(index);
        return setErrors(invalid);
      }
    }
    const { program } = flow;
    const toSave = visibleAnswers();
    void run(async () => {
      await save(program, { stage: "gather_documents", answers: toSave });
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

  function updateStatus(status: AppStatus | "restore", approval?: ApprovalDetails, onSaved?: (app: ApplicationEntry) => void) {
    if (!caseId || !activeApp) return;
    const { program } = activeApp;
    void run(async () => {
      const saved = await updateAppStatus(caseId, program, status, approval);
      const updated: ApplicationEntry = {
        ...activeApp, ...saved,
        determination: saved.status === "accepted" ? "approved" : saved.status === "denied" ? "denied" : activeApp.determination,
      };
      setApps((prev) => prev.map((app) => app.program === program ? updated : app));
      onSaved?.(updated);
      setFlow({ step: "list" });
    }, "Could not update the application status. Please try again.");
  }

  const steps = applicationSteps(!!activeApp?.has_forms);
  const step = flow.step === "list" || flow.step === "loading" ? null : FLOW_STEPS[flow.step];
  const stepAt = step ? steps.indexOf(step) : -1;
  const previousStep = stepAt > 0 ? steps[stepAt - 1] : null;
  const nextStep = stepAt >= 0 && stepAt < steps.length - 1 ? steps[stepAt + 1] : null;

  /** Moving forward saves the step like its own continue button; moving back keeps the saved stage. */
  function goToNextStep() {
    if (!activeApp) return;
    if (flow.step === "questions") return finishQuestions();
    if (flow.step === "documents") return reviewForms();
    if (flow.step === "preview") return followUp();
    if (flow.step === "follow_up") {
      const { program, stage, completed_follow_ups } = activeApp;
      void run(async () => {
        if (checked.join() !== completed_follow_ups.join()) await save(program, { stage, completed_follow_ups: checked });
        setFlow({ step: "status", program });
      }, "Could not save your follow-up steps. Please try again.");
    }
  }

  function goToPreviousStep() {
    if (!activeApp || !previousStep) return;
    const { program, stage } = activeApp;
    void run(async () => {
      // Checklist ticks are kept when leaving a step backwards.
      if (flow.step === "documents" && checked.join() !== activeApp.ready_documents.join()) {
        await save(program, { stage, ready_documents: checked });
      }
      if (flow.step === "follow_up" && checked.join() !== activeApp.completed_follow_ups.join()) {
        await save(program, { stage, completed_follow_ups: checked });
      }
      if (previousStep === "update_information") await openQuestions(activeApp);
      else if (previousStep === "gather_documents") {
        setChecked(activeApp.ready_documents);
        setFlow({ step: "documents", program });
      } else if (previousStep === "review_forms") await showPreview(program);
      else if (previousStep === "follow_up") {
        setChecked(activeApp.completed_follow_ups);
        setFlow({ step: "follow_up", program });
      }
    }, "Could not open the previous step. Please try again.");
  }

  return {
    apps, loading: Boolean(caseId && loadedCase !== caseId), activeApp, flow, failure, busy,
    answers, errors, stepIndex, screens, currentScreen, checked, setChecked,
    filledFrom, documents, addDocuments, removeDocument: (id: string) => setDocuments((prev) => prev.filter((d) => d.id !== id)),
    start, answer, next, reviewForms, download, followUp, saveFollowUps, updateStatus,
    previousStep, nextStep, goToPreviousStep, goToNextStep,
    reopenPreview: () => { if (activeApp) void run(() => showPreview(activeApp.program), "Could not open your forms. Please try again."); },
    onAutofill,
    toQuestions: () => setOnAutofill(false),
    back: () => {
      setErrors({});
      if (stepIndex === 0) setOnAutofill(true);
      else setStepIndex((index) => index - 1);
    },
    close: () => { setFailure(""); setFlow({ step: "list" }); },
  };
}

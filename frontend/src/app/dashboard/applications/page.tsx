"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useCaseId } from "@/features/accounts/auth-context";
import { APPLICATION_GROUPS, ApplicationList, EMPTY_GROUP_MESSAGES, applicationGroup, type ApplicationGroup } from "@/features/applications/components/application-list";
import { ApprovalForm } from "@/features/applications/components/approval-form";
import { QuestionScreen } from "@/features/applications/components/question-screen";
import { APP_STATUS_LABELS, STEP_LABELS, type ApplicationStep, type ApprovalDetails, type AppStatus } from "@/features/applications/types";
import { useApplicationFlow } from "@/features/applications/use-application-flow";

function StepArrow({ direction, step, disabled, onClick }: {
  direction: "previous" | "next";
  step: ApplicationStep | null;
  disabled: boolean;
  onClick: () => void;
}) {
  if (!step) return null;
  // Pinned to the screen's vertical middle, over the grid column kept free for it beside the sidebar (w-60 + p-8).
  const Icon = direction === "previous" ? ChevronLeft : ChevronRight;
  return (
    <button type="button" disabled={disabled} onClick={onClick}
      aria-label={`${direction === "previous" ? "Previous" : "Next"} step: ${STEP_LABELS[step]}`}
      className={`group fixed top-1/2 z-10 flex w-32 -translate-y-1/2 flex-col ${direction === "previous" ? "left-[17rem]" : "right-8"} items-center gap-2 rounded-lg p-2 text-center text-sm text-muted-foreground transition-colors hover:text-primary disabled:opacity-50`}>
      <span className="flex size-12 items-center justify-center rounded-full border border-border bg-card transition-colors group-hover:border-primary">
        <Icon aria-hidden="true" className="size-6" />
      </span>
      <span className="text-xs uppercase tracking-wide">{direction === "previous" ? "Previous" : "Next"}</span>
      <span className="font-medium text-foreground group-hover:text-primary">{STEP_LABELS[step]}</span>
    </button>
  );
}

/** One application step, with the way back to the list and arrows to the neighbouring steps. */
function StepLayout({ flow, program, step, children }: {
  flow: ReturnType<typeof useApplicationFlow>;
  program: string;
  step: ApplicationStep;
  children: ReactNode;
}) {
  return (
    <div className="space-y-6">
      <Button variant="ghost" size="lg" className="-ml-3 text-base" disabled={flow.busy} onClick={flow.close}>
        <ArrowLeft aria-hidden="true" className="size-5" /> Back to applications
      </Button>
      <div className="grid grid-cols-[8rem_minmax(0,1fr)_8rem] gap-6">
        <div><StepArrow direction="previous" step={flow.previousStep} disabled={flow.busy} onClick={flow.goToPreviousStep} /></div>
        <div className="mx-auto w-full max-w-4xl space-y-6">
          <header className="space-y-2">
            <h1 className="page-title">{program}</h1>
            <h2 className="text-2xl">{STEP_LABELS[step]}</h2>
          </header>
          {children}
        </div>
        <div><StepArrow direction="next" step={flow.nextStep} disabled={flow.busy} onClick={flow.goToNextStep} /></div>
      </div>
    </div>
  );
}

export default function ApplicationsPage() {
  const caseId = useCaseId();
  const [expanded, setExpanded] = useState<Set<ApplicationGroup>>(() => new Set(["likely"]));
  const f = useApplicationFlow(caseId);
  const toggle = (group: ApplicationGroup, open: boolean) => setExpanded((prev) => {
    const next = new Set(prev);
    if (open) next.add(group); else next.delete(group);
    return next;
  });
  // Expands the section an updated application lands in, so it stays in view.
  const updateStatus = (status: AppStatus | "restore", details?: ApprovalDetails) =>
    f.updateStatus(status, details, (app) => toggle(applicationGroup(app), true));
  const [showApproval, setShowApproval] = useState(false);
  const { flow, activeApp } = f;
  const error = f.failure && <p role="alert" className="text-destructive">{f.failure}</p>;

  if (flow.step === "loading") {
    return <p role="status" className="py-8">Preparing your {flow.program} application…</p>;
  }

  if (flow.step === "status" && activeApp && showApproval && !activeApp.renewal_record_id) {
    return (
      <ApprovalForm program={activeApp.program} busy={f.busy} error={f.failure}
        onSave={(details) => updateStatus("accepted", details)} onCancel={() => setShowApproval(false)} />
    );
  }

  if (flow.step === "status" && activeApp) {
    const status = activeApp.status;
    return (
      <StepLayout flow={f} program={flow.program} step="update_status">
        {error}
        <Card>
          <CardContent className="space-y-4">
            <p>Current status <strong className="ml-2">{APP_STATUS_LABELS[status]}</strong></p>
            <div className="flex flex-wrap gap-2">
              {status === "accepted" && (activeApp.renewal_record_id
                ? <Link className={buttonVariants({ variant: "outline" })} href="/dashboard/records#renewals">View records</Link>
                : <Button disabled={f.busy} onClick={() => setShowApproval(true)}>Add to Records &amp; Renewal</Button>)}
              {status === "archived" ? (
                <Button disabled={f.busy} onClick={() => updateStatus("restore")}>Restore application</Button>
              ) : (
                <>
                  {status === "pending_determination" && (
                    <>
                      <Button disabled={f.busy} onClick={() => setShowApproval(true)}>Mark approved</Button>
                      <Button variant="outline" disabled={f.busy} onClick={() => updateStatus("denied")}>Mark denied</Button>
                      <Button variant="outline" disabled={f.busy} onClick={() => updateStatus("in_progress")}>Move back to in progress</Button>
                    </>
                  )}
                  {status !== "pending_determination" && status !== "accepted" && status !== "denied" && (
                    <Button disabled={f.busy} onClick={() => updateStatus("pending_determination")}>Mark pending determination</Button>
                  )}
                  {status !== "accepted" && status !== "denied" && <Button variant="outline" disabled={f.busy} onClick={() => updateStatus("archived")}>Archive application</Button>}
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </StepLayout>
    );
  }

  if (flow.step !== "list" && activeApp) {
    const stage = flow.step === "questions" ? "update_information"
      : flow.step === "documents" ? "gather_documents"
      : flow.step === "preview" ? "review_forms" : "follow_up";
    const checklist = flow.step === "documents" ? activeApp.required_documents : activeApp.next_steps;
    const items = [...new Set(checklist)];

    return (
      <StepLayout flow={f} program={flow.program} step={stage}>
        {error}
        {flow.step === "questions" && (
          <>
            <Progress value={((f.stepIndex + 1) / f.screens.length) * 100} />
            <p className="text-sm text-muted-foreground">Questions {f.stepIndex + 1} of {f.screens.length}</p>
            <Card>
              <CardContent className="divide-y pt-6">
                <QuestionScreen screen={f.currentScreen} answers={f.answers} errors={f.errors} onAnswer={f.answer} />
              </CardContent>
            </Card>
            <div className="flex justify-between gap-2">
              <Button variant="outline" disabled={f.busy || f.stepIndex === 0} onClick={f.back}>Back</Button>
              <Button disabled={f.busy} onClick={f.next}>{f.stepIndex >= f.screens.length - 1 ? "Continue to documents" : "Next"}</Button>
            </div>
          </>
        )}
        {(flow.step === "documents" || flow.step === "follow_up") && (
          <>
            {items.length ? (
              <ul className="divide-y rounded-lg border bg-card">
                {items.map((item) => (
                  <li key={item}>
                    <label className="flex cursor-pointer items-start gap-3 p-4">
                      <input
                        type="checkbox"
                        className="mt-1 size-4 shrink-0 accent-primary"
                        checked={f.checked.includes(item)}
                        disabled={f.busy}
                        onChange={(event) => {
                          const selected = event.target.checked;
                          f.setChecked((prev) => selected ? [...prev, item] : prev.filter((value) => value !== item));
                        }}
                      />
                      {item}
                    </label>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">
                {flow.step === "documents" ? "There are no supporting documents on your checklist." : "There are no follow-up steps on your checklist."}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {flow.step === "documents" ? (
                <Button disabled={f.busy} onClick={f.reviewForms}>{f.busy ? "Preparing forms…" : "Continue to form review"}</Button>
              ) : (
                <>
                  {activeApp.has_forms && <Button variant="outline" disabled={f.busy} onClick={f.reopenPreview}>View forms</Button>}
                  <Button variant="outline" disabled={f.busy} onClick={() => f.saveFollowUps()}>Save progress</Button>
                  {activeApp.status !== "completed" && <Button disabled={f.busy || items.some((item) => !f.checked.includes(item))} onClick={() => f.saveFollowUps(true)}>Mark as complete</Button>}
                </>
              )}
            </div>
          </>
        )}
        {flow.step === "preview" && (
          <>
            <iframe src={`${flow.pdfUrl}#navpanes=0`} className="h-[75vh] w-full rounded-lg border" title="Filled application forms" />
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={f.download}>Download forms</Button>
              <Button disabled={f.busy} onClick={f.followUp}>Continue to follow-up steps</Button>
            </div>
          </>
        )}
      </StepLayout>
    );
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="page-title">Program Applications</h1>
        <p className="text-muted-foreground">Caregiver assistance programs you may be eligible for, ranked by match strength</p>
      </header>
      {error}
      {f.loading ? (
        <p role="status">Loading applications…</p>
      ) : (
        !f.apps.length && !f.failure && <p className="text-muted-foreground">
          {caseId ? "There are no new program applications to show." : "Complete intake and eligibility to see program applications."}
        </p>
      )}
      {f.apps.length > 0 && (Object.keys(APPLICATION_GROUPS) as ApplicationGroup[]).map((group) => {
        const apps = f.apps.filter((app) => applicationGroup(app) === group);
        const open = expanded.has(group);
        return (
          <section key={group} className="space-y-4">
            <h2>
              <button type="button" aria-expanded={open} aria-controls={`applications-${group}`} onClick={() => toggle(group, !open)}
                className="flex w-full items-center gap-2 border-b pb-2 text-left text-xl text-primary">
                <ChevronDown aria-hidden="true" className={`size-5 transition-transform ${open ? "" : "-rotate-90"}`} />
                {APPLICATION_GROUPS[group]}
                <span className="text-base text-muted-foreground">({apps.length})</span>
              </button>
            </h2>
            {open && (
              <div id={`applications-${group}`}>
                {apps.length
                  ? <ApplicationList apps={apps} onStart={(program) => { setShowApproval(false); f.start(program); }} />
                  : <p className="text-muted-foreground">{EMPTY_GROUP_MESSAGES[group]}</p>}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

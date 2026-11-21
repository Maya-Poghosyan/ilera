"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useCaseId } from "@/features/accounts/auth-context";
import { ApplicationList } from "@/features/applications/components/application-list";
import { QuestionScreen } from "@/features/applications/components/question-screen";
import { useApplicationFlow } from "@/features/applications/use-application-flow";

function Working({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-20">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-primary" />
      <h2 className="text-lg">{title}</h2>
      <p className="text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

export default function ApplicationsPage() {
  const caseId = useCaseId();
  const f = useApplicationFlow(caseId);
  const { flow } = f;

  if (flow.step === "loading") {
    return <Working title={`Auto-filling forms for ${flow.program}…`} detail="Resolving your profile against form templates." />;
  }
  if (flow.step === "completing") {
    return <Working title={`Generating combined PDF for ${flow.program}…`} detail="Filling remaining fields and stitching forms together." />;
  }

  if (flow.step === "questions") {
    const last = f.stepIndex >= f.screens.length - 1;
    return (
      <div className="mx-auto w-full max-w-2xl space-y-6">
        <Button variant="ghost" size="sm" onClick={f.close}>&larr; Back to applications</Button>
        <div className="space-y-1">
          <h1 className="text-2xl">{flow.program}</h1>
          <p className="text-sm text-muted-foreground">
            Filled {flow.autofilled} of {flow.totalFields} fields automatically. We need a few more answers to complete your forms.
          </p>
        </div>
        <div className="space-y-2">
          <Progress value={((f.stepIndex + 1) / f.screens.length) * 100} />
          <p className="text-xs text-muted-foreground">Step {f.stepIndex + 1} of {f.screens.length}</p>
        </div>
        <Card>
          <CardContent className="divide-y pt-6">
            <QuestionScreen screen={f.currentScreen} answers={f.answers} errors={f.errors} onAnswer={f.answer} />
          </CardContent>
        </Card>
        <div className="flex justify-between">
          <Button variant="outline" disabled={f.stepIndex === 0} onClick={f.back}>Back</Button>
          <Button onClick={f.next}>{last ? "Generate preview" : "Next"}</Button>
        </div>
      </div>
    );
  }

  if (flow.step === "preview") {
    return (
      <div className="flex flex-1 flex-col gap-4">
        <Button variant="ghost" size="sm" onClick={f.close}>&larr; Back to applications</Button>
        <div className="space-y-1">
          <h1 className="text-2xl">{flow.program} &mdash; Preview</h1>
          <p className="text-sm text-muted-foreground">Review the completed forms below, then export.</p>
        </div>
        <div className="flex-1 overflow-hidden rounded-lg border border-border">
          <iframe src={`${flow.pdfUrl}#navpanes=0`} className="h-[75vh] w-full" title="PDF Preview" />
        </div>
        <div className="flex justify-end pb-4">
          <Button onClick={f.exportAndClose}>Export &amp; return to dashboard</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl">Your applications</h1>
        <p className="text-sm text-muted-foreground">Programs ranked by eligibility. Click to fill and download the required forms.</p>
      </div>
      {f.failure && <p role="alert" className="text-sm text-destructive">{f.failure}</p>}
      {!caseId && !f.loading && (
        <Card><CardContent className="py-6"><p className="text-sm text-muted-foreground">Complete the intake wizard and eligibility assessment first.</p></CardContent></Card>
      )}
      {f.loading && (
        <div className="flex items-center gap-3 py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading applications&hellip;</p>
        </div>
      )}
      {f.apps.length === 0 && !f.loading && caseId && (
        <Card><CardContent className="py-6"><p className="text-sm text-muted-foreground">No eligible programs found yet. Complete the eligibility assessment to see available applications.</p></CardContent></Card>
      )}
      <ApplicationList apps={f.apps} onStatus={f.setStatus} onStart={f.start} />
    </div>
  );
}

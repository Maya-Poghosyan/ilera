import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { intakeIssues } from "@/features/intake/flow";
import { interpolateName } from "@/features/intake/schema";

type Issue = ReturnType<typeof intakeIssues>[number];

/** Unanswered required questions by section, each linking back to its page; submit once none remain. */
export function ReviewScreen({ issues, name, submitting, submitLabel, saveMessage, onJump, onBack, onSubmit }: {
  issues: Issue[];
  name: string;
  submitting: boolean;
  submitLabel: string;
  saveMessage: string | null;
  onJump: (fieldId: string) => void;
  onBack: () => void;
  onSubmit: () => void;
}) {
  const sections = [...new Set(issues.map((issue) => issue.section))];
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-14">
      <h1 id="intake-review-title" tabIndex={-1} className="text-2xl">{issues.length ? "Complete your answers" : "Ready to submit"}</h1>
      {sections.map((section) => (
        <Card key={section}>
          <CardHeader><CardTitle>{interpolateName(section, name)}</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-4">
              {issues.filter((issue) => issue.section === section).map((issue) => (
                <li key={issue.question.field_id}>
                  <a href={`#intake-${issue.question.field_id}`} className="text-primary underline underline-offset-4"
                     onClick={(event) => { event.preventDefault(); onJump(issue.question.field_id); }}>
                    {interpolateName(issue.question.text, name)}
                  </a>
                  <p className="mt-1 text-sm text-destructive">{issue.message}</p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
      <div className="flex justify-between gap-4">
        <Button variant="outline" disabled={submitting} onClick={onBack}>Back to intake</Button>
        <Button disabled={submitting || issues.length > 0} onClick={onSubmit}>{submitting ? "Submitting…" : submitLabel}</Button>
      </div>
      {saveMessage && <p role="status" className="text-sm text-muted-foreground">{saveMessage}</p>}
    </main>
  );
}

import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ApprovalDetails } from "@/features/applications/types";

export function ApprovalForm({ program, busy, error, onSave, onCancel }: {
  program: string;
  busy: boolean;
  error: string;
  onSave: (details: ApprovalDetails) => void;
  onCancel: () => void;
}) {
  const leave = program === "Paid Family Leave";
  const tax = program === "Caregiver Tax Relief";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const read = (name: string) => String(data.get(name) ?? "") || undefined;
    const year = read("tax_year");
    onSave({
      approval_date: read("approval_date"),
      effective_date: read("effective_date"),
      due_date: read("due_date"),
      benefit_end_date: read("benefit_end_date"),
      tax_year: year ? Number(year) : undefined,
    });
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <header className="space-y-2">
        <h1 className="page-title">{program}</h1>
        <h2 className="text-2xl">Record approval</h2>
        <p className="text-muted-foreground">Add this program to Records &amp; Renewal. You can leave dates blank if you don’t know them.</p>
      </header>
      <Card>
        <CardContent>
          <form onSubmit={submit} className="space-y-5">
            {error && <p role="alert" className="text-destructive">{error}</p>}
            <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1"><span>Approval date (optional)</span><Input name="approval_date" type="date" /></label>
              {!tax && <label className="space-y-1"><span>{leave ? "Approved leave start" : "Effective date"} (optional)</span><Input name="effective_date" type="date" /></label>}
              {leave ? (
                <label className="space-y-1"><span>Approved leave end (optional)</span><Input name="benefit_end_date" type="date" /></label>
              ) : tax ? (
                <label className="space-y-1"><span>Tax year (optional)</span><Input name="tax_year" type="number" min={1900} max={2100} /></label>
              ) : (
                <label className="space-y-1"><span>Next renewal or review deadline (optional)</span><Input name="due_date" type="date" /></label>
              )}
            </fieldset>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} type="submit">Save approval</Button>
              <Button disabled={busy} type="button" variant="outline" onClick={onCancel}>Cancel</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

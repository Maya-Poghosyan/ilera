"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { submitIntake } from "@/lib/api";
import type { CaseProfile, Insurance } from "@/lib/types";

type Form = {
  age: string;
  state: string;
  insurance: Insurance;
  veteran: boolean;
  care_needs: string;
  relationship: string;
  employment_status: string;
  household_size: string;
  income_monthly: string;
  goals: string;
};

const empty: Form = {
  age: "",
  state: "CA",
  insurance: "unknown",
  veteran: false,
  care_needs: "",
  relationship: "",
  employment_status: "",
  household_size: "",
  income_monthly: "",
  goals: "",
};

const steps = ["Care recipient", "About you", "Household", "Goals"] as const;

export default function IntakePage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(empty);
  const [submitting, setSubmitting] = useState(false);

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const pct = ((step + 1) / steps.length) * 100;

  async function finish() {
    setSubmitting(true);
    const profile: Partial<CaseProfile> = {
      id: "",
      care_recipient: {
        age: form.age ? Number(form.age) : null,
        state: form.state,
        conditions: [],
        veteran: form.veteran,
        insurance: form.insurance,
        current_benefits: [],
        care_needs: form.care_needs ? form.care_needs.split(",").map((s) => s.trim()) : [],
      },
      caregiver: {
        relationship: form.relationship,
        employment_status: form.employment_status,
        hours_per_week: null,
      },
      household: {
        size: form.household_size ? Number(form.household_size) : null,
        income_monthly: form.income_monthly ? Number(form.income_monthly) : null,
        assets: null,
      },
      goals: form.goals ? form.goals.split(",").map((s) => s.trim()) : [],
    };
    try {
      const created = await submitIntake(profile);
      localStorage.setItem("ilera_case_id", created.id);
      router.push(`/eligibility/${created.id}`);
    } catch {
      setSubmitting(false);
      alert("Could not reach the API. Is the backend running on :8000?");
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 py-12">
      <div className="space-y-2">
        <Progress value={pct} />
        <p className="text-sm text-muted-foreground">
          Step {step + 1} of {steps.length}: {steps[step]}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{steps[step]}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {step === 0 && (
            <>
              <Field label="Care recipient age">
                <Input type="number" value={form.age} onChange={(e) => set({ age: e.target.value })} />
              </Field>
              <Field label="State">
                <Input value={form.state} onChange={(e) => set({ state: e.target.value })} />
              </Field>
              <Field label="Primary insurance" hint="Medi-Cal status strongly affects eligibility for IHSS.">
                <select
                  className="h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                  value={form.insurance}
                  onChange={(e) => set({ insurance: e.target.value as Insurance })}
                >
                  <option value="unknown">Not sure</option>
                  <option value="medi-cal">Medi-Cal</option>
                  <option value="medicare">Medicare</option>
                  <option value="private">Private</option>
                  <option value="none">None</option>
                </select>
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.veteran}
                  onChange={(e) => set({ veteran: e.target.checked })}
                />
                Care recipient is a veteran
              </label>
              <Field label="Care needs (comma separated)">
                <Input
                  placeholder="bathing, mobility, medication"
                  value={form.care_needs}
                  onChange={(e) => set({ care_needs: e.target.value })}
                />
              </Field>
            </>
          )}

          {step === 1 && (
            <>
              <Field label="Your relationship to the care recipient">
                <Input
                  placeholder="daughter, spouse, friend…"
                  value={form.relationship}
                  onChange={(e) => set({ relationship: e.target.value })}
                />
              </Field>
              <Field label="Your employment status" hint="Affects Paid Family Leave eligibility.">
                <Input
                  placeholder="full-time, part-time, unemployed…"
                  value={form.employment_status}
                  onChange={(e) => set({ employment_status: e.target.value })}
                />
              </Field>
            </>
          )}

          {step === 2 && (
            <>
              <Field label="Household size">
                <Input
                  type="number"
                  value={form.household_size}
                  onChange={(e) => set({ household_size: e.target.value })}
                />
              </Field>
              <Field label="Monthly household income (USD)" hint="Used to estimate Medi-Cal eligibility.">
                <Input
                  type="number"
                  value={form.income_monthly}
                  onChange={(e) => set({ income_monthly: e.target.value })}
                />
              </Field>
            </>
          )}

          {step === 3 && (
            <Field label="What are you hoping to get help with? (comma separated)">
              <Input
                placeholder="get paid to provide care, lower medical costs"
                value={form.goals}
                onChange={(e) => set({ goals: e.target.value })}
              />
            </Field>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Button variant="outline" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          Back
        </Button>
        {step < steps.length - 1 ? (
          <Button onClick={() => setStep((s) => s + 1)}>Next</Button>
        ) : (
          <Button onClick={finish} disabled={submitting}>
            {submitting ? "Submitting…" : "Determine eligibility"}
          </Button>
        )}
      </div>
    </main>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

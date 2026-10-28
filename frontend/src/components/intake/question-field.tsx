"use client";

import { ExternalLink } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TagInput } from "@/components/intake/tag-input";
import { HouseholdMembers } from "@/components/intake/household-members";
import { ProgramDetails } from "@/components/intake/program-details";
import { cn } from "@/lib/utils";
import {
  type AnswerValue,
  type Answers,
  type Question,
  US_STATES,
  effectiveOptions,
  interpolateName,
} from "@/lib/intake-schema";

interface Props {
  question: Question;
  value: AnswerValue;
  name: string;
  error?: string;
  answers?: Answers;
  onChange: (value: AnswerValue) => void;
}

export function QuestionField({ question, value, name, error, answers = {}, onChange }: Props) {
  const text = interpolateName(question.text, name);
  const taxYear = answers["tax.year"];
  const selectedTaxYear = typeof taxYear === "number" && Number.isInteger(taxYear) && taxYear >= 2000 && taxYear <= 2100 ? taxYear : undefined;
  const helper = question.field_id === "tax.lived_together_over_half_year" && selectedTaxYear
    ? `For the ${selectedTaxYear} tax year, count the time from January 1 through December 31, ${selectedTaxYear}. This is the year the income or care expenses are from, even if you file the return in ${selectedTaxYear + 1}.`
    : question.helper_text ? interpolateName(question.helper_text, name) : undefined;
  const helperLinks = [...(question.helper_link ? [question.helper_link] : []), ...(question.helper_links ?? [])];
  const why = question.why_this_matters ? interpolateName(question.why_this_matters, name) : undefined;

  return (
    // Full height with the control pushed to the bottom, so side-by-side fields keep
    // their inputs on one line even when only one of them has helper text.
    <div className="flex h-full flex-col gap-2" data-field-id={question.field_id} role="group" aria-label={text}>
      {text && !question.hide_title && (
        <Label className="block text-base font-medium">
          {text}
          {!question.required && <span className="ml-1 text-sm text-muted-foreground">(optional)</span>}
        </Label>
      )}
      {helper && <p className="whitespace-pre-line text-sm text-muted-foreground">{helper}</p>}
      {helperLinks.length > 0 && (
        <div className="mb-2 space-y-1.5">
          {helperLinks.map((link, index) => <a
            key={`${link.href}-${index}`}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="group flex w-fit items-center gap-1.5 text-sm text-primary"
          >
            <span className="relative after:absolute after:-bottom-0.5 after:left-0 after:h-px after:w-full after:origin-left after:scale-x-0 after:bg-current after:transition-transform after:duration-300 group-hover:after:scale-x-100 group-focus-visible:after:scale-x-100">{link.text}</span>
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>)}
        </div>
      )}
      {why && (
        <p className="text-sm text-muted-foreground">
          <span className="font-medium">Why this matters: </span>
          {why}
        </p>
      )}

      <div className={`mt-auto space-y-1.5 ${question.type === "household_members" ? "pt-2" : ""}`}>
        <FieldControl question={question} value={value} name={name} answers={answers} onChange={onChange} />
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </div>
  );
}

function FieldControl({
  question,
  value,
  name,
  answers = {},
  onChange,
}: Pick<Props, "question" | "value" | "name" | "answers" | "onChange">) {
  switch (question.type) {
    case "household_members":
      return <HouseholdMembers value={value} answers={answers} onChange={onChange} />;
    case "program_statuses":
    case "program_dates":
      return <ProgramDetails question={question} value={value} answers={answers} onChange={onChange} />;
    case "tag_input":
      return (
        <TagInput
          suggestions={question.options ?? []}
          placeholder={question.placeholder}
          value={(value as string[]) ?? []}
          onChange={(tags) => onChange(tags)}
        />
      );
    case "single_select":
      return <SingleSelect question={question} value={value as string} name={name} onChange={onChange} />;
    case "multi_select":
      return (
        <MultiSelect question={question} value={(value as string[]) ?? []} name={name} onChange={onChange} />
      );
    case "boolean":
      return <BooleanField value={value} allowNotSure={!!question.allow_not_sure} allowPreferNot={!!question.allow_prefer_not_to_answer} onChange={onChange} />;
    case "long_text":
      return <TextField question={question} value={value} name={name} onChange={onChange} />;
    case "number":
      return (
        <NumberField
          value={value}
          allowPreferNot={!!question.allow_prefer_not_to_answer}
          allowNotSure={!!question.allow_not_sure}
          validation={question.validation}
          onChange={onChange}
        />
      );
    case "state_dropdown":
      return (
        <select
          className="h-10 w-full rounded-lg border border-input bg-transparent px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select a state…</option>
          {(question.options ?? US_STATES).map((s) => (
            <option key={s} value={s}>
              {question.option_labels?.[s] ?? s}
            </option>
          ))}
        </select>
      );
    case "zip":
      return (
        <Input
          className="h-10"
          inputMode="numeric"
          maxLength={5}
          placeholder="12345"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 5))}
        />
      );
    case "date":
      return <DateField value={value} allowNotSure={!!question.allow_not_sure} allowPreferNot={!!question.allow_prefer_not_to_answer} onChange={onChange} />;
    case "short_text":
    default:
      return <TextField question={question} value={value} name={name} onChange={onChange} />;
  }
}

function TextField({ question, value, name, onChange }: Pick<Props, "question" | "value" | "name" | "onChange">) {
  const unsure = value === "I'm not sure";
  const props = { "aria-label": interpolateName(question.text, name), value: unsure ? "" : typeof value === "string" ? value : "", disabled: unsure, onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value) };
  return <div className="space-y-2">{question.type === "long_text" ? <Textarea {...props} rows={3} /> : <Input {...props} className="h-10" />}{question.allow_not_sure && <button type="button" aria-pressed={unsure} onClick={() => onChange(unsure ? null : "I'm not sure")} className={cn("rounded-lg border px-3 py-1.5 text-xs", unsure ? "border-primary bg-primary/5" : "border-input")}>I&apos;m not sure</button>}</div>;
}

function OptionRow({
  label,
  selected,
  multi,
  onClick,
}: {
  label: string;
  selected: boolean;
  multi: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-base transition-colors",
        selected ? "border-primary bg-primary/5" : "border-input hover:bg-muted",
      )}
    >
      <span
        className={cn(
          "flex size-4 shrink-0 items-center justify-center border",
          multi ? "rounded-[4px]" : "rounded-full",
          selected ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40",
        )}
      >
        {selected && (multi ? "✓" : <span className="size-2 rounded-full bg-current" />)}
      </span>
      <span>{label}</span>
    </button>
  );
}

function SingleSelect({
  question,
  value,
  name,
  onChange,
}: {
  question: Question;
  value: string | undefined;
  name: string;
  onChange: (v: AnswerValue) => void;
}) {
  if (question.display_as === "dropdown") {
    return <select aria-label={interpolateName(question.text, name)} className="h-11 w-full rounded-lg border border-input bg-transparent px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">Choose…</option>
      {effectiveOptions(question).map((opt) => <option key={opt} value={opt}>{interpolateName(question.option_labels?.[opt] ?? opt, name)}</option>)}
    </select>;
  }
  return (
    <div className="space-y-1.5">
      {effectiveOptions(question).map((opt) => (
        <OptionRow
          key={opt}
          label={interpolateName(question.option_labels?.[opt] ?? opt, name)}
          selected={value === opt}
          multi={false}
          onClick={() => onChange(value === opt ? null : opt)}
        />
      ))}
    </div>
  );
}

function MultiSelect({
  question,
  value,
  name,
  onChange,
}: {
  question: Question;
  value: string[];
  name: string;
  onChange: (v: AnswerValue) => void;
}) {
  const exclusive = question.validation?.exclusive_options ?? [];

  function toggle(opt: string) {
    const isExclusive = exclusive.includes(opt);
    if (value.includes(opt)) {
      onChange(value.filter((v) => v !== opt));
      return;
    }
    if (isExclusive) {
      onChange([opt]);
      return;
    }
    // selecting a normal option clears any exclusive selections
    const conflicts = (question.validation?.incompatible_options ?? []).filter(pair => pair.includes(opt)).flat();
    const next = value.filter((v) => !exclusive.includes(v) && !conflicts.includes(v));
    onChange([...next, opt]);
  }

  return (
    <div className="space-y-1.5">
      {effectiveOptions(question).map((opt) => (
        <OptionRow
          key={opt}
          label={interpolateName(question.option_labels?.[opt] ?? opt, name)}
          selected={value.includes(opt)}
          multi
          onClick={() => toggle(opt)}
        />
      ))}
    </div>
  );
}

function BooleanField({
  value,
  allowNotSure,
  allowPreferNot,
  onChange,
}: {
  value: AnswerValue;
  allowNotSure: boolean;
  allowPreferNot: boolean;
  onChange: (v: AnswerValue) => void;
}) {
  const options: { label: string; v: AnswerValue }[] = [
    { label: "Yes", v: true },
    { label: "No", v: false },
    ...(allowNotSure ? [{ label: "I'm not sure", v: "I'm not sure" }] : []),
    ...(allowPreferNot ? [{ label: "Prefer not to answer", v: "Prefer not to answer" }] : []),
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.label}
          type="button"
          aria-pressed={value === o.v}
          onClick={() => onChange(value === o.v ? null : o.v)}
          className={cn(
            "rounded-lg border px-4 py-2 text-base transition-colors",
            value === o.v ? "border-primary bg-primary/5" : "border-input hover:bg-muted",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function NumberField({
  value,
  allowPreferNot,
  allowNotSure,
  validation,
  onChange,
}: {
  value: AnswerValue;
  allowPreferNot: boolean;
  allowNotSure: boolean;
  validation?: Question["validation"];
  onChange: (v: AnswerValue) => void;
}) {
  const isPreferNot = value === "Prefer not to answer";
  const isNotSure = value === "I'm not sure";
  return (
    <div className="space-y-2">
      <Input
        className="h-10"
        type="number"
        min={validation?.min}
        max={validation?.max}
        step={validation?.integer ? 1 : "any"}
        disabled={isPreferNot || isNotSure}
        value={isPreferNot || isNotSure || value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      {allowNotSure && (
        <button type="button" aria-pressed={isNotSure} onClick={() => onChange(isNotSure ? null : "I'm not sure")}
          className={cn("rounded-lg border px-3 py-1.5 text-xs", isNotSure ? "border-primary bg-primary/5" : "border-input")}>
          I&apos;m not sure
        </button>
      )}
      {allowPreferNot && (
        <button
          type="button"
          onClick={() => onChange(isPreferNot ? null : "Prefer not to answer")}
          className={cn(
            "rounded-lg border px-3 py-1.5 text-xs transition-colors",
            isPreferNot ? "border-primary bg-primary/5" : "border-input hover:bg-muted",
          )}
        >
          Prefer not to answer
        </button>
      )}
    </div>
  );
}

function DateField({
  value,
  allowNotSure,
  allowPreferNot,
  onChange,
}: {
  value: AnswerValue;
  allowNotSure: boolean;
  allowPreferNot: boolean;
  onChange: (v: AnswerValue) => void;
}) {
  const isUnknown = value === "I'm not sure" || value === "Prefer not to answer";
  const options = [
    ...(allowNotSure ? ["I'm not sure"] : []),
    ...(allowPreferNot ? ["Prefer not to answer"] : []),
  ];
  return (
    <div className="space-y-2">
      <Input
        className="h-10"
        type="date"
        disabled={isUnknown}
        value={isUnknown || value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        {options.map(option => (
          <button
            key={option}
            type="button"
            aria-pressed={value === option}
            onClick={() => onChange(value === option ? null : option)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-xs transition-colors",
              value === option ? "border-primary bg-primary/5" : "border-input hover:bg-muted",
            )}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

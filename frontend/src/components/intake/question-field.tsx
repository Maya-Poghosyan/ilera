"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TagInput } from "@/components/intake/tag-input";
import { cn } from "@/lib/utils";
import {
  type AnswerValue,
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
  onChange: (value: AnswerValue) => void;
}

export function QuestionField({ question, value, name, error, onChange }: Props) {
  const text = interpolateName(question.text, name);
  const helper = question.helper_text ? interpolateName(question.helper_text, name) : undefined;
  const why = question.why_this_matters ? interpolateName(question.why_this_matters, name) : undefined;

  return (
    <div className="space-y-2">
      <Label className="block text-sm font-medium">
        {text}
        {!question.required && <span className="ml-1 text-xs text-muted-foreground">(optional)</span>}
      </Label>
      {helper && <p className="text-xs text-muted-foreground">{helper}</p>}
      {why && (
        <p className="text-xs text-muted-foreground">
          <span className="font-medium">Why this matters: </span>
          {why}
        </p>
      )}

      <FieldControl question={question} value={value} name={name} onChange={onChange} />

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function FieldControl({
  question,
  value,
  name,
  onChange,
}: Pick<Props, "question" | "value" | "name" | "onChange">) {
  switch (question.type) {
    case "tag_input":
      return (
        <TagInput
          suggestions={question.options ?? []}
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
      return <BooleanField value={value as boolean | null} onChange={onChange} />;
    case "long_text":
      return (
        <Textarea
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
        />
      );
    case "number":
      return (
        <NumberField
          value={value}
          allowPreferNot={!!question.allow_prefer_not_to_answer}
          onChange={onChange}
        />
      );
    case "state_dropdown":
      return (
        <select
          className="h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select a state…</option>
          {US_STATES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      );
    case "zip":
      return (
        <Input
          inputMode="numeric"
          maxLength={5}
          placeholder="12345"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 5))}
        />
      );
    case "date":
      return <DateField value={value} allowNotSure={!!question.allow_not_sure} onChange={onChange} />;
    case "short_text":
    default:
      return (
        <Input value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />
      );
  }
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
        "flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
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
  return (
    <div className="space-y-1.5">
      {effectiveOptions(question).map((opt) => (
        <OptionRow
          key={opt}
          label={interpolateName(opt, name)}
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
    const next = value.filter((v) => !exclusive.includes(v));
    onChange([...next, opt]);
  }

  return (
    <div className="space-y-1.5">
      {effectiveOptions(question).map((opt) => (
        <OptionRow
          key={opt}
          label={interpolateName(opt, name)}
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
  onChange,
}: {
  value: boolean | null;
  onChange: (v: AnswerValue) => void;
}) {
  return (
    <div className="flex gap-2">
      {[
        { label: "Yes", v: true },
        { label: "No", v: false },
      ].map((o) => (
        <button
          key={o.label}
          type="button"
          onClick={() => onChange(value === o.v ? null : o.v)}
          className={cn(
            "rounded-lg border px-4 py-1.5 text-sm transition-colors",
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
  onChange,
}: {
  value: AnswerValue;
  allowPreferNot: boolean;
  onChange: (v: AnswerValue) => void;
}) {
  const isPreferNot = value === "Prefer not to answer";
  return (
    <div className="space-y-2">
      <Input
        type="number"
        disabled={isPreferNot}
        value={isPreferNot || value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
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
  onChange,
}: {
  value: AnswerValue;
  allowNotSure: boolean;
  onChange: (v: AnswerValue) => void;
}) {
  const isNotSure = value === "I'm not sure";
  return (
    <div className="space-y-2">
      <Input
        type="date"
        disabled={isNotSure}
        value={isNotSure || value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      />
      {allowNotSure && (
        <button
          type="button"
          onClick={() => onChange(isNotSure ? null : "I'm not sure")}
          className={cn(
            "rounded-lg border px-3 py-1.5 text-xs transition-colors",
            isNotSure ? "border-primary bg-primary/5" : "border-input hover:bg-muted",
          )}
        >
          I&apos;m not sure
        </button>
      )}
    </div>
  );
}

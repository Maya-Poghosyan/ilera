import { FileText } from "lucide-react";
import { inputLabelIsRedundant } from "@/features/applications/screens";
import type { AppQuestion } from "@/features/applications/types";
import { QuestionField } from "@/features/intake/components/question-field";
import type { Answers, AnswerValue, Question } from "@/features/intake/schema";

/** One screen of form questions: each group's prompt once, then its inputs. */
export function QuestionScreen({ screen, answers, errors, filledFrom, onAnswer }: {
  screen: AppQuestion[][];
  answers: Answers;
  errors: Record<string, string>;
  /** Where a prefilled answer came from, shown under it until it is changed. */
  filledFrom: Record<string, string>;
  onAnswer: (fieldId: string, value: AnswerValue) => void;
}) {
  return (
    <>
      {screen.map((group, g) => {
        // Inputs of a group tend to repeat one explanation under every box; it is said once.
        const shared = group[0]?.why_this_matters ?? "";
        // A lone Yes/No or select input labels itself with filler; the prompt is the question.
        const dropLabel = inputLabelIsRedundant(group);
        return (
          <div key={group[0].group_id || group[0].field_id} className={`space-y-4 pb-5 ${g === 0 ? "" : "pt-5"}`}>
            {group[0].group_prompt && (
              <div className="space-y-1">
                <p className="text-base font-semibold">{group[0].group_prompt}</p>
                {shared && <p className="text-xs text-muted-foreground">{shared}</p>}
              </div>
            )}
            {group.map((question, i) => {
              const repeated = question.why_this_matters === shared || question.why_this_matters === group[i - 1]?.why_this_matters;
              const cleaned = {
                ...question,
                why_this_matters: repeated ? "" : question.why_this_matters,
                text: dropLabel ? "" : question.text,
                // A state list with no options of its own offers every state.
                options: question.type === "state_dropdown" && !question.options?.length ? undefined : question.options,
              };
              const source = filledFrom[question.field_id];
              return (
                <div key={question.field_id} className="space-y-1.5">
                  <QuestionField
                    question={cleaned as Question}
                    value={answers[question.field_id] ?? null}
                    name=""
                    error={errors[question.field_id]}
                    onChange={(v) => onAnswer(question.field_id, v)}
                  />
                  {source && (
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <FileText aria-hidden="true" className="size-3.5 shrink-0" />
                      Filled in from {source}. Change it if it&rsquo;s wrong.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}

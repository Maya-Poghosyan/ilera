import type { ReactNode } from "react";

import { QuestionField } from "@/features/intake/components/question-field";
import type { Answers, AnswerValue, Question } from "@/features/intake/schema";

// Stacked on narrow screens, side by side once there's room for readable fields.
const INLINE_COLS: Record<number, string> = { 1: "grid-cols-1", 2: "grid-cols-1 sm:grid-cols-2", 3: "grid-cols-1 sm:grid-cols-3" };

/** A page's questions; consecutive `inline` questions of one group share a row. `before` renders
 * anything that belongs above a question (document suggestions). */
export function QuestionList({ questions, name, answers, errors, onAnswer, before }: {
  questions: Question[];
  name: string;
  answers: Answers;
  errors: Record<string, string>;
  onAnswer: (fieldId: string, value: AnswerValue) => void;
  before: (question: Question) => ReactNode;
}) {
  const field = (q: Question) => (
    <QuestionField key={q.field_id} question={q} answers={answers} value={answers[q.field_id] ?? null}
                   name={name} error={errors[q.field_id]} onChange={(v) => onAnswer(q.field_id, v)} />
  );
  const prefix = (q: Question) => {
    const node = before(q);
    return node ? <div key={`before-${q.field_id}`}>{node}</div> : null;
  };
  const elements: ReactNode[] = [];
  for (let i = 0; i < questions.length;) {
    const cur = questions[i];
    if (cur.layout !== "inline") {
      elements.push(prefix(cur), field(cur));
      i++;
      continue;
    }
    let j = i + 1;
    while (j < questions.length && questions[j].layout === "inline" && questions[j].group === cur.group) j++;
    const row = questions.slice(i, j);
    elements.push(...row.map(prefix));
    elements.push(
      <div key={`inline-${cur.field_id}`} className={`grid items-end gap-5 ${INLINE_COLS[row.length] ?? INLINE_COLS[2]}`}>
        {row.map(field)}
      </div>,
    );
    i = j;
  }
  return <>{elements}</>;
}

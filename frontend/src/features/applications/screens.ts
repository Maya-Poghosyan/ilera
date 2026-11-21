import type { Answers } from "@/features/intake/schema";
import type { AppQuestion } from "@/features/applications/types";

/** The inputs the backend put under one `group_id`: one thing a person knows. */
function groupQuestions(questions: AppQuestion[]): AppQuestion[][] {
  const groups: AppQuestion[][] = [];
  for (const question of questions) {
    const last = groups[groups.length - 1];
    if (last && question.group_id && last[0].group_id === question.group_id) {
      last.push(question);
    } else {
      groups.push([question]);
    }
  }
  return groups;
}

const INPUTS_PER_SCREEN = 6;

// Generic input labels that repeat the answer control instead of naming a question:
// a Yes/No group prints "Yes or No" above its two buttons, a select prints "Select one".
const GENERIC_INPUT_LABELS = new Set([
  "yes or no",
  "yes/no",
  "yes / no",
  "select one",
  "select",
  "choose one",
]);

/**
 * Whether a single-input group's input label is redundant with its prompt.
 *
 * These forms carry the real question in the group prompt ("Is the patient a family
 * member?") and give the lone input a filler label ("Yes or No"). Rendered as-is the
 * screen stutters: the question, then a generic label, then the buttons. When a group
 * has exactly one input and that input's label adds nothing — it is generic, empty, or
 * just repeats the prompt — the label is dropped so the prompt stands alone.
 */
export function inputLabelIsRedundant(group: AppQuestion[]): boolean {
  if (group.length !== 1) return false;
  const only = group[0];
  if (!only.group_prompt) return false;
  const label = (only.text ?? "").trim().toLowerCase();
  if (!label) return true;
  if (GENERIC_INPUT_LABELS.has(label)) return true;
  return label === only.group_prompt.trim().toLowerCase();
}

/**
 * Groups gathered onto screens, so a yes/no question doesn't get a page to itself.
 *
 * Neighbouring groups come from the same part of the form, so they read as one short
 * page of related questions. The packing is done before any answers are given and
 * never changes, so answering something can't shuffle the screens underneath you.
 */
function toScreens(groups: AppQuestion[][]): AppQuestion[][][] {
  const screens: AppQuestion[][][] = [];
  for (const group of groups) {
    const last = screens[screens.length - 1];
    const filled = last?.reduce((n, g) => n + g.length, 0) ?? 0;
    if (last && filled + group.length <= INPUTS_PER_SCREEN) {
      last.push(group);
    } else {
      screens.push([group]);
    }
  }
  return screens;
}

/**
 * Whether a follow-up screen is worth showing, given what has been answered.
 *
 * The backend sends the "if yes, ..." parts of a form with an `ask_when` naming the
 * answer they depend on, e.g. `past_ihss.received_ihss_before == "Yes"`. An unmet
 * condition skips the screen. A condition nobody can answer — the question it names
 * isn't asked here — shows it, since an unasked question is a blank box on a
 * government form.
 */
function shouldAsk(
  group: AppQuestion[],
  answers: Answers,
  asked: Set<string>
): boolean {
  const condition = group[0]?.ask_when;
  if (!condition) return true;
  const match = /^\s*([\w.]+)\s*(==|!=)\s*(.+?)\s*$/.exec(condition);
  if (!match) return true;
  const [, path, op, rawExpected] = match;
  const answer = answers[path];
  if (answer === undefined || answer === null || answer === "") {
    // Still blank. A section the applicant hasn't opted into isn't shown while it is
    // undecided — an appendix appears when they say it applies, not before.
    return !asked.has(path);
  }
  const expected = rawExpected.replace(/^['"]|['"]$/g, "").toLowerCase();
  const given = (Array.isArray(answer) ? answer : [answer]).map((v) =>
    String(v).toLowerCase()
  );
  const matches = given.includes(expected);
  return op === "==" ? matches : !matches;
}

/** The screens to show now: question groups packed onto pages, minus follow-ups whose condition
 * the answers so far rule out. */
export function visibleScreens(questions: AppQuestion[], answers: Answers): AppQuestion[][][] {
  const asked = new Set(questions.map((q) => q.field_id));
  return toScreens(groupQuestions(questions))
    .map((screen) => screen.filter((group) => shouldAsk(group, answers, asked)))
    .filter((screen) => screen.length > 0);
}

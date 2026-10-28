"use client";
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { type Answers, type AnswerValue, type Question, type ProgramAnswers } from '@/lib/intake-schema';
export function ProgramDetails({ question, value, answers, onChange }: { question: Question; value: AnswerValue; answers: Answers; onChange: (v: AnswerValue) => void }) {
  const selected = answers['recipient.programs_touched'];
  const programs = Array.isArray(selected) ? selected.filter(p => typeof p === 'string') as string[] : [];
  const rows = value && typeof value === 'object' && !Array.isArray(value) ? value as ProgramAnswers : {};
  const update = (program: string, entry: string) => onChange(Object.fromEntries(programs.map(p => [p,p === program ? entry : rows[p] ?? ''])));
  return <div className="space-y-5">{programs.map(program => {
    const label = program === 'Other' && typeof answers['recipient.other_program'] === 'string' ? answers['recipient.other_program'] as string : question.option_labels?.[program] ?? program;
    return <div key={program} className="grid items-start gap-3 border-b pb-5 sm:grid-cols-[minmax(0,1fr)_2fr]"><p className="pt-2 font-medium">{label}</p>{question.type === 'program_statuses' ? <select aria-label={`${label} status`} className="h-11 w-full rounded-lg border border-input bg-transparent px-3" value={rows[program] ?? ''} onChange={e=>update(program,e.target.value)}><option value="">Choose a status…</option>{question.options?.map(option=><option key={option}>{option}</option>)}</select> : <div className="space-y-2"><Input aria-label={`${label} application or decision date`} type="date" disabled={rows[program] === "I'm not sure"} value={rows[program] === "I'm not sure" ? '' : rows[program] ?? ''} onChange={e=>update(program,e.target.value)} /><Button type="button" size="sm" variant="outline" aria-pressed={rows[program] === "I'm not sure"} onClick={()=>update(program,rows[program] === "I'm not sure" ? '' : "I'm not sure")}>I need to check the date</Button></div>}</div>;
  })}</div>;
}

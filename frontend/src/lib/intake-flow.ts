import { type Answers, type IntakeSchema, type Question, evalCondition, validateQuestions } from './intake-schema';
export interface IntakePage { key: string; title: string; introText?: string; introEmphasis?: string; helperText?: string; helperLink?: {text:string;href:string}; showIntro: boolean; kind: 'intro'|'questions'; questions: Question[]; }
export function paginate(questions: Question[]): Question[][] {
  const pages: Question[][]=[];
  for (const question of questions) {
    const previous=pages[pages.length-1];
    if (previous && question.page_group && previous[0].page_group===question.page_group) previous.push(question);
    else pages.push([question]);
  }
  return pages;
}
export function buildPages(schema: IntakeSchema,answers: Answers): IntakePage[] {
  return schema.screens.flatMap(section=>{
    const groups=paginate(section.questions.filter(q=>evalCondition(q.show_when,answers)));
    if(!groups.length)return [];
    return [{key:`section:${section.id}`,title:section.title,introText:section.intro_text,introEmphasis:section.intro_emphasis,showIntro:true,kind:'intro' as const,questions:[]},...groups.map(questions=>({key:questions[0].field_id,title:questions[0].page_title??section.title,helperText:questions[0].page_helper_text,helperLink:questions[0].page_helper_link,showIntro:false,kind:'questions' as const,questions}))];
  });
}
export function pageIndex(pages: IntakePage[],questionId: string|null): number {
  const found=pages.findIndex(p=>p.key===questionId || p.questions.some(q=>q.field_id===questionId));
  return found<0?0:found;
}

// Resume the completed prefix, rather than an arbitrary later page visited before saving.
export function lastCompletedPage(pages: IntakePage[], answers: Answers): string | null {
  let completed: string | null = null;
  for (const page of pages) {
    if (page.kind === 'intro') continue;
    const hasAnswer = page.questions.some(q => {
      const value = answers[q.field_id];
      return value !== undefined && value !== null && value !== '' && (!Array.isArray(value) || value.length > 0);
    });
    if (!hasAnswer || Object.keys(validateQuestions(page.questions, answers)).length > 0) break;
    completed = page.key;
  }
  return completed ?? pages.find(page => page.kind === 'questions')?.key ?? null;
}

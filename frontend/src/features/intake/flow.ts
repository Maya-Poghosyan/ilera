import { type Answers, type IntakeSchema, type Question, type UploadDocument, evalCondition, validateQuestions } from '@/features/intake/schema';
export interface IntakePage { key: string; title: string; introText?: string; introDocuments?: { document: string; location: string }[]; introEmphasis?: string; helperText?: string; helperLink?: {text:string;href:string}; uploadDocuments?: UploadDocument[]; showIntro: boolean; kind: 'intro'|'questions'; questions: Question[]; }
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
    return [{key:`section:${section.id}`,title:section.title,introText:section.intro_text,introDocuments:section.intro_documents,introEmphasis:section.intro_emphasis,uploadDocuments:section.upload_documents,showIntro:true,kind:'intro' as const,questions:[]},...groups.map(questions=>({key:questions[0].field_id,title:questions[0].page_title??section.title,helperText:questions[0].page_helper_text,helperLink:questions[0].page_helper_link,uploadDocuments:questions.some(q=>q.upload_when&&evalCondition(q.upload_when,answers))?section.upload_documents:undefined,showIntro:false,kind:'questions' as const,questions}))];
  });
}
export function pageIndex(pages: IntakePage[],questionId: string|null): number {
  const found=pages.findIndex(p=>p.key===questionId || p.questions.some(q=>q.field_id===questionId));
  return found<0?0:found;
}

export function intakeIssues(pages: IntakePage[], answers: Answers) {
  let section = '';
  return pages.flatMap(page => {
    if (page.kind === 'intro') {
      section = page.title;
      return [];
    }
    const errors = validateQuestions(page.questions, answers);
    return page.questions.filter(q => errors[q.field_id]).map(question => ({
      section, question, pageKey: page.key, message: errors[question.field_id],
    }));
  });
}

export function resumePage(pages: IntakePage[], questionId: string | null, answers: Answers): string | null {
  const saved = pages.find(page => page.key === questionId || page.questions.some(q => q.field_id === questionId));
  return saved?.key ?? lastCompletedPage(pages, answers);
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

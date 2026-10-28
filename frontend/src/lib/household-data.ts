import type { Answers, AnswerValue, HouseholdMember } from './intake-schema';
export const INCOME_SOURCES = ['Wages', 'Self-employment', 'Social Security retirement or survivor benefits', 'SSDI', 'SSI', 'Pension or retirement payments', 'VA benefits', 'Interest, investments or rental income', 'Other income', 'No income', "I'm not sure"];
export const MEMBER_EMPLOYMENT = ['Employed full time', 'Employed part time', 'Self-employed', 'Not working', 'Retired', 'Student', 'Other', "I'm not sure"];
export const HOUSEHOLD_RELATIONSHIPS = ['Self', 'Spouse or partner', 'Child', 'Parent', 'Sibling', 'Other relative', 'Grandparent', 'Grandchild', 'Parent-in-law', 'Child-in-law', 'Friend or neighbor', 'Unrelated person', 'Other'];
export const HOUSEHOLD_TAX_LINKS = ['They are claimed by the recipient', 'They claim the recipient', 'Neither', 'Another tax relationship', "I'm not sure"];
const unsure = "I'm not sure";
export function validHouseholdMembers(value: AnswerValue, answers: Answers = {}): boolean {
  if (!Array.isArray(value) || value.length < 1 || value.length > 30) return false;
  const members = value as HouseholdMember[];
  if (members.some(m => !m || typeof m !== 'object')) return false;
  const kinds = members.map(m => m.kind);
  if (kinds.filter(k => k === 'recipient').length !== 1 || kinds.filter(k => k === 'spouse').length > 1 || kinds.filter(k => k === 'caregiver').length > 1) return false;
  if (kinds.includes('spouse') !== (answers['recipient.marital_status'] === 'Yes')) return false;
  if (kinds.includes('caregiver') !== (!(answers['recipient.marital_status'] === 'Yes' && answers['caregiver.relationship'] === 'Spouse or domestic partner'))) return false;
  const number = (v: unknown, max: number, integer = false) => v === unsure || typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= max && (!integer || Number.isInteger(v));
  return members.every(m => Object.keys(m).sort().join(',') === 'age,employment_status,gross_monthly_income,income_other,income_sources,income_varies,kind,lives_with_recipient,relationship,tax_link'
    && ['recipient','spouse','caregiver','other'].includes(m.kind)
    && HOUSEHOLD_RELATIONSHIPS.includes(m.relationship)
    && (m.kind !== 'recipient' || m.relationship === 'Self' && m.lives_with_recipient === true)
    && (m.kind !== 'spouse' || m.relationship === 'Spouse or partner')
    && (m.kind !== 'other' || !['Self','Spouse or partner'].includes(m.relationship))
    && HOUSEHOLD_TAX_LINKS.includes(m.tax_link) && MEMBER_EMPLOYMENT.includes(m.employment_status)
    && number(m.age,120,true) && number(m.gross_monthly_income,1000000000)
    && (typeof m.lives_with_recipient === 'boolean' || m.lives_with_recipient === unsure)
    && ['Yes','No',unsure].includes(m.income_varies)
    && Array.isArray(m.income_sources) && m.income_sources.length > 0 && m.income_sources.every(x => INCOME_SOURCES.includes(x))
    && new Set(m.income_sources).size === m.income_sources.length
    && !(m.income_sources.length > 1 && m.income_sources.some(x => [unsure,'No income'].includes(x)))
    && typeof m.income_other === 'string' && (!m.income_sources.includes('Other income') || !!m.income_other.trim())
    && (!m.income_sources.includes('No income') || m.gross_monthly_income === 0 && m.income_varies === 'No'));
}
export function householdDetails(answers: Answers): Answers {
  const value = answers['household.members'];
  if (!Array.isArray(value)) return {};
  const members = value.filter(m => m && typeof m === 'object') as HouseholdMember[];
  const data: Answers = {};
  for (const m of members) {
    const prefix = m.kind === 'recipient' ? 'recipient' : m.kind === 'spouse' ? 'recipient.spouse' : m.kind === 'caregiver' ? 'caregiver' : null;
    if (!prefix) continue;
    for (const key of ['income_sources','gross_monthly_income','income_varies','employment_status'] as const) data[`${prefix}.${key}`] = m[key];
    data[`${prefix}.has_income`] = m.income_sources?.length === 1 && m.income_sources[0] === 'No income' ? false : Array.isArray(m.income_sources) && m.income_sources.length && !m.income_sources.includes(unsure) ? true : null;
  }
  if (answers['recipient.marital_status'] === 'Yes' && answers['caregiver.relationship'] === 'Spouse or domestic partner' && 'recipient.spouse.has_income' in data) {
    for (const key of ['income_sources','gross_monthly_income','income_varies','employment_status','has_income']) data[`caregiver.${key}`] = data[`recipient.spouse.${key}`];
  }
  if (validHouseholdMembers(value, answers)) {
    const resident = members.filter(m => m.lives_with_recipient === true);
    const residenceKnown = members.every(m => typeof m.lives_with_recipient === 'boolean');
    data['recipient.household_size'] = residenceKnown ? resident.length : null;
    data['household.reported_income_monthly'] = residenceKnown && resident.every(m => typeof m.gross_monthly_income === 'number' && !m.income_sources.includes(unsure)) ? resident.reduce((sum,m) => sum + (m.gross_monthly_income as number),0) : null;
  }
  return data;
}

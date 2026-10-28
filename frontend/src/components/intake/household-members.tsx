"use client";
import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { type Answers, type AnswerValue, type HouseholdMember, answerContext } from '@/lib/intake-schema';
import { INCOME_SOURCES, MEMBER_EMPLOYMENT, HOUSEHOLD_RELATIONSHIPS, HOUSEHOLD_TAX_LINKS, householdDetails, validHouseholdMembers } from '@/lib/household-data';
const unsure = "I'm not sure";
const selectClass = 'h-11 w-full rounded-lg border border-input appearance-none bg-transparent pl-3 pr-10';
const blank = (kind: HouseholdMember['kind'], relationship: string, age: number | string | null = null, residence: boolean | string | null = null): HouseholdMember => ({ kind, relationship, age, lives_with_recipient: residence, tax_link: 'Neither', employment_status: '', gross_monthly_income: null, income_sources: [], income_other: '', income_varies: '' });
export function HouseholdMembers({ value, answers, onChange }: { value: AnswerValue; answers: Answers; onChange: (v: AnswerValue) => void }) {
  const [editing,setEditing] = useState<number | null>(null);
  const [step,setStep] = useState(0);
  const stored = Array.isArray(value) && value.every(m => m && typeof m === 'object' && 'kind' in m) ? value as HouseholdMember[] : [];
  const context = answerContext(answers);
  const recipientFirstName = answers['recipient.first_name'];
  const recipientLabel = typeof recipientFirstName === 'string' && recipientFirstName.trim() ? recipientFirstName.trim() : 'the person receiving care';
  const married = answers['recipient.marital_status'] === 'Yes';
  const cgSpouse = married && answers['caregiver.relationship'] === 'Spouse or domestic partner';
  const cgResident = answers['caregiver.coresidence'] === 'Yes';
  const recipientAge = typeof context['recipient.age'] === 'number' ? context['recipient.age'] : unsure;
  const caregiverAge = typeof context['caregiver.age'] === 'number' ? context['caregiver.age'] : unsure;
  const defaults = [blank('recipient','Self',recipientAge,true)];
  if (married) defaults.push(blank('spouse','Spouse or partner',cgSpouse ? caregiverAge : null,cgSpouse ? cgResident : answers['recipient.spouse_living_situation'] === 'With the recipient' ? true : answers['recipient.spouse_living_situation'] === unsure ? unsure : false));
  if (!cgSpouse) defaults.push(blank('caregiver',({'Spouse or domestic partner':'Spouse or partner',Parent:'Child',Child:'Parent',Grandparent:'Grandchild',Grandchild:'Grandparent','Parent-in-law':'Child-in-law',Sibling:'Sibling',Friend:'Friend or neighbor',Neighbor:'Friend or neighbor','Other relative':'Other relative'} as Record<string,string>)[String(answers['caregiver.relationship'])] ?? 'Other',caregiverAge,cgResident));
  const members = defaults.map(d => {
    const existing = stored.find(m=>m.kind === d.kind);
    const m = existing ? { ...existing, relationship: d.relationship } : d;
    if (d.kind === 'recipient' || d.kind === 'caregiver' || cgSpouse && d.kind === 'spouse') m.age = d.age;
    if (d.kind === 'recipient' || d.kind === 'caregiver' || d.kind === 'spouse') m.lives_with_recipient = d.lives_with_recipient;
    if (d.kind === 'caregiver') { const raw = String(answers['caregiver.employment_status'] ?? ''); m.employment_status = MEMBER_EMPLOYMENT.includes(raw) ? raw : raw ? 'Not working' : ''; }
    return m;
  }).concat(stored.filter(m=>m.kind === 'other'));
  const serialized = JSON.stringify(members);
  const original = JSON.stringify(stored);
  useEffect(()=> { if(serialized !== original) onChange(JSON.parse(serialized)); },[serialized,original,onChange]);
  const index = editing !== null && editing < members.length ? editing : null;
  const member = index === null ? null : members[index];
  const firstStep = member?.kind === 'recipient' ? 1 : 0;
  function label(m: HouseholdMember,i: number) { return m.kind === 'recipient' ? 'Care recipient' : m.kind === 'spouse' ? cgSpouse ? 'You (their spouse)' : "Recipient’s spouse or partner" : m.kind === 'caregiver' ? 'You' : `Household Member ${i+1}`; }
  function update(patch: Partial<HouseholdMember>) { if(index !== null) onChange(members.map((m,i)=>i === index ? {...m,...patch}:m)); }
  function select(text: string,current: string,options: string[],change: (s:string)=>void) { return <label className={`flex flex-col ${text === 'Their employment status' ? 'gap-3' : 'gap-2'}`}> <span className="text-base font-medium">{text}</span><span className="relative block"><select aria-label={text} className={selectClass} value={current} onChange={e=>change(e.target.value)}><option value="">Choose…</option>{options.map(o=><option key={o}>{o}</option>)}</select><ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /></span></label>; }
  function numeric(text: string,current: number|string|null,change: (s:number|string|null)=>void,age=false) { return <div className="space-y-2"><label className="block space-y-2"><span>{text}</span><Input aria-label={text} disabled={current === unsure} type="number" min={0} max={age ? 120 : 1000000000} step={age ? 1 : 'any'} value={typeof current === 'number' ? current : ''} onChange={e=>change(e.target.value === '' ? null : Number(e.target.value))}/></label><Button type="button" variant={current === unsure ? "secondary" : "outline"} className={current === unsure ? "border border-primary bg-secondary text-foreground" : ""} size="sm" onClick={()=>change(current === unsure ? null : unsure)} aria-pressed={current === unsure}>I need to check this {age ? 'age' : 'amount'}</Button></div>; }
  const stageValid = member && (step === 0 ? HOUSEHOLD_RELATIONSHIPS.includes(member.relationship) && (member.age === unsure || typeof member.age === 'number' && Number.isInteger(member.age) && member.age >= 0 && member.age <= 120) && (typeof member.lives_with_recipient === 'boolean' || member.lives_with_recipient === unsure) && HOUSEHOLD_TAX_LINKS.includes(member.tax_link) : step === 1 ? MEMBER_EMPLOYMENT.includes(member.employment_status) && member.income_sources.length > 0 && (!member.income_sources.includes('Other income') || !!member.income_other.trim()) : validHouseholdMembers(members.map((m,i)=>i===index ? member : {...m,employment_status: m.employment_status || 'Not working',income_sources:['No income'],gross_monthly_income:0,income_varies:'No',age:m.age ?? unsure,lives_with_recipient:m.lives_with_recipient ?? unsure}),answers));
  const total = householdDetails({...answers,'household.members':members})['household.reported_income_monthly'];
  return <div className="space-y-4">{index === null && <>
    {members.map((m,i)=><div key={`${m.kind}-${i}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"><div><p className="font-medium">{label(m,i)}</p><p className="text-sm text-muted-foreground">{m.income_sources.length ? m.income_sources.join(', ') : 'Income details needed'}{typeof m.gross_monthly_income === 'number' ? ` · $${m.gross_monthly_income.toLocaleString()}/month` : m.gross_monthly_income === unsure ? ' · Amount to check' : ''}</p></div><div className="flex gap-2"><Button type="button" variant="outline" size="sm" onClick={()=>{setEditing(i);setStep(m.kind === 'recipient' ? 1 : 0);}}>Edit {m.kind === 'spouse' && !cgSpouse ? "recipient’s spouse or partner" : label(m,i)}</Button>{m.kind === 'other'&&<Button type="button" variant="ghost" size="sm" onClick={()=>onChange(members.filter((_,j)=>i!==j))}>Remove</Button>}</div></div>)}
    <Button type="button" variant="outline" disabled={members.length>=30} onClick={()=>{onChange([...members,blank('other','')]);setEditing(members.length);setStep(0);}}>Add household member</Button>
    {typeof total === 'number' ? <p className="text-sm">Total monthly income for people living with {recipientLabel}: <strong>${total.toLocaleString()}</strong>.</p> : <p className="text-sm text-muted-foreground">Add everyone who belongs on this list. We’ll total the income you enter for members living with the recipient.</p>}
  </>}
  {member && <div className="space-y-5 rounded-lg border p-4"><p className="font-medium">{label(member,index!)} · Details {step-firstStep+1} of {3-firstStep}</p>
    {step===0 && <>{member.kind==='other' && select('Their relationship to the care recipient',member.relationship,HOUSEHOLD_RELATIONSHIPS.filter(r=>!['Self','Spouse or partner'].includes(r)),relationship=>update({relationship}))}{!(member.kind==='recipient'||member.kind==='caregiver'||cgSpouse&&member.kind==='spouse') && numeric('How old are they?',member.age,age=>update({age}),true)}{member.kind==='other'&&select('Do they live with the care recipient?',typeof member.lives_with_recipient==='boolean' ? member.lives_with_recipient ? 'Yes':'No':'',["Yes","No"],s=>update({lives_with_recipient:s==='Yes'}))}{member.kind!=='spouse' && select(member.kind==='caregiver' ? 'How are your taxes connected to the care recipient?' : 'How are their taxes connected to the care recipient?',member.tax_link,HOUSEHOLD_TAX_LINKS,tax_link=>update({tax_link}))}</>}
    {step===1 && <>{member.kind!=='caregiver' && select('Their employment status',member.employment_status,MEMBER_EMPLOYMENT,employment_status=>update({employment_status}))}<p className="text-base font-medium">{member.kind==='caregiver'||cgSpouse&&member.kind==='spouse' ? 'Your income sources' : 'Their income sources'}</p><div className="flex flex-wrap gap-2">{INCOME_SOURCES.map(source=><Button type="button" key={source} variant={member.income_sources.includes(source)?'secondary':'outline'} size="sm" aria-pressed={member.income_sources.includes(source)} onClick={()=>{
      let income_sources=member.income_sources.includes(source)?member.income_sources.filter(x=>x!==source):[...member.income_sources.filter(x=>![unsure,'No income'].includes(x)),source];
      if([unsure,'No income'].includes(source)) income_sources=member.income_sources.includes(source)?[]:[source];
      update({income_sources, income_other: income_sources.includes('Other income')?member.income_other:'', ...(income_sources.includes('No income')?{gross_monthly_income:0,income_varies:'No'}: member.income_sources.includes('No income')?{gross_monthly_income:null,income_varies:''}:{})});
    }}>{source==='SSDI'?'Social Security Disability Insurance (SSDI)':source==='SSI'?'Supplemental Security Income (SSI)':source}</Button>)}</div>{member.income_sources.includes('Other income')&&<label className="block space-y-2"><span>Other income source</span><Input aria-label="Other income source" value={member.income_other} onChange={e=>update({income_other:e.target.value})}/></label>}</>}
    {step===2 && <>{member.income_sources.includes('No income')?<p>No income reported; monthly amount is $0.</p>:<>{numeric('Monthly income before deductions ($)',member.gross_monthly_income,gross_monthly_income=>update({gross_monthly_income}))}{select('Does this income change month to month?',member.income_varies,['Yes','No',unsure],income_varies=>update({income_varies}))}<p className="text-sm text-muted-foreground">Use gross pay or the benefit amount before taxes, Medicare premiums and other deductions. Recent pay statements and benefit letters can help.</p></>}</>}
    <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" onClick={()=>step>firstStep?setStep(step-1):setEditing(null)}>{step>firstStep?'Previous details':'Back to household'}</Button><Button type="button" disabled={!stageValid} onClick={()=>step<2?setStep(step+1):setEditing(null)}>{step<2?'Next details':member.kind==='other'?'Add household member':'Save income details'}</Button></div>
  </div>}
  </div>;
}

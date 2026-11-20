"""Offline, synthetic branch counts; no database, model, files from users, or API calls."""
import sys, json
from pathlib import Path
from datetime import date
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from app.intake.schema import SCREENS
from app.intake.logic import answer_context, visible, clean_answers, validate_answers
QUESTIONS = {q['field_id']: q for s in SCREENS for q in s['questions']}
def member(kind, rel, source, amount, employed='Retired'):
 return dict(kind=kind, relationship=rel, age=75 if kind=='recipient' else 45, lives_with_recipient=True, tax_link='Neither', employment_status=employed, gross_monthly_income=amount, income_sources=[source], income_other='', income_varies='No')
base = {'caregiver.us_citizen':True,'recipient.us_citizen':True,'caregiver.date_of_birth':'1981-01-01','recipient.date_of_birth':'1951-01-01','caregiver.coresidence':'Yes','caregiver.relationship':'Parent','recipient.marital_status':'No','recipient.tax_filing_status':'No','caregiver.claims_recipient':False,'recipient.claimed_as_dependent':'No','recipient.condition_categories':['Age-related frailty'],'recipient.adl_needs':['None of these'],'recipient.recognizes_danger':'No','recipient.planned_nursing_home':'No','caregiver.employment_status':'Retired','caregiver.payment_status':'No','caregiver.caregiving_employment_impact':['No change'],'recipient.assets':['None'],'tax.year':2025,'tax.filing_status':'Single','tax.paid_care_to_work':'No','tax.unreimbursed_medical_expenses':'No','recipient.medicaid_covered':False,'recipient.coverage_and_benefits':['Medicare','Social Security retirement or survivor benefits'],'recipient.medicare_parts':['Part A (hospital)','Part B (medical)'],'recipient.military_status':'None of these','case.has_applied_or_received':'No','case.goals':['Understand benefits we already have'],'household.members':[member('recipient','Self','Social Security retirement or survivor benefits',1500),member('caregiver','Child','Pension or retirement payments',2000)]}
def finish(seed):
 a=dict(seed)
 for _ in range(20):
  added=False
  for q in QUESTIONS.values():
   k,t=q['field_id'],q['type']
   if k in a or not q['required'] or not visible(q.get('show_when'),answer_context(a,today=date(2026,10,28))):continue
   opts=q.get('options',[])
   if q.get('allow_not_sure') or "I'm not sure" in opts: v=["I'm not sure"] if t in ['multi_select','tag_input'] else "I'm not sure"
   elif t=='boolean':v=False
   elif t=='state_dropdown':v='CA'
   elif t=='zip':v='94601'
   elif t in ['short_text','long_text']:v='Synthetic'
   elif t=='date':v='2025-01-01'
   elif t=='number':v=q.get('validation',{}).get('min',0)
   elif t=='single_select':v=opts[0]
   elif t in ['multi_select','tag_input']:v=[opts[0]]
   else: raise ValueError(k)
   a[k]=v;added=True
  if not added:break
 return validate_answers(clean_answers(a),complete=True)
# Explicit narrow document hypotheses; excludes identities, whole roster, multi-select
# coverage completeness, year choice, and every inference requiring missing records.
common={'recipient.medicare_parts','recipient.medicare_part_a_start','recipient.medicare_part_b_start','tax.filing_status','tax.adjusted_gross_income'}
scenarios={
 'A_retired_single_medicare':(base,common,'Current Medicare card + SSA/pension letters; complete filed 2025 Form 1040 of caregiver. No care invoices, wages, or VA documents.'),
 'B_employed_leave_married_veteran':({**base,'case.goals':['Get paid for caregiving','Get financial support or tax savings'],'caregiver.employment_status':'Employed full time','caregiver.employer_type':'Private company or nonprofit','caregiver.caregiving_employment_impact':['Taking leave'],'recipient.marital_status':'Yes','recipient.tax_filing_status':'Yes, jointly with a spouse','recipient.claims_dependents':'No','recipient.military_status':'Veteran','recipient.va_contact':'Yes','recipient.va_health_enrolled':'Yes','recipient.va_rating_assigned':'Yes','recipient.va_rating':'70% or higher','recipient.va_pension_status':'VA pension only','recipient.va_pension_interest':'Yes','recipient.assets':['Savings or investments','Retirement accounts'],'recipient.spouse.assets':['Savings or investments'],'tax.filing_status':'Married filing jointly','tax.paid_care_to_work':'Yes','tax.unreimbursed_medical_expenses':'Yes','household.members':[member('recipient','Self','VA benefits',1500),member('spouse','Spouse or partner','Pension or retirement payments',1000),member('caregiver','Child','Wages',4000,'Employed full time')]},common|{'caregiver.sdi_deductions','caregiver.leave_start','recipient.va_rating_assigned','recipient.va_rating','recipient.military_discharge_status','recipient.va_pension_status'},'A bundle plus dated pay statements, leave designation, and VA benefit/service summary expressly giving rating, discharge and pension type; no assumed complete expense ledger or bank accounts.'),
 'C_paid_caregiver_younger_recipient':({**base,'recipient.date_of_birth':'1991-01-01','case.goals':['Get paid for caregiving','Get financial support or tax savings'],'caregiver.employment_status':'Employed part time','caregiver.payment_status':'Yes, through Medicaid, a waiver, IHSS, or another public program','recipient.medicaid_covered':True,'recipient.coverage_and_benefits':['Medicaid','SSI'],'recipient.medicare_parts':['Neither'],'recipient.condition_categories':['Physical disability or mobility limitation'],'household.members':[member('recipient','Self','SSI',1000),member('caregiver','Child','Wages',2000,'Employed part time')]}, {'tax.filing_status','tax.adjusted_gross_income','tax.public_payment_program','tax.caregiver_earned_income'},'Caregiver complete filed 2025 Form 1040, W-2, public-program payment statement; recipient current SSI letter and Medi-Cal notice. No Medicare or leave documents.')}
result={'as_of':'2026-10-28','catalog_count':len(QUESTIONS),'unit':'top-level question records; roster subfields and intro cards excluded','scenarios':{}}
for name,(seed,candidates,bundle) in scenarios.items():
 a=finish(seed); ctx=answer_context(a,today=date(2026,10,28))
 shown=[q['field_id'] for q in QUESTIONS.values() if visible(q.get('show_when'),ctx)]
 eligible=sorted(set(shown)&candidates)
 result['scenarios'][name]={'document_assumptions':bundle,'answers':a,'visible_fields':shown,'visible_count':len(shown),'sections':{s['id']:sum(q['field_id'] in shown for q in s['questions']) for s in SCREENS},'narrow_document_candidate_fields':eligible,'candidate_count':len(eligible),'candidate_percent':round(100*len(eligible)/len(shown),1),'partial_help':['household.members','recipient.coverage_and_benefits']}
p=Path(__file__).with_name('coverage-scenarios.json');p.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:{x:v[x] for x in ['visible_count','candidate_count','candidate_percent','sections','narrow_document_candidate_fields']} for k,v in result['scenarios'].items()},indent=2))

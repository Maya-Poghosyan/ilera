"""Structured, reported household finances; not a program eligibility unit."""
from math import isfinite

UNKNOWN = "I'm not sure"
RELATIONSHIPS = {"Self", "Spouse or partner", "Child", "Parent", "Sibling", "Other relative", "Grandparent", "Grandchild", "Parent-in-law", "Child-in-law", "Friend or neighbor", "Unrelated person", "Other"}
TAX_LINKS = {"They are claimed by the recipient", "They claim the recipient", "Neither", "Another tax relationship", UNKNOWN}
EMPLOYMENT = {"Employed full time", "Employed part time", "Self-employed", "Not working", "Retired", "Student", "Other", UNKNOWN}
INCOME_SOURCES = {"Wages", "Self-employment", "Social Security retirement or survivor benefits", "SSDI", "SSI", "Pension or retirement payments", "VA benefits", "Interest, investments or rental income", "Other income", "No income", UNKNOWN}
KEYS = {"kind", "relationship", "age", "lives_with_recipient", "tax_link", "employment_status", "gross_monthly_income", "income_sources", "income_other", "income_varies"}


def valid_members(value, answers):
    if not isinstance(value, list) or not 1 <= len(value) <= 30:
        return False
    kinds = [m.get("kind") for m in value if isinstance(m, dict)]
    if kinds.count("recipient") != 1 or kinds.count("spouse") > 1 or kinds.count("caregiver") > 1:
        return False
    married = answers.get("recipient.marital_status") == "Yes"
    if ("spouse" in kinds) != married:
        return False
    cg_spouse = married and answers.get("caregiver.relationship") == "Spouse or domestic partner"
    if ("caregiver" in kinds) != (not cg_spouse):
        return False
    for m in value:
        if not isinstance(m, dict) or set(m) != KEYS or not isinstance(m["kind"], str) or m["kind"] not in {"recipient", "spouse", "caregiver", "other"}:
            return False
        if not isinstance(m["relationship"], str) or m["relationship"] not in RELATIONSHIPS:
            return False
        if m["kind"] == "recipient" and (m["relationship"] != "Self" or m["lives_with_recipient"] is not True):
            return False
        if m["kind"] == "spouse" and m["relationship"] != "Spouse or partner":
            return False
        if m["kind"] == "other" and m["relationship"] in {"Self", "Spouse or partner"}:
            return False
        if not isinstance(m["tax_link"], str) or m["tax_link"] not in TAX_LINKS or not isinstance(m["employment_status"], str) or m["employment_status"] not in EMPLOYMENT:
            return False
        if not isinstance(m["income_sources"], list) or not m["income_sources"] or any(not isinstance(x, str) or x not in INCOME_SOURCES for x in m["income_sources"]):
            return False
        src=m["income_sources"]
        if len(src) != len(set(src)) or len(src)>1 and any(x in src for x in [UNKNOWN,"No income"]):
            return False
        def number(v, maximum, integer=False):
            return v == UNKNOWN or type(v) in (int,float) and isfinite(v) and 0<=v<=maximum and (not integer or v==int(v))
        if not number(m["age"],120,True) or not number(m["gross_monthly_income"],1000000000):
            return False
        if type(m["lives_with_recipient"]) is not bool and m["lives_with_recipient"] != UNKNOWN:
            return False
        if not isinstance(m["income_varies"],str) or m["income_varies"] not in {"Yes","No",UNKNOWN} or not isinstance(m["income_other"],str):
            return False
        if "Other income" in src and not m["income_other"].strip():
            return False
        if "No income" in src and (m["gross_monthly_income"] != 0 or m["income_varies"] != "No"):
            return False
    return True


def details(answers):
    members=answers.get("household.members")
    if not isinstance(members,list):return {}
    data={}
    for m in members:
        if not isinstance(m,dict):continue
        kind=m.get("kind")
        prefix={"recipient":"recipient","spouse":"recipient.spouse","caregiver":"caregiver"}.get(kind) if isinstance(kind,str) else None
        if not prefix:continue
        for key in ["income_sources","gross_monthly_income","income_varies","employment_status"]:
            data[prefix+'.'+key]=m.get(key)
        src=m.get("income_sources")
        data[prefix+'.has_income']=False if src==["No income"] else True if isinstance(src,list) and src and UNKNOWN not in src else None
    if answers.get("recipient.marital_status")=="Yes" and answers.get("caregiver.relationship")=="Spouse or domestic partner" and 'recipient.spouse.has_income' in data:
        for suffix in ['income_sources','gross_monthly_income','income_varies','employment_status','has_income']:
            data['caregiver.'+suffix]=data.get('recipient.spouse.'+suffix)
    complete=valid_members(members,answers)
    if complete:
        resident=[m for m in members if m['lives_with_recipient'] is True]
        known=all(type(m['lives_with_recipient']) is bool for m in members) and all(type(m['gross_monthly_income']) in (int,float) and m['income_sources'] != [UNKNOWN] for m in resident)
        data['household.reported_income_monthly']=sum(m['gross_monthly_income'] for m in resident) if known else None
        data['recipient.household_size']=len(resident) if all(type(m['lives_with_recipient']) is bool for m in members) else None
    return data

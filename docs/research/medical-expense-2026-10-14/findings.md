# Unreimbursed medical-expense amount — October 14, 2026

A direct six-program specialist request was attempted using the question in
question.txt. The hosted research request failed; no fresh specialist answer is
claimed. Findings below use code inspection and official web sources.

- `tax.medical_expense_amount` asks about the caregiver's unreimbursed payments for
  the recipient in the reviewed tax year. It is passed in raw profile.answers to
  specialists. No dedicated deterministic eligibility formula referencing that
  field was found in the current eligibility checks.
- The amount is material to preliminary medical-expense tax-deduction screening,
  not a universal benefits criterion. IRS Topic 502 requires itemizing, qualifying
  paid unreimbursed expenses, applicable relationships and expenses above 7.5%
  of adjusted gross income. The intake amount alone cannot establish the actual
  deduction or whether itemizing is advantageous.
- VA pension uses deductible medical expenses in income/net-worth and payment
  calculations. That is a separate program-specific question with different
  persons/time periods; the caregiver tax-year amount cannot simply substitute.
- Some Medi-Cal share-of-cost pathways use incurred medical expenses, potentially
  including old unpaid bills. A caregiver's tax-year paid total is not an adequate
  standalone measure for those monthly/program-specific calculations.

Recommendation: retain a conditional amount when screening medical tax deductions;
keep VA-specific details separate, and request monthly/incurred bills only if a
relevant Medi-Cal pathway is identified. Do not require everyone to retrieve a
precise yearly total for unrelated program eligibility. No intake changes made.

Sources:
- https://www.irs.gov/taxtopics/tc502
- https://www.va.gov/pension/veterans-pension-rates/
- https://www.va.gov/resources/va-health-care-income-limits/
- https://www.dhcs.ca.gov/th/wp-content/uploads/2025/10/I-23-61.pdf

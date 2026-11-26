// What each document programs ask for is, where to get it, and what it fills in.
// Links point to official pages only.

export interface DocumentGuide {
  id: string;
  title: string;
  what: string[];
  where: string[];
  /** What an upload of this document fills in on the application. */
  fills?: string;
  example?: { label: string; url: string };
  /** Words in a program's own document names that mean this document. */
  keywords: string[];
}

export const DOCUMENT_GUIDES: Record<string, DocumentGuide> = {
  photo_id: {
    id: "photo_id",
    title: "Photo ID",
    what: ["A driver's license, state ID card or passport", "Shows legal name, date of birth and home address"],
    where: ["In your wallet, or the wallet of the person you care for", "A replacement or first ID comes from the DMV"],
    fills: "Names, dates of birth and addresses",
    example: { label: "California DMV ID cards", url: "https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/identification-id-cards/" },
    keywords: ["photo id", "identification", "driver", "license", "passport", "proof of identity", "id card"],
  },
  social_security_card: {
    id: "social_security_card",
    title: "Social Security card",
    what: ["The card with a 9-digit Social Security number", "Most applications ask for the number of the person applying"],
    where: ["Kept with important papers at home", "A replacement comes from Social Security, online or at an office"],
    fills: "Social Security numbers",
    example: { label: "my Social Security account", url: "https://www.ssa.gov/myaccount/" },
    keywords: ["social security card", "social security number", "ssn"],
  },
  medi_cal_card: {
    id: "medi_cal_card",
    title: "Medi-Cal card (Benefits Identification Card)",
    what: ["The plastic card the state mails to everyone with Medi-Cal", "Shows the Medi-Cal ID number and date of issue"],
    where: ["Kept with the person's wallet or medical papers", "A replacement comes from the county social services office"],
    fills: "Medi-Cal ID number, name and date of birth",
    keywords: ["medi-cal card", "benefits identification", "bic", "medi-cal id", "proof of medi-cal"],
  },
  medicare_card: {
    id: "medicare_card",
    title: "Medicare card",
    what: ["The red, white and blue card for Medicare", "Shows the Medicare number and Part A and Part B start dates"],
    where: ["Kept with the person's wallet or medical papers", "A replacement can be printed from a Medicare.gov account"],
    fills: "Medicare number and coverage dates",
    example: { label: "Your Medicare card (Medicare.gov)", url: "https://www.medicare.gov/basics/get-started-with-medicare/using-medicare/your-medicare-card" },
    keywords: ["medicare card", "medicare number"],
  },
  benefit_letter: {
    id: "benefit_letter",
    title: "Social Security benefit letter",
    what: ["A letter showing monthly SSI, SSDI or retirement payments", "Also called an award letter or benefit verification letter"],
    where: ["Mailed by Social Security each year", "Download any time from a my Social Security account"],
    fills: "Benefit types and monthly amounts",
    example: { label: "my Social Security account", url: "https://www.ssa.gov/myaccount/" },
    keywords: ["benefit letter", "award letter", "benefit verification", "ssi", "ssdi", "social security income", "proof of benefits"],
  },
  pay_stubs: {
    id: "pay_stubs",
    title: "Recent pay stubs",
    what: ["Pay statements from the last month or two", "Show gross pay, hours and deductions"],
    where: ["Given by the employer with each paycheck", "Often downloadable from the employer's payroll site"],
    fills: "Employer and monthly income",
    keywords: ["pay stub", "paystub", "earnings", "wage", "proof of income", "income verification", "employment"],
  },
  tax_return: {
    id: "tax_return",
    title: "Tax return or W-2",
    what: ["Last year's Form 1040 tax return, or the W-2 from an employer", "Shows yearly income and household filing status"],
    where: ["Kept with tax papers, or from whoever prepared the taxes", "Past returns can be downloaded from an IRS online account"],
    fills: "Yearly income and filing status",
    example: { label: "About Form 1040 (IRS)", url: "https://www.irs.gov/forms-pubs/about-form-1040" },
    keywords: ["tax return", "1040", "w-2", "w2", "tax"],
  },
  bank_statements: {
    id: "bank_statements",
    title: "Bank statements",
    what: ["Monthly statements for checking and savings accounts", "Some programs count savings and other assets"],
    where: ["Mailed by the bank, or downloaded from online banking"],
    fills: "Account balances",
    keywords: ["bank", "asset", "savings", "account statement", "resources"],
  },
  health_insurance_card: {
    id: "health_insurance_card",
    title: "Other health insurance card",
    what: ["A card for private, employer or Medicare Advantage coverage", "Shows the plan name and member ID"],
    where: ["Kept with the person's wallet or medical papers"],
    fills: "Plan name and member ID",
    keywords: ["insurance card", "other health insurance", "private insurance", "health plan"],
  },
  proof_of_address: {
    id: "proof_of_address",
    title: "Proof of address",
    what: ["A recent utility bill, lease or bank statement with the home address"],
    where: ["Mailed bills, or downloaded from the utility's website"],
    fills: "Home address",
    keywords: ["proof of address", "residency", "utility bill", "lease", "rental agreement", "proof of residence"],
  },
  citizenship: {
    id: "citizenship",
    title: "Proof of citizenship or immigration status",
    what: ["A U.S. birth certificate or passport, or a green card or other immigration document"],
    where: ["Kept with important papers at home", "Birth certificates come from the county where the person was born"],
    fills: "Citizenship or immigration status",
    example: { label: "Green card (USCIS)", url: "https://www.uscis.gov/green-card" },
    keywords: ["citizenship", "immigration", "birth certificate", "green card", "residency status"],
  },
  ihss_health_certification: {
    id: "ihss_health_certification",
    title: "IHSS Health Care Certification (form SOC 873)",
    what: [
      "A form a doctor, nurse practitioner or other licensed provider fills out",
      "Confirms the person needs help with daily activities like bathing, dressing or eating to stay safely at home",
      "IHSS can't approve services without it",
    ],
    where: [
      "The county IHSS office mails it after you apply, or print it from the link",
      "Take it to the person's doctor to complete and sign",
      "Return it to the county, usually within 45 days",
    ],
    example: { label: "SOC 873 form (CDSS)", url: "https://www.cdss.ca.gov/cdssweb/entres/forms/English/SOC873.pdf" },
    keywords: ["soc 873", "health care certification", "clinician", "medical statement", "adl", "physician", "doctor's statement", "provider statement", "medical certification of need"],
  },
  pfl_medical_certification: {
    id: "pfl_medical_certification",
    title: "Doctor's certification for family leave",
    what: [
      "A statement from the care recipient's doctor that they have a serious health condition and need care",
      "For Paid Family Leave it's part B of form DE 2501F",
    ],
    where: ["Give the form to the care recipient's doctor to complete", "Your employer or EDD can also send it"],
    example: { label: "Form DE 2501F (EDD)", url: "https://www.edd.ca.gov/pdf_pub_ctr/de2501f.pdf" },
    keywords: ["de 2501", "medical certification", "certification of health care provider", "serious health condition"],
  },
  dd214: {
    id: "dd214",
    title: "Military discharge papers (DD-214)",
    what: ["The Certificate of Release or Discharge from Active Duty", "Shows service dates and type of discharge"],
    where: ["Kept with the veteran's important papers", "Copies can be requested from the National Archives"],
    fills: "Service dates and branch",
    example: { label: "Request military records (National Archives)", url: "https://www.archives.gov/veterans/military-service-records" },
    keywords: ["dd-214", "dd214", "discharge", "military service", "service record"],
  },
  va_rating_letter: {
    id: "va_rating_letter",
    title: "VA disability rating letter",
    what: ["A VA letter showing the veteran's service-connected disability rating"],
    where: ["Mailed by the VA, or downloaded from VA.gov"],
    fills: "Disability rating and VA file details",
    example: { label: "Download VA benefit letters (VA.gov)", url: "https://www.va.gov/records/download-va-letters/" },
    keywords: ["va rating", "disability rating", "va letter", "service-connected", "va benefit"],
  },
};

/** Documents worth uploading on each program's application: the ones holding its answers. */
const AUTOFILL_DOCUMENTS: Record<string, string[]> = {
  IHSS: ["photo_id", "medi_cal_card", "social_security_card", "medicare_card", "benefit_letter"],
  "Medi-Cal": ["photo_id", "social_security_card", "pay_stubs", "benefit_letter", "tax_return", "medicare_card", "health_insurance_card", "bank_statements"],
  "VA Caregiver Support": ["photo_id", "dd214", "va_rating_letter"],
  CHAMPVA: ["photo_id", "dd214", "va_rating_letter", "medicare_card", "health_insurance_card"],
  "CFRA / FMLA": ["photo_id"],
  "IHSS Provider": ["photo_id", "social_security_card"],
};

export function autofillDocuments(program: string): DocumentGuide[] {
  return (AUTOFILL_DOCUMENTS[program] ?? ["photo_id"]).map((id) => DOCUMENT_GUIDES[id]);
}

/** The guide for a program's own name for a document, when one matches. */
export function guideFor(name: string, program: string): DocumentGuide | undefined {
  const text = name.toLowerCase();
  // Whole words (or their plurals) only, so "ssi" doesn't match "assistance".
  const has = (k: string) => new RegExp(`(^|[^a-z0-9])${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}s?([^a-z0-9]|$)`).test(text);
  // The same "medical certification" means a different form for IHSS than for family leave.
  const preferred = program.startsWith("IHSS") ? "ihss_health_certification" : "pfl_medical_certification";
  const matches = Object.values(DOCUMENT_GUIDES).filter((g) => g.keywords.some(has));
  return matches.find((g) => g.id === preferred) ?? matches[0];
}

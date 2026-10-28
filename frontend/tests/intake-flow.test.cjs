/* eslint-disable @typescript-eslint/no-require-imports -- Node harness loads transpiled CommonJS modules. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { execFileSync } = require('node:child_process');
const ts = require('typescript');
const root = path.resolve(__dirname, '../..');
function load(name, dependencies = {}) {
  const filename = path.join(root, 'frontend/src/lib', name + '.ts');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = new Module(filename);
  mod.require = (id) => dependencies[id] ?? require(id);
  mod._compile(compiled, filename);
  return mod.exports;
}
const household = load('household-data');
const logic = load('intake-schema', { './household-data': household });
const flow = load('intake-flow', { './intake-schema': logic });
const schema = JSON.parse(execFileSync(path.join(root, 'backend/.venv/bin/python'), ['-c', 'import json; from app.intake.schema import build_schema; print(json.dumps(build_schema()))'], { cwd: path.join(root, 'backend'), env: { ...process.env, PYTHONPATH: path.join(root, 'backend') }, encoding: 'utf8' }));
const question = (id) => schema.screens.flatMap((s) => s.questions).find((q) => q.field_id === id);
const visibleIds = (answers) => flow.buildPages(schema, answers).flatMap((p) => p.questions.map((q) => q.field_id));

test('five section introductions and only the last optional question', () => {
 const pages = flow.buildPages(schema, {});
 assert.equal(pages.filter(p => p.kind === 'intro').length, 5);
 assert.deepEqual(schema.screens.flatMap(s => s.questions).filter(q => !q.required).map(q => q.field_id), ['case.application_barriers']);
 const names = pages.find(p => p.questions.some(q => q.field_id === 'caregiver.first_name'));
 assert.ok(names.questions.some(q => q.field_id === 'caregiver.date_of_birth'));
 assert.ok(!names.questions.some(q => q.field_id === 'recipient.first_name'));
 assert.deepEqual(schema.screens[0].questions.map(q => q.field_id), ['caregiver.first_name', 'caregiver.last_name', 'caregiver.date_of_birth', 'caregiver.us_citizen', 'caregiver.address.street', 'caregiver.address.city', 'caregiver.address.state', 'caregiver.address.county', 'caregiver.address.zip', 'caregiver.coresidence']);
 assert.equal(schema.screens[2].questions[0].field_id, 'case.goals');
 assert.equal(schema.screens[4].questions[0].field_id, 'recipient.medicaid_covered');
 const hazardous = flow.buildPages(schema, {'recipient.recognizes_danger': 'Yes'}).find(p => p.questions.some(q => q.field_id === 'recipient.hazardous_behaviors'));
 assert.equal(hazardous.questions.length, 1);
});
test('reduced hours do not imply a leave application', () => {
 const a = { 'caregiver.caregiving_employment_impact': ['Reduced hours'] };
 assert.ok(!visibleIds(a).includes('caregiver.leave_start'));
 assert.ok(!visibleIds({ ...a, 'caregiver.check_pfl': 'Yes' }).includes('caregiver.leave_start'));
 for (const leave of ['Have taken leave', 'Taking leave', 'Expect to take leave']) assert.ok(visibleIds({ 'caregiver.caregiving_employment_impact': [leave] }).includes('caregiver.leave_start'));
 const pages = flow.buildPages(schema, { 'caregiver.caregiving_employment_impact': ['Taking leave'] });
 assert.equal(pages.find(p => p.questions.some(q => q.field_id === 'caregiver.leave_start')).questions.length, 1);
});
test('Medicaid auto selection does not reveal Medicare parts', () => {
 const a = logic.cleanAnswers(schema, { 'recipient.medicaid_covered': true });
 assert.deepEqual(a['recipient.coverage_and_benefits'], ['Medicaid']);
 assert.ok(!visibleIds(a).includes('recipient.medicare_parts'));
 assert.ok(visibleIds({ ...a, 'recipient.coverage_and_benefits': ['Medicaid', 'Medicare'] }).includes('recipient.medicare_parts'));
});
test('program changes clear statuses and dates for removed programs', () => {
 const a = logic.cleanAnswers(schema, { 'case.has_applied_or_received': 'Yes', 'recipient.programs_touched': ['IHSS'], 'recipient.program_statuses': { IHSS: 'Denied', PFL: 'Denied' }, 'case.program_dates': { IHSS: '2026-09-01', PFL: '2026-08-01' } });
 assert.deepEqual(a['recipient.program_statuses'], { IHSS: 'Denied' });
 assert.deepEqual(a['case.program_dates'], { IHSS: '2026-09-01' });
 assert.equal(logic.cleanAnswers(schema, { ...a, 'case.has_applied_or_received': 'No' })['case.program_dates'], undefined);
});
test('invalid dates are rejected', () => {
 assert.ok(logic.validateQuestions([question('recipient.date_of_birth')], { 'recipient.date_of_birth': '2026-02-30' })['recipient.date_of_birth']);
});

test('eligibility followups stay with their topics and follow their prerequisites', () => {
 const positions = new Map(schema.screens.flatMap((s, section) => s.questions.map((q, order) => [q.field_id, { section, order }])));
 assert.equal(positions.get('case.goals').section, 2);
 for (const id of ['caregiver.citizenship_residency', 'caregiver.work_authorized', 'caregiver.tax_residency', 'recipient.tax_residency']) assert.equal(positions.get(id).section, 3);
 for (const id of ['recipient.citizenship_residency', 'recipient.immigration_status_detail']) assert.equal(positions.get(id).section, 1);
 for (const id of ['recipient.lpr_since', 'recipient.five_year_us_residence']) assert.equal(positions.get(id).section, 4);
 assert.equal(positions.get('recipient.medicaid_covered').section, 4);
 assert.equal(positions.get('recipient.coverage_and_benefits').section, 4);
 assert.ok(positions.get('recipient.us_citizen').order < positions.get('recipient.citizenship_residency').order);
 const base = { 'caregiver.us_citizen': false, 'caregiver.citizenship_residency': 'Another immigration status', 'case.goals': ['Get paid for caregiving'] };
 assert.ok(visibleIds(base).includes('caregiver.work_authorized'));
 assert.ok(!visibleIds({ ...base, 'caregiver.us_citizen': true }).includes('caregiver.citizenship_residency'));
 assert.ok(!visibleIds({ ...base, 'case.goals': ['Take a break from caregiving'], 'caregiver.check_pfl': 'Yes' }).includes('caregiver.work_authorized'));
 assert.ok(!visibleIds({ ...base, 'caregiver.citizenship_residency': 'Prefer not to answer' }).includes('caregiver.work_authorized'));
});

test('recipient status and residence gates use age, coverage and the actual pathway', () => {
 const base = { 'recipient.us_citizen': false, 'recipient.date_of_birth': '1950-01-01', 'case.goals': ['Find health coverage'], 'recipient.medicaid_covered': false, 'recipient.coverage_and_benefits': ['No health coverage'], 'recipient.citizenship_residency': 'Lawful permanent resident', 'recipient.medicare_insured_work': 'No' };
 assert.ok(visibleIds(base).includes('recipient.lpr_since'));
 assert.ok(visibleIds(base).includes('recipient.five_year_us_residence'));
 assert.ok(!visibleIds({ ...base, 'recipient.medicare_insured_work': 'Yes' }).includes('recipient.five_year_us_residence'));
 assert.ok(!visibleIds({ ...base, 'recipient.coverage_and_benefits': ['Medicare'] }).includes('recipient.five_year_us_residence'));
 assert.ok(visibleIds({ ...base, 'recipient.date_of_birth': '2015-01-01' }).includes('recipient.citizenship_residency'));
 assert.ok(visibleIds({ ...base, 'recipient.citizenship_residency': 'Another immigration status' }).includes('recipient.immigration_status_detail'));
 assert.ok(!visibleIds({ ...base, 'recipient.citizenship_residency': 'Prefer not to answer' }).includes('recipient.pregnancy_postpartum'));
 for (const citizen of [true, "I'm not sure", 'Prefer not to answer']) assert.ok(!visibleIds({ ...base, 'recipient.us_citizen': citizen }).includes('recipient.citizenship_residency'));
 const tax = { ...base, 'case.goals': ['Get financial support or tax savings'] };
 assert.ok(visibleIds(tax).includes('recipient.tax_residency'));
 assert.ok(visibleIds(tax).includes('recipient.citizenship_residency')); // Financial support now includes income-benefit pathways.
});

test('sensitive branch cleanup and uncertainty match the server', () => {
 const base = { 'caregiver.us_citizen': false, 'caregiver.citizenship_residency': 'Another immigration status', 'caregiver.work_authorized': 'No', 'recipient.us_citizen': false, 'recipient.date_of_birth': '1950-01-01', 'case.goals': ['Get paid for caregiving', 'Find health coverage'], 'recipient.medicaid_covered': false, 'recipient.coverage_and_benefits': ['No health coverage'], 'recipient.citizenship_residency': 'Lawful permanent resident', 'recipient.medicare_insured_work': 'No', 'recipient.lpr_since': "I'm not sure", 'recipient.five_year_us_residence': 'Prefer not to answer' };
 const changed = logic.cleanAnswers(schema, { ...base, 'caregiver.us_citizen': true, 'recipient.us_citizen': true });
 for (const id of ['caregiver.citizenship_residency', 'caregiver.work_authorized', 'recipient.citizenship_residency', 'recipient.lpr_since', 'recipient.five_year_us_residence']) assert.equal(changed[id], undefined);
 const ids = ['caregiver.us_citizen', 'recipient.us_citizen', 'recipient.lpr_since'];
 const unknown = Object.fromEntries(ids.map(id => [id, 'Prefer not to answer']));
 const declineErrors = logic.validateQuestions(ids.map(question), unknown);
 assert.ok(declineErrors['caregiver.us_citizen']);
 assert.ok(declineErrors['recipient.us_citizen']);
 assert.equal(declineErrors['recipient.lpr_since'], undefined);
 const uncertaintyErrors = logic.validateQuestions(ids.map(question), Object.fromEntries(ids.map(id => [id, "I'm not sure"])));
 assert.ok(uncertaintyErrors['caregiver.us_citizen']);
 assert.ok(uncertaintyErrors['recipient.us_citizen']);
 assert.equal(uncertaintyErrors['recipient.lpr_since'], undefined);
 const future = new Date(); future.setFullYear(future.getFullYear() + 1);
 assert.ok(logic.validateQuestions([question('recipient.lpr_since')], { 'recipient.lpr_since': future.toISOString().slice(0, 10) })['recipient.lpr_since']);
});

test('old goal selections merge without losing intent', () => {
 const a = logic.cleanAnswers(schema, { 'case.goals': ['Help paying for care', 'In-home assistance', 'Finding VA caregiver benefits', 'Medical coverage'] });
 assert.deepEqual(a['case.goals'], ['Get help providing or paying for care', 'Find health coverage']);
 assert.equal(question('case.goals').options.length, 7);
});
test('resume uses last completed page and ignores partial later pages', () => {
 const pages = [
  {key:'section:a',kind:'intro',questions:[]},
  {key:'caregiver.first_name',kind:'questions',questions:[question('caregiver.first_name')]},
  {key:'caregiver.address.street',kind:'questions',questions:[question('caregiver.address.street'),question('caregiver.address.city')]},
 ];
 assert.equal(flow.lastCompletedPage(pages, {'caregiver.first_name':'Test','caregiver.address.street':'1 Test St'}), 'caregiver.first_name');
 assert.equal(flow.lastCompletedPage(pages, {'caregiver.first_name':'Test','caregiver.address.street':'1 Test St','caregiver.address.city':'Oakland'}), 'caregiver.address.street');
});

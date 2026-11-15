# Live research check — November 15, 2026

**Connectivity and compact output verified: 6/6 specialists.** The focused run took
15.72 seconds total, with three concurrent requests. Each specialist retrieved four
hosted policy passages and returned a validated answer under 150 words.

| Specialist | Answer words |
| --- | ---: |
| IHSS | 73 |
| Medi-Cal | 72 |
| Paid Family Leave | 94 |
| VA | 68 |
| Medicare | 65 |
| Tax | 48 |

See `focused-live-run.json` for exact answers and document/page references. References
were checked against retrieved pairs. This verifies reference validity, not claim
entailment or current policy. Content review still found tangential findings (notably
VA's historical payment rates), and corpus effective dates remain unverified. These
outputs are research leads, not approved current eligibility advice.

The first live attempt exceeded the word budget and was correctly rejected. Tightening
the target to 90–110 words, with per-field guidance, produced six compact answers
(`initial-live-run.json`, 58–76 words, 10.51 seconds). That run confused policy manuals
with caregiver-held records. The final prompt distinguishes the two, prioritizes
self-report, and keeps verification/filing tasks out of preliminary screening.
Focused queries produced the final run above. A citation retry failure also led to
passing an explicit list of allowed document/page pairs and including it in retry
feedback. A failure now waits for sibling requests before shared resources close.

## Connection used

PostgreSQL public access remains disabled. An IP firewall allowance alone cannot
enable laptop access. Used the existing `ilera-api-prod-eastus2` container inside
the VNet, confirmed `SELECT 1`, and ran local research sources in a separate Python
process. No deployment, restart, firewall change, resource provisioning, case creation
or personal-document processing occurred. The running API process was not changed.

Verified model destination: `ilera-resource.openai.azure.com`, deployment `gpt-5-mini`;
Azure inventory confirms the existing `ilera-resource` account. The 3,429 indexed
chunks have source URLs on official government domains: ACL, VA, EDD, CDSS, CMS,
DHCS, IRS and Medicare. No credentials were printed or copied into these artifacts.

The test copies of local modules were loaded only into the probe process; this is
**not a production deployment of the new contracts**. Future research should execute
inside the VNet until a private laptop route exists. Do not reopen the database to
public networking to accommodate a changed laptop IP.

Automatic approval review initially rejected the run because model destination and
corpus trust were unverified. Read-only checks established resource ownership and
public source domains; retry of the same operation then succeeded.

Offline backend verification: 351 passed, 1 skipped. Final focused contract/SDK
checks: 24 passed. Live latency is one run, not a before/after performance benchmark.

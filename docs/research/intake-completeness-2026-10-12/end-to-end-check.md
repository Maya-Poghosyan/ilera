# Intake browser check

Synthetic data only. Local Next preview and actual FastAPI intake endpoints; database,
Azure orchestration credentials/URL and outbound email disabled. The test origin was
localhost:3019, separate from the user's 127.0.0.1:3019 draft storage.

Verified through visible browser controls:
- Shared address removes redundant address entry.
- Conditional work/PFL details appear for reduced hours.
- Household member editor advances through two prompts per step, stores relationships,
  age, residence and tax connections, and avoids repeating spouse income.
- Recipient/spouse income and selected asset details appear within their topics.
- Medicare parts reveal coverage dates.
- VA contact/rating sequence and distinct pension branch appear.
- Tax questions reach the final submission screen.
- Actual intake submission saved 107 answers and navigated to the results route.

Checked the saved case via the local API: recipient monthly income 1000, spouse 1500,
A/B parts, VA rating bucket and structured spouse member were retained. Explicit
uncertainty remained uncertainty. Aggregate household numeric income remained unknown;
no midpoint or universal eligibility unit was fabricated.

The results page reported processing unavailable because Azure was disabled. Live
eligibility decisions, production persistence and every combination of branches were
not exercised. A temporary component preview was used for the household controls and
removed after inspection. The final topic ordering was reviewed for forward-only
cross-topic dependencies and the resulting answer payload was replayed through the API.

Found and fixed: the condition-tag dropdown could obstruct Next. It now closes on
selection/blur. Also moved VA financial details to their appropriate topics, after the
lead-ins they depend on.

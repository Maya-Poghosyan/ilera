# Azure email scanning implementation

Target: Microsoft 365 first, Gmail second, with both feeding the same Azure pipeline:
OAuth → provider notification → Ilera ingest API → Service Bus → scan worker → Azure OpenAI → suggested events → Care Calendar.

## Infrastructure sequencing

- [x] Confirm the existing Azure API, frontend, Container Apps environment, and Postgres can be reused.
- [x] Keep mailbox OAuth identity separate from the deployment identity; use one API runtime identity for vault access.
- [x] Schedule Service Bus provisioning with notifications and the worker, rather than with OAuth setup.
- [x] Complete the OAuth infrastructure checklist in [Azure setup](azure-email-setup.md).

Service Bus is still required by the planned scanning architecture. The worker will be a
separate background process; mailbox routes and notification ingress belong in the existing API.

**Rollout status (2026-09-16):** the scanning pipeline is APPLIED and ENABLED on
`ilera-subscription`. Service Bus `ilera-email-bus`/`email.scan`, the scan worker container
app, the hourly maintenance job `ilera-email-maint`, and all RBAC are provisioned via Terraform
(`email-scanning.tfstate`). The Entra client secret and Fernet key are in Key Vault. Following
BAA / abuse-monitoring opt-out confirmation for the `ilera-resource` Azure OpenAI account,
`EMAIL_CONNECTIONS_ENABLED=true` and `EMAIL_SCANNING_ENABLED=true` are set on the API, worker,
and maintenance job. The maintenance job runs clean (`checked=0 failed=0` with no mailboxes
connected). Remaining: interactive live end-to-end — connect a real M365 mailbox in the
browser, send a test email, and confirm a suggestion reaches the Care Calendar. See
[infrastructure status](email-infra-status.md).

## 1. Shared contracts and ownership — implemented, runtime validation pending

- [x] Define provider interface for authorization, code exchange, token refresh, subscription lifecycle, message retrieval, and revocation.
- [x] Define mailbox metadata, identifier-only queue payloads, transient email input, and minimal scan-result ledger.
- [x] Add Postgres tables for connections and results; require durable storage for ingestion.
- [x] Add owner, case, provenance, confidence, extraction version, and review status to suggestions.
- [x] Require authentication and ownership for suggestion listing/deletion.
- [ ] Validate database changes and ownership behavior when test runs resume.

Completion criterion: another account cannot read or delete a suggestion; queue payloads reject extra fields; raw email and OAuth credentials have no fields in persistent models.

Legacy suggestions without an owner stay in storage but are hidden by the API. Do not infer ownership from the old global demo case. Any backfill needs verified ownership.

## 2. Microsoft 365 OAuth and credential lifecycle — implemented, cloud validation pending

- [ ] Register an Entra application with exact callback URLs and delegated Mail.Read plus offline_access; restrict initial rollout to one approved organizational tenant.
- [x] Implement authenticated connect initiation bound to a user and an owned case. Require explicit ownership, including for formerly anonymous cases.
- [x] Generate expiring, single-use server-side OAuth state and PKCE; atomically consume state on callback. Validate tenant/account identity and granted scopes before connecting.
- [x] Store tokens encrypted server-side using Key Vault/managed identity; never expose token material in connection API responses or logs.
- [x] Implement the Microsoft adapter and token refresh with rotation/concurrency handling.
- [x] Implement connection listing, disconnect, subscription deletion, credential deletion, and reconnect states.
- [x] Ensure old inbox-monitoring preferences never count as new OAuth consent.

Completion criterion: an approved Microsoft 365 mailbox can connect, refresh, and disconnect; no cross-account callback or replay succeeds. Outlook.com consumer support requires a separate account-policy decision.

## 3. Notifications and Service Bus — ingress, subscription maintenance, and reconciliation implemented

- [x] Add Service Bus publisher using managed identity by default and deterministic broker message IDs.
- [x] Keep email ingestion disabled by default; do not silently drop jobs when configuration is missing.
- [x] Create Graph message subscriptions with immutable IDs, validation challenge handling, and an unguessable clientState (only its hash is stored).
- [x] Validate each notification against a stored active subscription and owner before enqueueing message IDs. Do not fetch email in the webhook.
- [x] Handle batched notifications, queue failures, provider retries, and subscription lifecycle notifications. Lifecycle recovery needs are persisted; replay/reconciliation remains pending.
- [x] Renew subscriptions before expiry and reconcile missed notifications.
- [ ] Provision Service Bus with duplicate detection, bounded delivery attempts, dead-letter queue, and scoped sender/receiver RBAC.

Completion criterion: valid notifications enqueue only identifiers; forged notifications enqueue nothing; a queue failure is retried rather than acknowledged as success. Broker deduplication does not replace worker idempotency.

Missed-notification reconciliation is implemented in `app/email_ingestion/reconciliation.py`.
When a subscription lapses (expiry, replacement, `subscriptionRemoved`/`missed` lifecycle
events, or reconnect) the connection is flagged `reconciliation_required`. `reconcile()` lists
the identifiers of messages received since the connection's `reconciled_through` cursor
(falling back to `consented_at`, with a one-second overlap for clock skew) via the new
`MicrosoftEmailProvider.list_message_ids_since` — identifiers only, never bodies/subjects/
senders, paged over `@odata.nextLink` and bounded (`max_ids`/`max_pages`). Each identifier is
enqueued as an ordinary `EmailScanJob`; the worker's deterministic message identity and single
completion ledger make re-enqueue idempotent, so a message also delivered by a live webhook is
not scanned twice. The flag is cleared and the cursor advanced to the pass start time **only**
when the whole window enqueued without error; a provider/queue failure raises, leaving the flag
set for a later run. All state changes occur under the same case advisory lock as OAuth/
disconnect/renewal, so a disconnect or reconnect that races the pass discards it. Reconciliation
runs inside the hourly `python -m app.email_ingestion.subscriptions` maintenance pass (after
subscription create/renew, so a freshly created subscription's initial gap is recovered) and is
also runnable on its own via `python -m app.email_ingestion.reconciliation`. If more mail
exists than the per-pass bound, the flag stays set and the next pass continues from the cursor.

## 4. Azure scan worker and extraction — implemented locally; live validation pending

- [x] Add a separate Container Apps worker consuming messages with peek-lock and lock renewal.
- [x] Resolve connection/owner from server storage; reject inactive connections before fetching or committing results.
- [x] Fetch sender, subject, timestamp, and text body inside the worker only; skip attachments.
- [x] Use a dedicated Azure OpenAI configuration and managed identity; never fall back to the existing general OpenAI configuration for email.
- [x] Extract structured care events with validated dates, time zones, action required, confidence, and explanation; represent ambiguous/missing dates without inventing a calendar date.
- [x] Treat email text as untrusted data, not instructions; provide no tools to the extractor.
- [x] Atomically persist suggestions and processing completion with unique message identity; handle crashes, duplicate deliveries, multiple events per email, and retries.
- [x] Acknowledge after commit; use bounded retries/dead-lettering and fixed error codes that cannot leak email text.
- [x] Keep raw email transient, use fixed errors, suppress transport logging, and store only structured suggestions. Deployment-level tracing/logging checks remain required.

Completion criterion: one email produces zero or more owned suggestions; replay creates no duplicate suggestions; a crash cannot mark an uncommitted event complete; disconnect prevents subsequent processing. The worker now writes suggestions and completion in one transaction under a per-message lock; live Postgres concurrency/crash validation remains pending.

## 5. Care Calendar review — implemented; live end-to-end verification pending

- [x] Add Outlook connection state and connect/disconnect/reconnect UI, gated by backend configuration. Live verification remains pending.
- [x] Display real suggestions with explanation, confidence, and source; support accept/dismiss and persist review state.
- [x] Add authenticated calendar-event persistence and idempotent acceptance into the user's calendar.
- [x] Replace the fixed demo month and static calendar events with date navigation and real data.
- [x] Show empty, processing, failure, and reconnect states without implying the mailbox is being scanned when it is not.

Completion criterion: a user connects Outlook, receives a suggestion, accepts it, and sees it on the correct calendar date after reload.

Review state and calendar acceptance are backed by:
`PATCH /api/suggested-events/{id}` (owner-enforced; `status` = `accepted` | `dismissed` |
`pending`), `GET /api/calendar-events`, and `DELETE /api/calendar-events/{id}`. Accepting a
suggestion materializes a `CalendarEvent` whose id is derived from the source suggestion
(`uuid5`), so re-accepting is idempotent — no duplicate calendar entries. Dismissing, resetting
to pending, or deleting the suggestion removes any calendar event previously accepted from it.
The suggested-events list returns the full owned `SuggestedEvent`, including `confidence`,
`action_required`, `status`, and `source`. A suggestion with no established date shows
"Date needs review" and cannot be accepted until a date exists; no artificial date is invented.

The Care Calendar page (`frontend/src/app/dashboard/page.tsx`) now navigates real months
(previous/next/today), renders accepted calendar events as real grid data, previews dated
pending suggestions as tentative entries, and surfaces loading, empty, and load-failure
(retry) states for the suggestions/calendar fetch. The failure copy explicitly does not imply
the mailbox failed to scan. Accept/dismiss call the review endpoint and reload.

Validation: 5 focused backend tests (`tests/test_calendar_review.py`) cover status
persistence, idempotent acceptance, dismiss-removes-calendar-event, owner isolation (404 for
a stranger reviewing or deleting), and delete-cascade. Run with the full email suite this is
94 passing on a Python 3.14 environment with mocked/in-memory stores. Frontend `tsc --noEmit`
passes and the changed files lint clean. Live end-to-end verification against Postgres and a
real connected mailbox (connect → suggestion → accept → reload) remains pending, as scanning
stays disabled until the ingestion path is validated.

## 6. Gmail and production rollout — pending

- [ ] Implement Google OAuth and read-only Gmail adapter with account-policy checks.
- [ ] Configure Gmail watch and authenticated Pub/Sub push delivery. Gmail notifications contain history IDs, not message IDs: resolve history into individual message IDs before the shared scan queue.
- [ ] Persist history cursors, handle expired cursors, renew watches, and recover gaps.
- [ ] Add Gmail connection UI using the same downstream extraction/review flow.
- [ ] Add infrastructure definitions for API, worker, Service Bus, Key Vault, Azure OpenAI, identity/RBAC, secret references, and network boundaries.
- [ ] Add operational dashboards for queue age, failures, expired subscriptions, and dead letters without logging PHI.
- [ ] Define account/tenant eligibility, retention/deletion policy, deployment rollback, and staged rollout.

Completion criterion: both providers produce suggestions through the same worker; lifecycle recovery and deletion work under production configuration.

## Current implementation boundaries

Microsoft OAuth initiation/callback, account validation, encrypted credential persistence, serialized refresh/disconnect, and a Graph adapter are implemented. The Care Calendar has connection controls, gated by EMAIL_CONNECTIONS_ENABLED and the required configuration. The callback uses the frontend session cookie and then posts to the backend; it requires the same Ilera user who initiated the flow.

Tokens are encrypted in the existing Postgres database. A versioned Fernet key and the Microsoft application secret are read from Key Vault via managed identity. No raw credentials appear in connection API responses. Old encryption-key versions must remain available until records are re-encrypted. Microsoft disconnect deletes local credentials and attempts subscription removal; it does not revoke tenant-wide sessions or remove Microsoft's consent grant. Subscription cleanup failures are reported and the local connection becomes inactive regardless.

Webhook ingress, subscription maintenance, the scan worker, and structured extraction now exist. The Care Calendar review flow (suggestion accept/dismiss with persisted status and idempotent calendar-event acceptance) is also implemented and unit-tested. Missed-message reconciliation and live end-to-end verification remain pending. OAuth infrastructure has been applied; scanning infrastructure has not (see [infrastructure status](email-infra-status.md)). No live OAuth round trip has been validated. Leave EMAIL_SCANNING_ENABLED=false until the ingestion path is ready.

The public backend endpoint is `POST /api/email/microsoft/notifications`, used for both basic and lifecycle notifications. Configure `EMAIL_MICROSOFT_NOTIFICATION_URL` to this path on the public **API** origin, not the authenticated frontend proxy. Validation challenges return plain text without accessing the database. Normal deliveries require scanning, Postgres, and Service Bus configuration. Invalid/forged notices are acknowledged without enqueueing; database/queue failures return a fixed 503 so Graph retries. Partial-batch retries use the existing deterministic queue message IDs.

Once the downstream pipeline is ready, schedule `python -m app.email_ingestion.subscriptions` from `backend/` at least hourly with the API's configuration and identity. It creates subscriptions for connected owned mailboxes, renews within one day of expiry, responds to persisted renewal requests, and — in the same pass — reconciles missed notifications for any mailbox flagged `reconciliation_required`. OAuth callbacks do not start scanning by themselves. Initial subscriptions, expired/replaced subscriptions, and missed notifications mark `reconciliation_required`; the reconciliation pass enqueues the gap's message identifiers (idempotently) and clears the flag only once the whole window is covered, advancing a `reconciled_through` cursor. Reconciliation can also be run on its own with `python -m app.email_ingestion.reconciliation`. A Graph creation that succeeds before a database commit fails can leave an orphan subscription; the maintenance pass now prunes these automatically via `prune_orphan_subscriptions`, which lists the mailbox's Graph subscriptions and deletes any that deliver to our exact notification URL but are not the connection's currently tracked subscription (re-read under the case lock). Subscriptions belonging to other integrations in the tenant (different notification URLs) and the live tracked subscription are never touched. Scheduling/deployment of this maintenance command is still pending.

Focused validation: 39 notification/subscription tests passed in a temporary Python 3.14 environment, covering challenge echo, forged notices, ownership query constraints, inactive/expired connections, disconnect races, identifier-only payloads, queue retry behavior, lifecycle flags, and subscription renewal. These use mocked database/provider boundaries; they do not establish live Postgres transaction behavior or Azure delivery. Production Python 3.12 and live integration validation remain required.

Follow-up PHI/efficiency review expands this to 47 tests: fixed email error responses,
private transport logging, redacted backend email access logs, lazy per-batch sender reuse,
duplicate-send suppression, bounded sends, and skipping credential access when renewal
is not due. See [review findings and remaining deployment checks](email-infra-status.md#local-phi-and-efficiency-review-2026-09-16).

Schema additions use the repository's existing idempotent startup DDL and apply on the next Postgres pool initialization. Existing records are not deleted.

Test environment: a Python 3.12 conda env (`ilera312`, matching production per backend/Dockerfile) with the full `backend/requirements.txt` installed runs the whole backend suite. Run with:

```sh
DATABASE_URL="" ACS_EMAIL_CONNECTION_STRING="" conda run -n ilera312 python -m pytest tests/ -q
```

Clearing `ACS_EMAIL_CONNECTION_STRING` prevents a local `.env` from routing signup-verification email to real Azure during tests. As of the reconciliation and orphan-pruning work the full suite is **216 passed** (including 16 reconciliation/orphan-pruning tests and 5 maintenance-wiring tests added here). Two stale tests were removed: the old 201 signup contract (signup now returns 202 pending email verification) and a room→case mapping test referencing a store function that no longer exists. Modules `db.py`, `forms/extract.py`, `forms/filler.py`, `rag/index.py`, and `email_ingestion/store.py` gained `from __future__ import annotations` so PEP 604 (`X | None`) annotations evaluate under the conda runtime. These use mocked database/provider/queue boundaries; they do not establish live Postgres transaction behavior or Azure delivery. Live integration validation remains required.

Earlier OAuth work: static Python parsing ran with Anaconda and frontend TypeScript/lint checks for connection components/routes passed. Production uses Python 3.12 per backend/Dockerfile.

## Implementation references

- [Microsoft Graph message retrieval](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0)
- [Azure Service Bus Python SDK and identity authentication](https://learn.microsoft.com/en-us/python/api/overview/azure/servicebus-readme?view=azure-python)

- [Microsoft OAuth authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft ID-token validation](https://learn.microsoft.com/en-us/entra/identity-platform/id-tokens)

## Worker implementation and validation (2026-09-16)

Run `python -m app.email_ingestion.worker` from `backend/`. Build the smaller standalone
image from the repository root with:

```sh
docker build -f backend/Dockerfile.email-worker -t ilera-email-worker backend
```

The worker requires `DATABASE_URL`, the mailbox OAuth/Key Vault settings, Service Bus
settings, `EMAIL_CONNECTIONS_ENABLED=true`, and `EMAIL_SCANNING_ENABLED=true` **only in
an approved validation/rollout environment**. Leave production scanning disabled. Set
`EMAIL_OPENAI_ENDPOINT` to the dedicated configuration's Azure resource origin
(`https://<resource>.openai.azure.com/`) and `EMAIL_OPENAI_DEPLOYMENT` to a deployment
supporting strict structured outputs. No general OpenAI settings or API-key fallback
are used. The model request uses managed identity, `store=false`, no tools, bounded
input/output, and no sender field. The existing account may be reused; configuration
is isolated from eligibility inference.

`EMAIL_SCAN_MAX_DELIVERIES` defaults to 5 (range 1–5, matching broker policy). The worker
receives one message at a time with no prefetch, uses peek-lock and automatic renewal,
and acknowledges only after the DB transaction exits successfully. A per-message
transaction advisory lock avoids duplicate extraction; deterministic event IDs and a
single completion ledger prevent replay from duplicating saved suggestions. Ownership,
status, and the consent timestamp are rechecked after fetch and before committing.
Disconnect/reconnect during processing discards output; Graph 401 records reconnect
state. A request already in flight cannot be recalled by disconnect.

Malformed queue payloads are discarded with a fixed outcome rather than copied into a
DLQ that could retain unexpected PHI. Valid identifier-only jobs are abandoned on
failure and dead-lettered after bounded retries with fixed error text. Operator replay
and retention policies remain pending. Failed jobs do not write a success ledger.

Graph responses are capped at 2 MB. Model input is capped at 24,000 body characters and
300 subject characters; long messages can lose relevant events beyond that window.
At most 10 events are accepted per email. Invalid dates/zones, inconsistent certainty,
DST gaps/ambiguous wall times, model refusal, and truncated/invalid responses fail
validation. Missing/ambiguous dates persist as null with `day=0`, and the existing
suggestion panel displays “Date needs review”; no artificial calendar date is inserted.
Structured event text remains sensitive derived data. Prompt minimization reduces
unnecessary details but is not a guarantee that model-generated text contains no PHI.

89 focused email tests pass on Python 3.14, including mocked transaction rollback,
replay, disconnect/reconnect races, model contract validation, and Graph request limits.
Frontend TypeScript checks pass. Terraform formatting passes; full validation could
not run because local Azure providers are not installed. The container was not built,
cloud resources were not changed, and Azure/OpenAI/live Postgres testing remains pending.
The scanning Terraform now selects the worker command, but its deployment still needs
DB credentials, OAuth settings, rollout flags, and authenticated scaler wiring reviewed.

References: [structured output contract](https://developers.openai.com/api/docs/guides/structured-outputs),
[Azure managed identity](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/managed-identity),
[Service Bus receive/lock semantics](https://learn.microsoft.com/en-us/python/api/overview/azure/servicebus-readme?view=azure-python).

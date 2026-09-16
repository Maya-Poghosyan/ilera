# Azure email scanning implementation

Target: Microsoft 365 first, Gmail second, with both feeding the same Azure pipeline:
OAuth → provider notification → Ilera ingest API → Service Bus → scan worker → Azure OpenAI → suggested events → Care Calendar.

## Infrastructure sequencing

- [x] Confirm the existing Azure API, frontend, Container Apps environment, and Postgres can be reused.
- [x] Keep mailbox OAuth identity separate from the deployment identity; use one API runtime identity for vault access.
- [x] Schedule Service Bus provisioning with notifications and the worker, rather than with OAuth setup.
- [ ] Complete the OAuth infrastructure checklist in [Azure setup](azure-email-setup.md).

Service Bus is still required by the planned scanning architecture. The worker will be a
separate background process; mailbox routes and notification ingress belong in the existing API.

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

## 3. Notifications and Service Bus — ingress and subscription maintenance implemented; recovery pending

- [x] Add Service Bus publisher using managed identity by default and deterministic broker message IDs.
- [x] Keep email ingestion disabled by default; do not silently drop jobs when configuration is missing.
- [x] Create Graph message subscriptions with immutable IDs, validation challenge handling, and an unguessable clientState (only its hash is stored).
- [x] Validate each notification against a stored active subscription and owner before enqueueing message IDs. Do not fetch email in the webhook.
- [x] Handle batched notifications, queue failures, provider retries, and subscription lifecycle notifications. Lifecycle recovery needs are persisted; replay/reconciliation remains pending.
- [ ] Renew subscriptions before expiry and reconcile missed notifications.
- [ ] Provision Service Bus with duplicate detection, bounded delivery attempts, dead-letter queue, and scoped sender/receiver RBAC.

Completion criterion: valid notifications enqueue only identifiers; forged notifications enqueue nothing; a queue failure is retried rather than acknowledged as success. Broker deduplication does not replace worker idempotency.

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

## 5. Care Calendar review — connection controls implemented; event review pending

- [x] Add Outlook connection state and connect/disconnect/reconnect UI, gated by backend configuration. Live verification remains pending.
- [ ] Display real suggestions with explanation, confidence, and source; support accept/dismiss and persist review state.
- [ ] Add authenticated calendar-event persistence and idempotent acceptance into the user's calendar.
- [ ] Replace the fixed demo month and static calendar events with date navigation and real data.
- [ ] Show empty, processing, failure, and reconnect states without implying the mailbox is being scanned when it is not.

Completion criterion: a user connects Outlook, receives a suggestion, accepts it, and sees it on the correct calendar date after reload.

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

Webhook ingress, subscription maintenance, the scan worker, and structured extraction now exist. Missed-message reconciliation and event acceptance remain pending. OAuth infrastructure has been applied; scanning infrastructure has not (see [infrastructure status](email-infra-status.md)). No live OAuth round trip has been validated. Leave EMAIL_SCANNING_ENABLED=false until the ingestion path is ready.

The public backend endpoint is `POST /api/email/microsoft/notifications`, used for both basic and lifecycle notifications. Configure `EMAIL_MICROSOFT_NOTIFICATION_URL` to this path on the public **API** origin, not the authenticated frontend proxy. Validation challenges return plain text without accessing the database. Normal deliveries require scanning, Postgres, and Service Bus configuration. Invalid/forged notices are acknowledged without enqueueing; database/queue failures return a fixed 503 so Graph retries. Partial-batch retries use the existing deterministic queue message IDs.

Once the downstream pipeline is ready, schedule `python -m app.email_ingestion.subscriptions` from `backend/` at least hourly with the API's configuration and identity. It creates subscriptions for connected owned mailboxes, renews within one day of expiry, and responds to persisted renewal requests. OAuth callbacks do not start scanning by themselves. Initial subscriptions, expired/replaced subscriptions, and missed notifications mark `reconciliation_required`; nothing clears that flag until a recovery implementation can prove the gap is covered. A Graph creation that succeeds before a database commit fails can leave an orphan subscription; automated orphan reconciliation is still required before rollout. Scheduling/deployment of this maintenance command is also pending.

Focused validation: 39 notification/subscription tests passed in a temporary Python 3.14 environment, covering challenge echo, forged notices, ownership query constraints, inactive/expired connections, disconnect races, identifier-only payloads, queue retry behavior, lifecycle flags, and subscription renewal. These use mocked database/provider boundaries; they do not establish live Postgres transaction behavior or Azure delivery. Production Python 3.12 and live integration validation remain required.

Follow-up PHI/efficiency review expands this to 47 tests: fixed email error responses,
private transport logging, redacted backend email access logs, lazy per-batch sender reuse,
duplicate-send suppression, bounded sends, and skipping credential access when renewal
is not due. See [review findings and remaining deployment checks](email-infra-status.md#local-phi-and-efficiency-review-2026-09-16).

Schema additions use the repository's existing idempotent startup DDL and apply on the next Postgres pool initialization. Existing records are not deleted. New SDK dependencies were added to requirements.txt but were not installed into the local environment.

Earlier OAuth work: static Python parsing ran with Anaconda and frontend TypeScript/lint checks for connection components/routes passed; runtime tests were skipped in that earlier session. Production uses Python 3.12 per backend/Dockerfile; the Anaconda base is Python 3.9. The newer ingress tests above ran separately using Homebrew Python 3.14.

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

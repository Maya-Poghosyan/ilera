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

## 3. Notifications and Service Bus — publisher implemented; ingress pending

- [x] Add Service Bus publisher using managed identity by default and deterministic broker message IDs.
- [x] Keep email ingestion disabled by default; do not silently drop jobs when configuration is missing.
- [ ] Create Graph message subscriptions with immutable IDs, validation challenge handling, and an unguessable clientState.
- [ ] Validate each notification against a stored active subscription and owner before enqueueing message IDs. Do not fetch email in the webhook.
- [ ] Handle batched notifications, queue failures, provider retries, and subscription lifecycle notifications.
- [ ] Renew subscriptions before expiry and reconcile missed notifications.
- [ ] Provision Service Bus with duplicate detection, bounded delivery attempts, dead-letter queue, and scoped sender/receiver RBAC.

Completion criterion: valid notifications enqueue only identifiers; forged notifications enqueue nothing; a queue failure is retried rather than acknowledged as success. Broker deduplication does not replace worker idempotency.

## 4. Azure scan worker and extraction — pending

- [ ] Add a separate Container Apps worker consuming messages with peek-lock and lock renewal.
- [ ] Resolve connection/owner from server storage; reject inactive connections before fetching or committing results.
- [ ] Fetch sender, subject, timestamp, and text body inside the worker only; skip attachments.
- [ ] Use a dedicated Azure OpenAI configuration and managed identity; never fall back to the existing general OpenAI configuration for email.
- [ ] Extract structured care events with validated dates, time zones, action required, confidence, and explanation; represent ambiguous/missing dates without inventing a calendar date.
- [ ] Treat email text as untrusted data, not instructions; provide no tools to the extractor.
- [ ] Atomically persist suggestions and processing completion with unique message identity; handle crashes, duplicate deliveries, multiple events per email, and retries.
- [ ] Acknowledge after commit; use bounded retries/dead-lettering and fixed error codes that cannot leak email text.
- [ ] Exclude raw email from logs, traces, exception payloads, queues, and permanent storage. Release transient bodies after processing.

Completion criterion: one email produces zero or more owned suggestions; replay creates no duplicate suggestions; a crash cannot mark an uncommitted event complete; disconnect prevents subsequent processing. The current result-store helper alone is not an atomic worker transaction.

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

No webhook handler, worker, extractor, or event acceptance flow exists yet. No cloud resources were provisioned and no live OAuth round trip has been validated. Leave EMAIL_SCANNING_ENABLED=false until the ingestion path is ready. See [Azure setup handoff](azure-email-setup.md) for parallel setup tasks.

Schema additions use the repository's existing idempotent startup DDL and apply on the next Postgres pool initialization. Existing records are not deleted. New SDK dependencies were added to requirements.txt but were not installed into the local environment.

Static Python parsing ran with Anaconda. Frontend TypeScript and lint checks for the new connection components/routes passed. Test runs were skipped at the user's request. Production uses Python 3.12 per backend/Dockerfile; the current Anaconda base is Python 3.9 and will need a compatible project environment before runtime validation.

## Implementation references

- [Microsoft Graph message retrieval](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0)
- [Azure Service Bus Python SDK and identity authentication](https://learn.microsoft.com/en-us/python/api/overview/azure/servicebus-readme?view=azure-python)

- [Microsoft OAuth authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft ID-token validation](https://learn.microsoft.com/en-us/entra/identity-platform/id-tokens)

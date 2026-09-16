# Azure setup for Microsoft email connections

## Implementation plan and progress

Scope: configure the existing API for Microsoft mailbox OAuth first. Service Bus remains
part of the scanning architecture; provision it with the webhook and worker milestone.

- [x] Review the OAuth implementation and existing deployment workflow.
- [x] Inspect the active Azure subscription and Ilera resource inventory.
- [x] Confirm reuse of `ilera-api`, `ilera-web`, `ilera-env`, and existing Postgres `ilera-pg`.
- [x] Keep the mailbox Entra registration separate from the GitHub deployment identity.
- [x] Defer Service Bus, the scan worker, and dedicated email Azure OpenAI configuration.
- [x] Implement repeatable setup tooling with secret-safe output and disabled rollout flags.
- [x] Run the read-only Azure preview and four offline setup safety tests.
- [ ] Create or verify the single-tenant mailbox Entra registration and Web callback.
- [ ] Create or verify Key Vault and its two secrets; preserve existing encryption keys.
- [ ] Configure one runtime identity and scoped Key Vault read access on the existing API.
- [ ] Set non-secret backend configuration while preserving existing environment settings.
- [ ] Verify vault access from the runtime identity and callback logging behavior.
- [ ] Validate connect, refresh, disconnect/reconnect, ownership isolation, and deletion.

No additional API, frontend, database, or Container Apps environment is needed. The future
worker is a separate background process, not a duplicate API. Azure Communication Services
continues to handle account-verification email independently of mailbox reading.

Implementation is isolated in `infra/azure/` and these planning documents. Preserve the
ongoing application work in the shared workspace; this setup does not edit app/providers,
app/email_ingestion, app/db.py, or frontend connection code.

Run instructions, permission requirements, failure recovery, and rotation procedures are
in [infra/azure/README.md](../infra/azure/README.md). Provisioning is Terraform, split into
two sibling modules (`infra/azure/oauth/` and `infra/azure/scanning/`). The non-secret
production inputs for the OAuth slice are the defaults in
[infra/azure/oauth/variables.tf](../infra/azure/oauth/variables.tf) (copy
[terraform.tfvars.example](../infra/azure/oauth/terraform.tfvars.example) to `terraform.tfvars`);
`terraform plan` is the read-only preview.

## Suggested session prompt

> Read docs/azure-email-setup.md and docs/email-scanning-milestones.md. Use the Terraform in infra/azure/ to plan and configure Microsoft mailbox OAuth on the existing API (`terraform plan` to preview, `terraform apply` to configure). Inspect existing resources first and import any the earlier bootstrap created (see the README) so Terraform adopts rather than duplicates them; preserve existing secrets/settings, and record only non-secret resource IDs. Keep connection and scanning flags disabled during setup. Defer Service Bus and worker provisioning to their implementation milestone (`enable_scanning_infra = false`). Preserve ongoing application changes in the shared workspace.

## Required for the implemented OAuth slice

1. **Entra application:** use one approved organizational tenant for V1. Supported account type: accounts in that organizational directory only. Record tenant UUID and application/client UUID. Consumer Outlook.com accounts are not supported by this slice.
2. **Web callback:** register `https://ileracare.app/api/email/microsoft/callback` if this is the deployed frontend origin. Use the actual HTTPS frontend origin for staging. The callback is a Web redirect, not an SPA redirect, and must end in `/api/email/microsoft/callback`.
3. **Permissions:** delegated Microsoft Graph `Mail.Read`; OIDC `openid`, `profile`, and `offline_access` are requested in the authorization flow. No mail-write, send, directory-wide, or application mailbox permissions. Tenant policies may require admin consent. The verified ID token provides the account ID; the app does not need User.Read just to identify it.
4. **Application secret:** put the Entra client-secret VALUE in Key Vault as `ilera-microsoft-client-secret`. Do not confuse the secret's ID with its value. Record its expiration and plan rotation. Do not place its value in the environment file.
5. **Encryption key:** securely generate a Fernet key (URL-safe base64 encoding of 32 random bytes) and store it in Key Vault as `ilera-email-token-key`. Do not print or paste the key into chat. Preserve previous versions when rotating: each database ciphertext records its encryption-key version.
6. **Runtime identity:** assign the API's managed identity the `Key Vault Secrets User` role on the dedicated vault (or equivalent scoped secret-read access). The code reads secrets; it does not create them. A setup operator needs appropriate write permissions. Confirm network access to the vault.
7. **Postgres:** retain the existing DATABASE_URL. Startup DDL creates email metadata, encrypted credentials, and expiring OAuth-state tables. The API database role needs the same schema modification permissions used by the rest of the app. Do not copy production credentials into another database or session transcript.
8. **Deploy configuration:** set the non-secret settings below on the backend. The frontend's API_URL must target this backend. Dependency installation happens from backend/requirements.txt; production Python is 3.12.
9. **Callback logging:** configure proxy/access logging and tracing to omit the query string on `/api/email/microsoft/callback`; Microsoft sends a short-lived authorization code in this URL. Application callback code sends it onward in a POST body and redirects immediately to a clean dashboard URL, with no-store/no-referrer headers. Do not enable HTTP body logging for token or Key Vault requests.

| Setting | Value |
| --- | --- |
| EMAIL_CONNECTIONS_ENABLED | false during setup; true only when ready for a live connection check |
| EMAIL_MICROSOFT_TENANT_ID | Approved organizational tenant UUID |
| EMAIL_MICROSOFT_CLIENT_ID | Entra application/client UUID |
| EMAIL_MICROSOFT_REDIRECT_URI | Exact registered HTTPS frontend callback |
| EMAIL_KEY_VAULT_URL | `https://<vault-name>.vault.azure.net` |
| EMAIL_MICROSOFT_CLIENT_SECRET_NAME | `ilera-microsoft-client-secret` |
| EMAIL_TOKEN_ENCRYPTION_KEY_NAME | `ilera-email-token-key` |
| EMAIL_USE_MANAGED_IDENTITY | true in Azure |
| EMAIL_MANAGED_IDENTITY_CLIENT_ID | Empty for system-assigned identity; client ID for user-assigned identity |
| EMAIL_SCANNING_ENABLED | false; the scan pipeline is not ready |

Local development can use EMAIL_USE_MANAGED_IDENTITY=false with Azure CLI credentials and appropriate vault access. Use an HTTPS frontend development endpoint registered in Entra. Do not point local development at production mailboxes or credentials unintentionally. Current Anaconda base is Python 3.9; prepare a separate Anaconda Python 3.12 environment for runtime work when test runs resume.

## Can be prepared for later milestones

- Service Bus namespace and `email.scan` queue, with duplicate detection enabled at queue creation, bounded delivery attempts, and dead-letter handling.
- Sender role for the ingest API and receiver role for the future worker. Use managed identity, not a Service Bus connection string.
- Container Apps worker hosting and a dedicated Azure OpenAI deployment. The worker implementation will define its runtime settings; do not reuse the generic OPENAI_API_KEY path for email content.
- Cost estimates and deployment definitions in the infrastructure branch. The application session does not require provisioning these to finish OAuth code.

## Handoff

Return only non-secret resource names/IDs, the registered callback URL, configuration names, deployment readiness, and any missing permissions. Do not enable scanning or announce it as working. A live check still needs to demonstrate connect, refresh, reconnect/disconnect, ownership isolation, and deletion behavior.

References: [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [Key Vault Python secrets client](https://learn.microsoft.com/en-us/python/api/overview/azure/keyvault-secrets-readme?view=azure-python), [Service Bus Python SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/servicebus-readme?view=azure-python).

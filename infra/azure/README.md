# Ilera email infrastructure (Terraform)

Terraform for the Microsoft mailbox OAuth slice and the deferred email-scanning pipeline,
on Azure. This replaces the earlier `setup_email.py` bootstrap. It configures OAuth on the
**existing** `ilera-api`; it does not deploy application code, create another API or
database, or grant tenant-wide mailbox consent.

Everything is HIPAA-oriented: RBAC-only Key Vault with purge protection, managed-identity
access (no shared keys), audit logging to Log Analytics, and default-deny network ACLs.
Compliance is a posture, not a resource — see [HIPAA notes](#hipaa-notes).

## Layout

Two independent root modules under `infra/azure/`, each with its own state:

```
infra/azure/
  oauth/       mailbox OAuth slice — apply first
  scanning/    Service Bus + scan worker + OpenAI wiring — apply when the worker is ready
```

`scanning` depends on `oauth` only through remote state (it reads oauth's outputs for the
vault ID and API identity), so apply `oauth` first.

### `oauth/`

| File | What it manages |
|---|---|
| `versions.tf` | Provider pins (azurerm, azuread, azapi, random, time) and the remote-state backend |
| `variables.tf` | Inputs; defaults are the reviewed non-secret production values |
| `data.tf` | References to existing resources (subscription, API app, its identity); `EMAIL_*` env values |
| `entra.tf` | Docs only — the Entra app is managed **outside** Terraform (see below) |
| `keyvault.tf` | Dedicated Key Vault, Fernet key; bootstrap + runtime RBAC |
| `api.tf` | System-assigned identity, Secrets User role, and `EMAIL_*` env vars on `ilera-api` |
| `hipaa.tf` | Log Analytics + Key Vault diagnostic settings |
| `outputs.tf` | Non-secret resource IDs, callback URL, config names (read by `scanning/`) |

### `scanning/`

| File | What it manages |
|---|---|
| `versions.tf` | Provider pins and its own remote-state backend (`email-scanning.tfstate`) |
| `variables.tf` | Inputs; required inputs (worker image, OpenAI account) have no default |
| `data.tf` | `oauth/` remote state, existing Container Apps env, existing Azure OpenAI |
| `main.tf` | Service Bus (dedup/DLQ), scan worker Container App, sender/receiver + vault + OpenAI RBAC |

## Prerequisites

- Terraform >= 1.6 and an Azure CLI login in the configured tenant/subscription
  (`az login --tenant <tenant>`; `az account set --subscription <sub>`).
- The operator/CI identity running `apply` needs: resource create/update in the `Ilera`
  resource group and permission to create role assignments on the Key Vault
  (`Role Based Access Control Administrator`). It needs **no Entra/Graph permissions** —
  the Entra app is managed outside Terraform. Terraform grants the operator identity
  `Key Vault Secrets Officer` to write the Fernet key; the API runtime identity only gets
  `Secrets User`.
- The `Microsoft.KeyVault` and (for scanning) `Microsoft.ServiceBus`,
  `Microsoft.CognitiveServices` resource providers registered on the subscription.

## Remote state (required)

State is remote, never local: the Microsoft client secret and the Fernet key transit
Terraform state, so it lives in an encrypted, access-controlled Azure Storage container
with locking — shared by CI and operators. The backing storage must exist before the
first `terraform init`. One-time bootstrap (state lives in the existing `Ilera` group to
keep things consolidated):

```sh
az storage account create -n ileratfstate -g Ilera -l eastus2 \
  --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false \
  --encryption-services blob
az storage container create -n tfstate --account-name ileratfstate --auth-mode login
```

The `backend "azurerm"` block in each module's `versions.tf` is already configured for this
(`use_azuread_auth = true`, so no storage keys — access is via the CI/operator Entra
identity, which needs `Storage Blob Data Contributor` on the account). Both modules share
the `ileratfstate` account and `tfstate` container but use different state keys
(`email-infra.tfstate`, `email-scanning.tfstate`). The storage account name must be globally
unique; change it everywhere if it's taken.

For syntax/validate steps that must not touch Azure (CI lint, local checks), skip the
backend:

```sh
terraform init -backend=false && terraform validate
```

## Plan and apply

Apply `oauth/` first:

```sh
cd infra/azure/oauth
cp terraform.tfvars.example terraform.tfvars   # non-secret values only
terraform init      # connects to the remote azurerm backend (storage must exist)
terraform plan      # read-only; review before applying
terraform apply
```

`plan` is the equivalent of the old `setup_email.py` read-only preview. The email settings
`EMAIL_CONNECTIONS_ENABLED` and `EMAIL_SCANNING_ENABLED` are set to `"false"` directly in
`data.tf`: applying wires up the infrastructure without turning email on. Change them there
when you're ready — the plan diff shows the change.

## CI/CD

`.github/workflows/terraform.yml` runs Terraform through GitHub Actions:

- **Pull request** touching `infra/azure/**` → `fmt -check` + `validate` + `plan`, and the
  plan is posted as a PR comment. Read-only.
- **Push to `main`** → `apply`, gated behind the `infra-production` GitHub **Environment**. Apply
  waits until a required reviewer approves — that's the human gate on the high-risk step.
- **Manual dispatch** lets you target `oauth` or `scanning` and choose plan/apply. Automatic
  triggers only run `oauth`; run `scanning` explicitly once its worker image exists.

One-time setup (mirrors `deploy.yml`):

- Secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (OIDC federated
  credential for this repo — no stored password).
- A GitHub Environment named `infra-production` with **required reviewers** configured, so the
  apply job pauses for approval.
- The CI service principal needs (all ARM, **no Entra/Graph permissions**):
  - `Contributor` on the `Ilera` resource group (create/update resources)
  - `Role Based Access Control Administrator` on the `Ilera` resource group (create the
    Key Vault / Service Bus / OpenAI role assignments)
  - `Storage Blob Data Contributor` on `ileratfstate` (read/write remote state)

The apply job re-plans into a file and applies exactly that plan, so nothing can drift
between the reviewed plan and the approved apply.

## Importing existing resources

If the Python bootstrap already created the vault or assigned the API identity, import
them so Terraform adopts rather than duplicates them. Run these from `infra/azure/oauth/`.
Import, then run `plan` and reconcile any diff before `apply`:

```sh
# Key Vault
terraform import azurerm_key_vault.email \
  /subscriptions/<sub>/resourceGroups/Ilera/providers/Microsoft.KeyVault/vaults/ilera-email-01a341d5

# If a Fernet key already exists in the vault, import it — ignore_changes on value
# preserves the existing key material rather than re-keying stored tokens.
terraform import azurerm_key_vault_secret.token_encryption_key \
  "https://ilera-email-01a341d5.vault.azure.net/secrets/ilera-email-token-key/<version>"
```

The Entra application is **not** imported — it is managed outside Terraform (below). The
API Container App is also **not** imported as a full resource: `api.tf` patches only
identity + env onto it via `azapi_update_resource`, leaving the image/scale to the deploy
workflow.

## Entra app (out of band)

The `ilera-microsoft-mailbox` Entra application and its client secret are managed by a
human admin, not this module — managing a directory object from a CI service principal
would require granting that principal standing Microsoft Graph app-management permissions
with admin consent, which we don't want the deploy identity to hold.

Terraform only references the app's client ID (`var.mailbox_client_id`) and expects the
client-secret VALUE to already be present in the Key Vault under `var.client_secret_name`.
Admin steps (one-time, and on rotation):

1. Ensure the app exists: single-tenant (`AzureADMyOrg`), web redirect `var.redirect_uri`,
   delegated Microsoft Graph scopes `Mail.Read`, `openid`, `profile`, `offline_access`.
2. Create/rotate the client secret in the portal (or an admin-run `az ad app credential`
   command).
3. Write the secret VALUE into the vault:
   `az keyvault secret set --vault-name ilera-email-01a341d5 --name ilera-microsoft-client-secret --file <secret-file>`
   (use `--file`, not `--value`, to keep it out of shell history).

The API reads that secret at runtime via its managed identity. Rotation is a matter of
adding a new secret version out of band; Terraform is not involved.

## HIPAA notes

Technical safeguards Terraform expresses here (HIPAA Security Rule references):

- **Audit controls (§164.312(b))** — Key Vault diagnostic settings stream every secret
  access to Log Analytics; `log_retention_days` defaults to 730 (the workspace maximum).
  Longer HIPAA retention (e.g. 6 years) is via archive/export — see `hipaa.tf`.
- **Access control (§164.312(a))** — RBAC-only vault; runtime identities get `Secrets User`,
  never write/manage. Service Bus and OpenAI use managed identity, `local_auth_enabled = false`.
- **Transmission security (§164.312(e))** — Key Vault network ACLs default-deny; private
  endpoint scaffolding in `hipaa.tf` (set `key_vault_private_endpoint_subnet_id` and flip
  `key_vault_public_network_access_enabled = false` once a VNet-integrated environment exists).
- **Integrity / availability** — purge protection and soft-delete on the vault survive an
  accidental `terraform destroy`.

Outside Terraform, and required for actual compliance:

- A signed **Microsoft BAA** covering the subscription and every service touching PHI
  (Container Apps, Key Vault, Service Bus, Azure OpenAI, Log Analytics, Postgres).
- **Azure OpenAI content-logging / abuse-monitoring opt-out** so Microsoft does not retain
  or human-review PHI prompts. Request this for whichever OpenAI resource the worker uses.
- **Callback query-string logging** must be suppressed at the proxy/ingress: Microsoft sends
  a short-lived authorization code in the `/api/email/microsoft/callback` URL. This is an
  app/ingress config concern, not Terraform. Do not enable HTTP body logging for token or
  Key Vault requests.
- No PHI (raw email) in logs, traces, queues, or permanent storage — enforced by the worker
  code, not infrastructure.

### Azure OpenAI

The scan worker reuses your **existing** Azure OpenAI account — one deployment, no
dedicated resource. Set `existing_openai_account_name` and `email_openai_deployment_name`
in the `scanning/` module. The worker calls it with its managed identity (no shared API
key). HIPAA conditions that apply: the account is covered by your Microsoft BAA and has
content-logging / abuse-monitoring opted out for PHI.

## Rotation

- **Client secret** — managed outside Terraform. Rotate by adding a new Entra credential
  and writing its value into the vault under `var.client_secret_name` (see "Entra app (out
  of band)"). Validate a token refresh, then retire the old credential. Terraform is not
  involved.
- **Fernet key** — `azurerm_key_vault_secret.token_encryption_key` has `ignore_changes = [value]`
  so a re-apply never silently re-keys stored tokens. To rotate deliberately, add a new secret
  version out of band and re-encrypt database ciphertext before disabling the old version. Each
  DB ciphertext records its key version; keep every referenced version enabled until re-encrypted.

## Scanning pipeline (separate module)

The Service Bus, scan worker, and OpenAI role wiring live in `scanning/` as their own
module — not gated by a flag. Apply it when the worker image exists and the OAuth module
has already been applied (it reads that module's remote state for the vault and API
identity). A missing input (worker image, OpenAI account) fails at plan, not silently.

```sh
cd infra/azure/scanning
cp terraform.tfvars.example terraform.tfvars   # set scan_worker_image + OpenAI account/deployment
terraform init
terraform plan
terraform apply
```

The queue uses duplicate detection, bounded delivery (5), and dead-lettering; the API is a
Service Bus **sender** and the worker a **receiver**, both by managed identity. Broker dedup
does not replace worker idempotency. Set `EMAIL_SCANNING_ENABLED` to `"true"` in the OAuth
module's `data.tf` only once the pipeline and calendar review are validated.

## Verification

Terraform apply proves the resources exist, not that the mailbox flow works. Before enabling
connections: confirm the API identity can read both secrets, check callback logs omit query
strings, deploy the OAuth application code, and test connect, refresh, reconnect/disconnect,
ownership isolation, and deletion.

References:
[Key Vault RBAC roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/security),
[Service Bus RBAC](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-managed-service-identity),
[Azure OpenAI + managed identity](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/managed-identity),
[Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

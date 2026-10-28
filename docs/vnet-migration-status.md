# VNet migration status — October 19, 2026

Production cutover is complete. `ileracare.app` and `api.ileracare.app` now serve from the VNet-connected Container Apps environment. PostgreSQL public network access is **Disabled**.

## Production resources

| Resource | Network / status |
| --- | --- |
| `ilera-prod-cae-eastus2` | Integrated with `ilera-vnet/ilera-apps` (`10.84.0.0/23`); public HTTPS ingress for the website/API |
| `ilera-web-prod-eastus2` | Production website; server-side API proxy points to the VNet API |
| `ilera-api-prod-eastus2` | Production API; existing image, settings, secrets and RBAC preserved |
| `ilera-agent-orchestration` | Integrated with `ilera-vnet/ilera-functions` (`10.84.3.0/26`) |
| `ilera-email-worker-prod` | VNet environment; existing user-assigned identity and explicit Service Bus scaler identity |
| `ilera-email-maint-prod` | VNet environment; hourly schedule (`0 * * * *`) |
| `ilera-rag-ingest` | Manual VNet job; GitHub builds the corpus image and starts an execution |
| `ilera-pg` | Approved private endpoint at `10.84.2.4`; private DNS zone linked to the VNet; public access disabled |

Namecheap DNS now has A `@` → `74.155.160.236` and CNAME `api` → `ilera-api-prod-eastus2.redbay-48c0c5f1.eastus2.azurecontainerapps.io`. Both production domains have new Azure-managed TLS certificates. Mail and ownership records were preserved. The prior 30-minute DNS cache lifetime elapsed before database lockdown.

## Verification

- Production website `/healthz`, web API proxy `/api/intake/schema`, and API `/readyz` returned 200 after PostgreSQL public access was disabled.
- An in-VNet probe resolves PostgreSQL to `10.84.2.4` and performs a fresh `SELECT 1`.
- The updated GitHub RAG ingestion workflow completed successfully inside the VNet.
- Recent hourly maintenance executions succeeded.
- Both Terraform modules validate. Read-only plans show no replacement or deletion of migrated services or their API permissions. The scanning plan also includes an existing, unrelated local purge-job definition; no full scanning apply was performed.

## Deployment and Terraform tracking

GitHub repository variables are now `API_APP=ilera-api-prod-eastus2` and `WEB_APP=ilera-web-prod-eastus2`; the public host variables are unchanged.

Terraform state now tracks the VNet worker, maintenance job, and replacement API role assignments. The OAuth output was refreshed to the new API identity. Imported role-assignment GUIDs are preserved while scope, principal and role remain managed.

Published configuration commits:

- `ddef3aff6f1bbdeacc26244cb9496420e9ff9d50`: run corpus ingestion inside the VNet.
- `466989f03e249b6de81480f4619bbdf349f0f395`: track VNet production services.
- `909847e1b982ad3cf9911ada7effaab4001b6a57`: retain imported API role-assignment identifiers.

The latest GitHub Terraform plan passed. Its apply job remains behind the configured human-review gate; that gate was not bypassed. Runtime migration and Terraform imports were completed separately under the user's authorization.

## Rollback resources

The old web revision `ilera-web--0000028`, API revision `ilera-api--0000042`, and old email worker revisions are deactivated. The old maintenance job is Manual. Their resources are retained; none were deleted. Existing PostgreSQL firewall allowances remain inert while public access is disabled.

Rollback to the old environment requires restoring public PostgreSQL access under the previous firewall rules, reactivating the old revisions, and restoring A `@` → `4.152.158.189` and CNAME `api` → `ilera-api.blueglacier-bd9aff7b.eastus2.azurecontainerapps.io`. Restore GitHub deployment targets as part of a full rollback. Do not delete the private endpoint or private DNS zone.

## Local development

Direct laptop access to Azure PostgreSQL now requires private network connectivity. The user preferred VPN access but has not approved provisioning a managed gateway after reviewing its cost. No VPN gateway was created. Local development that uses the Azure database needs VPN/tunnel access; an isolated local database remains an alternative. Do not re-enable PostgreSQL public access as a development workaround.

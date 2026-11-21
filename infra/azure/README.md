# Ilera on Azure

Everything runs in subscription `ilera-subscription`, resource group `Ilera`, region
**eastus2** (resource group metadata in eastus). Azure access between services uses managed
identities; nothing holds a shared key except where noted. Inventory as of 2026-11-20.

## How a request flows

```
ileracare.app ─▶ ilera-web-prod-eastus2 ─▶ api.ileracare.app ─▶ ilera-api-prod-eastus2
                  (Next.js)                                       (FastAPI)
                                                                    │
     ┌───────────────────────┬─────────────────┬───────────────────┼──────────────────────┐
     ▼                       ▼                 ▼                   ▼                      ▼
 ilera-pg (Postgres,   ilera-agent-       ilera-resource       ilerastorage        ilera-email-bus
 private endpoint)     orchestration      (gpt-5-mini,         (forms, guides)     ─▶ ilera-email-worker-prod
                       (eligibility       embeddings)                                  (Outlook scanning)
                       pipeline)
```

## Resources

### Apps and compute
| Resource | Purpose |
|---|---|
| `ilera-prod-cae-eastus2` | Container Apps environment (VNet-integrated, subnet `ilera-apps`) hosting everything below |
| `ilera-web-prod-eastus2` | Web app (Next.js) at **ileracare.app**; proxies `/api` to the API |
| `ilera-api-prod-eastus2` | API (FastAPI) at **api.ileracare.app**: intake, accounts, records, forms, eligibility status, email webhooks, document reading |
| `ilera-email-worker-prod` | Reads queued Outlook messages and turns appointments into calendar suggestions |
| `ilera-email-maint-prod` (job, hourly) | Renews Microsoft Graph subscriptions, recovers missed mail, prunes orphans |
| `ilera-purge-unclaimed` (job, daily 10:00 UTC) | Deletes anonymous intakes no account claimed within 5 days (household data with no owner) |
| `ilera-rag-ingest` (job, on demand) | Embeds `backend/data/knowledge` into the search index; started by the RAG ingest workflow on merges |
| `ilera-agent-orchestration` + `ASP-Ilera-3782` | Azure Functions (Flex Consumption, subnet `ilera-functions`): the Durable eligibility pipeline — gates, per-program specialist agents, synthesis |
| `caff3fa0d6e7acr` | Container registry (Basic) for the API, web, worker and ingest images |
| `ilera-email-worker-id` | User-assigned identity shared by the worker and maintenance job |

### Data
| Resource | Purpose |
|---|---|
| `ilera-pg` | PostgreSQL 16 (Burstable B1ms, 32 GB, pgvector). Every record the app keeps plus the RAG index (`rag_chunks`). Public access disabled; reached through `ilera-pg-endpoint` |
| `ilerastorage` | Blob storage: `forms` (government PDF templates), `reference-guides` (public guides), plus the Functions app's packages, hosts and task-hub containers |
| `ileratfstate` | Terraform remote state (`tfstate` container) |
| `ilera-email-01a341d5` | Key Vault (RBAC, purge protection): Microsoft OAuth client secret and the mailbox-token encryption key |

### AI
| Resource | Purpose |
|---|---|
| `ilera-resource` | Azure OpenAI for eligibility research and email extraction: `gpt-5-mini` and `text-embedding-3-small` |
| `ilera-documents-openai` | Dedicated Azure OpenAI for reading uploaded intake documents (`gpt-5-mini`, US data zone). Managed identity only |

### Messaging and email
| Resource | Purpose |
|---|---|
| `ilera-email-bus` | Service Bus (Standard), queue `email.scan`: the API publishes Graph notifications, the worker consumes them |
| `ilera-comms` + `ilera-email` (domain `ileracare.app`) | Azure Communication Services: verification links and login codes (connection string held by the API) |

### Networking
| Resource | Purpose |
|---|---|
| `ilera-vnet` | 10.84.0.0/22 — subnets `ilera-apps`, `ilera-functions`, `ilera-private-endpoints` |
| `ilera-pg-endpoint` + `privatelink.postgres.database.azure.com` | Private endpoint and DNS zone so apps reach Postgres inside the VNet |
| `ME_ilera-prod-cae-eastus2_Ilera_eastus2` (group) | Load balancer and public IP managed by the Container Apps environment — do not edit |
| `NetworkWatcherRG` (group) | Created automatically by Azure |

### Monitoring
| Resource | Purpose |
|---|---|
| `workspace-leraWmgA` | Container Apps logs (API, web, worker, jobs) |
| `ilera-durable-insights` (+ its managed workspace) | Application Insights for the Functions pipeline |
| `ilera-email-logs` | HIPAA audit trail (730 days): Key Vault and `ilera-documents-openai` audit events, Functions logs |
| `workspace-leraBjB5`, `ilera-resource-logs`, `ilera-resource-appinsights` | Currently receive no data |
| Application Insights Smart Detection | Alert action group created by Azure |

## Managing it

- **Terraform** (`oauth/`: Key Vault, API identity roles, audit logging, `ilera-documents-openai`;
  `scanning/`: Service Bus, worker, maintenance job). State is in `ileratfstate`. Merges to
  `main` that touch `infra/azure/**` plan and then wait for approval on the `infra-production`
  environment before applying `oauth/`; `scanning/` is applied by running the Terraform
  workflow manually. The Entra app registration is managed outside Terraform.
- **App deploys** (`.github/workflows/deploy.yml`): every backend or frontend push to `main`
  builds in the registry and rolls the API, web app, Functions and email worker forward, then
  moves every job that runs the API image (maintenance, purge, RAG ingest, and any added
  later) to the same build. Terraform ignores those images so it never reverts them. App
  settings on the API are set on the container app, not in Terraform.
- **Key Vault safety**: purge protection is on and Terraform never re-keys the encryption key;
  rotating it means re-encrypting stored tokens first.
- **HIPAA**: the Microsoft BAA covers these services. The email docs record an approved
  abuse-monitoring opt-out for `ilera-resource`, but neither Azure OpenAI account currently
  shows the opt-out flag; confirm it, and request it for `ilera-documents-openai`.

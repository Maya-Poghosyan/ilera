# Input variables.
#
# The defaults reproduce the reviewed, non-secret production inputs that used to live
# in infra/azure/email.production.json. Nothing secret belongs here: the Microsoft
# client-secret value and the Fernet key are generated/stored in Key Vault, never in
# tfvars or state as inputs. (The client secret does transit state once — see README.)

variable "subscription_id" {
  description = "Azure subscription that owns the Ilera resources."
  type        = string
  default     = "01a341d5-5453-4e83-92ee-4f0cc2e3d47d"
}

variable "tenant_id" {
  description = "Entra tenant. Also the single approved organizational tenant for V1 mailbox OAuth."
  type        = string
  default     = "5c8a1e25-bdc4-4ced-b8c2-3cda51c721d9"
}

variable "resource_group" {
  description = "Existing resource group holding ilera-api, ilera-web, ilera-env, ilera-pg."
  type        = string
  default     = "Ilera"
}

variable "location" {
  description = "Azure region for new resources. Must be a region covered by your Microsoft BAA."
  type        = string
  default     = "eastus2"
}

variable "api_app_name" {
  description = "Existing API Container App to attach identity, env vars, and vault access to."
  type        = string
  default     = "ilera-api"
}

variable "terraform_principal_object_id" {
  description = "Object ID of the identity that runs terraform apply, granted Key Vault Secrets Officer to write the Fernet key. Defaults to the CI service principal (ilera-deploy). A human applying locally should override this with their own object ID (or pre-grant themselves the role)."
  type        = string
  default     = "9d46b02b-381b-4f94-a260-31d476992e63" # ilera-deploy CI service principal
}

# --- Mailbox OAuth (app managed outside Terraform — see entra.tf) ------------

variable "mailbox_client_id" {
  description = "Client (application) ID of the existing ilera-microsoft-mailbox Entra app. Managed outside Terraform."
  type        = string
  default     = "c3b57022-1fcd-4434-a04a-b9ce41e54987"
}

variable "redirect_uri" {
  description = "Exact HTTPS frontend callback. Must end in /api/email/microsoft/callback."
  type        = string
  default     = "https://ileracare.app/api/email/microsoft/callback"

  validation {
    condition     = can(regex("^https://[^?#]+/api/email/microsoft/callback$", var.redirect_uri))
    error_message = "redirect_uri must be HTTPS, have no query/fragment, and end in /api/email/microsoft/callback."
  }
}

variable "vault_name" {
  description = "Dedicated Key Vault for mailbox secrets. Global-unique, 3-24 chars."
  type        = string
  default     = "ilera-email-01a341d5"
}

variable "client_secret_name" {
  description = "Key Vault secret name holding the Entra application client-secret VALUE."
  type        = string
  default     = "ilera-microsoft-client-secret"
}

variable "encryption_key_name" {
  description = "Key Vault secret name holding the Fernet token-encryption key."
  type        = string
  default     = "ilera-email-token-key"
}

# --- HIPAA hardening ---------------------------------------------------------

variable "log_analytics_workspace_id" {
  description = "Existing Log Analytics workspace resource ID for diagnostic settings. Empty creates one."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "Log Analytics interactive retention (Azure allows 30-730). Longer HIPAA retention is via archive/export — see hipaa.tf."
  type        = number
  default     = 730

  validation {
    condition     = var.log_retention_days >= 30 && var.log_retention_days <= 730
    error_message = "log_retention_days must be between 30 and 730 (workspace limit); use archive/export for longer retention."
  }
}

variable "key_vault_network_default_action" {
  description = "Key Vault network ACL default action. 'Allow' (RBAC still gates access) lets CI runners write secrets; switch to 'Deny' once a private endpoint + known CI network exist."
  type        = string
  default     = "Allow"

  validation {
    condition     = contains(["Allow", "Deny"], var.key_vault_network_default_action)
    error_message = "key_vault_network_default_action must be 'Allow' or 'Deny'."
  }
}

variable "key_vault_allowed_ip_ranges" {
  description = "CIDR ranges permitted to reach Key Vault when default action is Deny."
  type        = list(string)
  default     = []
}

variable "key_vault_public_network_access_enabled" {
  description = "Leave the vault's public endpoint on (guarded by network ACLs) until a private endpoint is wired."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to all managed resources."
  type        = map(string)
  default = {
    application = "ilera"
    component   = "email-scanning"
    compliance  = "hipaa"
    managed-by  = "terraform"
  }
}

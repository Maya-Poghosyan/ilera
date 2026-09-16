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

# --- Mailbox OAuth (implemented slice) ---------------------------------------

variable "mailbox_app_name" {
  description = "Display name for the Entra application used for delegated mailbox OAuth."
  type        = string
  default     = "ilera-microsoft-mailbox"
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

variable "client_secret_rotation_days" {
  description = "Lifetime of the generated Entra client secret before Terraform rotates it."
  type        = number
  default     = 180
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

variable "key_vault_allowed_ip_ranges" {
  description = "CIDR ranges permitted to reach Key Vault when public access stays on. Empty + trusted-services only is the hardened default."
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

# Inputs for the scanning pipeline. Required inputs (worker image, OpenAI account) have
# no default: leaving them unset fails at plan time rather than silently doing nothing.

variable "subscription_id" {
  type    = string
  default = "01a341d5-5453-4e83-92ee-4f0cc2e3d47d"
}

variable "tenant_id" {
  type    = string
  default = "5c8a1e25-bdc4-4ced-b8c2-3cda51c721d9"
}

variable "resource_group" {
  type    = string
  default = "Ilera"
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "container_apps_environment_name" {
  description = "Existing Container Apps managed environment (ilera-env) the worker runs in."
  type        = string
  default     = "ilera-env"
}

variable "scan_worker_image" {
  description = "Container image for the scan worker. Required — no default."
  type        = string
}

variable "existing_openai_account_name" {
  description = "Name of the existing Azure OpenAI (Cognitive Services) account the worker calls. Required — no default."
  type        = string
}

variable "container_registry_name" {
  description = "Name of the existing Azure Container Registry holding the worker image (no .azurecr.io). Required — no default."
  type        = string
}

variable "api_image" {
  description = "Full API image reference (has the whole app) used by the maintenance job. Required — no default."
  type        = string
}

variable "database_url" {
  description = "Postgres connection string for the maintenance job. Sensitive; sourced out of band (same value as the API's database-url secret). Set via TF_VAR_database_url, not committed."
  type        = string
  sensitive   = true
}

variable "email_microsoft_notification_url" {
  description = "Public API notifications endpoint used by subscription maintenance."
  type        = string
  default     = "https://api.ileracare.app/api/email/microsoft/notifications"
}

variable "email_scanning_enabled" {
  description = "Master switch for processing real email content. Only true after BAA / abuse-monitoring opt-out is confirmed for the OpenAI account."
  type        = string
  default     = "true"
}

variable "mailbox_tenant_id" {
  type    = string
  default = "5c8a1e25-bdc4-4ced-b8c2-3cda51c721d9"
}

variable "mailbox_client_id" {
  type    = string
  default = "c3b57022-1fcd-4434-a04a-b9ce41e54987"
}

variable "mailbox_redirect_uri" {
  type    = string
  default = "https://ileracare.app/api/email/microsoft/callback"
}

variable "email_openai_deployment_name" {
  description = "Name of the deployment on the existing Azure OpenAI account for extraction."
  type        = string
}

variable "tags" {
  type = map(string)
  default = {
    application = "ilera"
    component   = "email-scanning"
    compliance  = "hipaa"
    managed-by  = "terraform"
  }
}

# Inputs for the scanning pipeline. The images and database URL have no default: CI reads them
# from Azure (terraform.yml), and leaving one unset fails at plan time.

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
  description = "Existing Container Apps managed environment (ilera-prod-cae-eastus2) the worker runs in."
  type        = string
  default     = "ilera-prod-cae-eastus2"
}

variable "scan_worker_image" {
  description = "Container image for the scan worker, used only when the app is created (CI rolls it after). CI passes the live image."
  type        = string
}

variable "existing_openai_account_name" {
  description = "Name of the existing Azure OpenAI (Cognitive Services) account the worker calls."
  type        = string
  default     = "ilera-resource"
}

variable "container_registry_name" {
  description = "Name of the existing Azure Container Registry holding the worker image (no .azurecr.io)."
  type        = string
  default     = "caff3fa0d6e7acr"
}

variable "api_image" {
  description = "Full API image reference used when the maintenance and purge jobs are created (CI rolls it after). CI passes the live image."
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
  default     = "gpt-5-mini"
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

variable "google_client_id" {
  description = "Gmail OAuth web client id (<number>-<id>.apps.googleusercontent.com). Empty = Gmail is off for the worker and maintenance job."
  type        = string
  default     = "816584170783-m4j85gmre1m2umtu8hcuu46gbekoinsr.apps.googleusercontent.com"
}

variable "google_redirect_uri" {
  type    = string
  default = "https://ileracare.app/api/email/google/callback"
}

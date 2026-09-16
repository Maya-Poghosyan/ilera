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

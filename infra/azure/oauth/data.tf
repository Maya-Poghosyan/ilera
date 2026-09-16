# References to resources that already exist and that this configuration must NOT
# recreate: the subscription, the API Container App, and the shared Container Apps
# environment. The Python setup guarded against clobbering these; data sources give
# Terraform the same guarantee — it reads them, it never proposes to replace them.

data "azurerm_subscription" "current" {
  subscription_id = var.subscription_id
}

data "azurerm_client_config" "current" {}

# The signed-in operator running terraform apply. Granted Key Vault Secrets Officer so
# Terraform can write the two secrets. This is a human/CI bootstrap principal, never the
# app's runtime identity (which only ever gets Secrets User).
data "azuread_client_config" "current" {}

# The existing API Container App. We attach a system-assigned identity, vault access,
# and env vars to it; we do not define its image or scaling here (that stays with the
# deploy workflow). Managed via an azapi/ignore pattern documented in the README so a
# terraform apply here does not fight the CI image roll-forward.
data "azurerm_container_app" "api" {
  name                = var.api_app_name
  resource_group_name = var.resource_group
}

locals {
  vault_uri = "https://${var.vault_name}.vault.azure.net"

  # Built-in Key Vault role definition GUIDs (stable across Azure).
  role_secrets_user_id    = "4633458b-17de-408a-b874-0445c86b69e6" # Key Vault Secrets User
  role_secrets_officer_id = "b86a8fe4-44ce-4948-aee5-eccb2c155cd7" # Key Vault Secrets Officer

  # Deterministic role-assignment names, matching the formula the earlier setup used
  # (Python uuid.uuid5(NAMESPACE_URL, scope.lower() + principal + role_definition_guid)).
  # Terraform's uuidv5("url", ...) uses the same URL namespace, so these reproduce the
  # existing assignment GUIDs exactly — imports are clean and re-applies never replace.
  role_assignment_scope = lower(azurerm_key_vault.email.id)

  # Non-secret backend configuration set on the API.
  # Secret VALUES are never here — only the Key Vault secret NAMES the app reads.
  # EMAIL_CONNECTIONS_ENABLED and EMAIL_SCANNING_ENABLED are set directly here.
  # Change them when you're ready to turn things on — the plan diff will show it.
  api_email_settings = {
    EMAIL_CONNECTIONS_ENABLED          = "false"
    EMAIL_SCANNING_ENABLED             = "false"
    EMAIL_MICROSOFT_TENANT_ID          = var.tenant_id
    EMAIL_MICROSOFT_CLIENT_ID          = var.mailbox_client_id
    EMAIL_MICROSOFT_REDIRECT_URI       = var.redirect_uri
    EMAIL_KEY_VAULT_URL                = local.vault_uri
    EMAIL_MICROSOFT_CLIENT_SECRET_NAME = var.client_secret_name
    EMAIL_TOKEN_ENCRYPTION_KEY_NAME    = var.encryption_key_name
    EMAIL_USE_MANAGED_IDENTITY         = "true"
    EMAIL_MANAGED_IDENTITY_CLIENT_ID   = "" # empty = system-assigned identity
  }
}

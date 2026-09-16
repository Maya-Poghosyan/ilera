# Non-secret outputs. These mirror the JSON "report" setup_email.py returned: resource
# names/IDs, the callback URL, and config names — never secret values.

output "mailbox_application_client_id" {
  description = "Entra application (client) ID for EMAIL_MICROSOFT_CLIENT_ID."
  value       = azuread_application.mailbox.client_id
}

output "mailbox_application_object_id" {
  description = "Entra application object ID."
  value       = azuread_application.mailbox.object_id
}

output "mailbox_service_principal_object_id" {
  description = "Enterprise application (service principal) object ID."
  value       = azuread_service_principal.mailbox.object_id
}

output "redirect_uri" {
  description = "Registered Web callback URL."
  value       = var.redirect_uri
}

output "key_vault_uri" {
  description = "Vault URI for EMAIL_KEY_VAULT_URL."
  value       = azurerm_key_vault.email.vault_uri
}

output "key_vault_id" {
  description = "Resource ID of the dedicated mailbox Key Vault."
  value       = azurerm_key_vault.email.id
}

output "client_secret_name" {
  description = "Key Vault secret name holding the Entra client secret."
  value       = var.client_secret_name
}

output "client_secret_expiration" {
  description = "Expiration of the current Entra client secret; rotate before this date."
  value       = azuread_application_password.mailbox.end_date
}

output "encryption_key_name" {
  description = "Key Vault secret name holding the Fernet token-encryption key."
  value       = var.encryption_key_name
}

output "api_identity_principal_id" {
  description = "System-assigned managed identity principal ID granted Key Vault Secrets User."
  value       = azapi_update_resource.api_email_config.output.identity.principalId
}

output "email_backend_settings" {
  description = "Non-secret EMAIL_* settings applied to the API (values are config names, not secrets)."
  value       = local.api_email_settings
}

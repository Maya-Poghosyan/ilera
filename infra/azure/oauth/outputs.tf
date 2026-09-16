# Non-secret outputs: resource names/IDs, the callback URL, and config names — never
# secret values. The scanning module reads key_vault_id, key_vault_uri, and
# api_identity_principal_id from this module's remote state.

output "mailbox_client_id" {
  description = "Client ID of the (externally managed) mailbox Entra app used for EMAIL_MICROSOFT_CLIENT_ID."
  value       = var.mailbox_client_id
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
  description = "Key Vault secret name holding the (externally written) Entra client secret."
  value       = var.client_secret_name
}

output "encryption_key_name" {
  description = "Key Vault secret name holding the Fernet token-encryption key."
  value       = var.encryption_key_name
}

output "api_identity_principal_id" {
  description = "System-assigned managed identity principal ID granted Key Vault Secrets User."
  value       = data.azapi_resource.api_identity.output.identity.principalId
}

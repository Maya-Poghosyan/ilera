# Dedicated Key Vault for mailbox secrets.
#
# Replaces the `az keyvault create` path in setup_email.py, plus the HIPAA hardening the
# Python bootstrap explicitly deferred ("private networking is not provisioned by this
# bootstrap. Revisit network boundaries before rollout.").
#
# Hardened defaults:
#   - RBAC authorization (no legacy access policies)
#   - purge protection ON (a deleted vault cannot be purged early — protects key material)
#   - soft-delete retention 90 days
#   - network ACLs default-deny with Azure trusted services allowed
#   - diagnostic settings stream audit events to Log Analytics (see hipaa.tf)

resource "azurerm_key_vault" "email" {
  name                = var.vault_name
  location            = var.location
  resource_group_name = var.resource_group
  tenant_id           = var.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 90

  public_network_access_enabled = var.key_vault_public_network_access_enabled

  network_acls {
    # Default deny. Only Azure trusted services (which includes the Container Apps
    # managed identity path) and any explicitly listed operator IP ranges get through.
    default_action             = "Deny"
    bypass                     = "AzureServices"
    ip_rules                   = var.key_vault_allowed_ip_ranges
    virtual_network_subnet_ids = []
  }

  tags = var.tags
}

# --- Bootstrap RBAC ----------------------------------------------------------
# The operator/CI principal running `terraform apply` needs write access to create the
# secrets. Secrets Officer (not Administrator) — enough to set secrets, not to rewrite
# the vault's access model. This mirrors the Python script granting the signed-in user
# Key Vault Secrets Officer, and it is separate from the app's runtime Secrets User role.
resource "azurerm_role_assignment" "operator_secrets_officer" {
  name               = uuidv5("url", "${local.role_assignment_scope}${data.azuread_client_config.current.object_id}${local.role_secrets_officer_id}")
  scope              = azurerm_key_vault.email.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_secrets_officer_id}"
  principal_id       = data.azuread_client_config.current.object_id
}

# --- Fernet token-encryption key --------------------------------------------
# URL-safe base64 of 32 random bytes, matching setup_email's
# base64.urlsafe_b64encode(secrets.token_bytes(32)). random_bytes keeps the raw value in
# state only (never in plan output). Rotation: add a new version and re-encrypt DB
# ciphertext before disabling the old version — never destroy a version still referenced.
resource "random_bytes" "token_encryption_key" {
  length = 32
}

resource "azurerm_key_vault_secret" "token_encryption_key" {
  name = var.encryption_key_name
  # Fernet requires URL-safe base64 of 32 raw bytes. random_bytes.base64 is STANDARD
  # base64 (+ and /), so translate to the URL-safe alphabet (- and _). Length is 44
  # chars with a single '=' pad, which Fernet accepts.
  value        = replace(replace(random_bytes.token_encryption_key.base64, "+", "-"), "/", "_")
  key_vault_id = azurerm_key_vault.email.id
  content_type = "fernet-key"

  # Preserve existing key material: if the secret already exists (e.g. imported from the
  # Python-era vault), do not let a value drift here silently re-key the mailbox tokens.
  lifecycle {
    ignore_changes = [value]
  }

  depends_on = [azurerm_role_assignment.operator_secrets_officer]

  tags = var.tags
}

# --- Microsoft application client secret -------------------------------------
# NOT managed here. The Entra app and its secret are managed outside Terraform (see
# entra.tf). Write the client-secret VALUE into this vault as var.client_secret_name
# out-of-band. Terraform only references the name via the API config, and grants the API
# identity read access below.


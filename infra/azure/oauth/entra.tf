# Mailbox OAuth identity (Microsoft Graph, delegated).
#
# Replaces the `az ad app create` / `az ad sp create` / `az ad app credential reset`
# path in setup_email.py. Single-tenant (AzureADMyOrg): consumer Outlook.com accounts
# are intentionally unsupported by this slice. Delegated Mail.Read only — no mail-write,
# no send, no directory-wide or application-mailbox permissions.

resource "azuread_application" "mailbox" {
  display_name     = var.mailbox_app_name
  sign_in_audience = "AzureADMyOrg"

  # Web redirect (authorization code flow), NOT an SPA redirect.
  web {
    redirect_uris = [var.redirect_uri]
  }

  required_resource_access {
    resource_app_id = local.msgraph_app_id # Microsoft Graph

    # Delegated scope: read the signed-in user's mail.
    resource_access {
      id   = local.msgraph_scope_ids["Mail.Read"]
      type = "Scope"
    }
    resource_access {
      id   = local.msgraph_scope_ids["openid"]
      type = "Scope"
    }
    resource_access {
      id   = local.msgraph_scope_ids["profile"]
      type = "Scope"
    }
    # offline_access = long-lived refresh tokens, required to refresh without re-consent.
    resource_access {
      id   = local.msgraph_scope_ids["offline_access"]
      type = "Scope"
    }
  }

  tags = ["ilera", "email-scanning", "hipaa"]
}

# The enterprise application (service principal) in this tenant. Consent remains a
# separate user/admin flow; creating the SP does not grant consent.
resource "azuread_service_principal" "mailbox" {
  client_id = azuread_application.mailbox.client_id
}

# Rotating client secret. Terraform manages the lifetime; the VALUE is written to Key
# Vault below and never printed. rotate_when_changed forces a fresh secret when the
# rotation window elapses. The value transits Terraform state once — keep state in the
# encrypted azurerm backend (see README), never local for production.
resource "time_rotating" "client_secret" {
  rotation_days = var.client_secret_rotation_days
}

resource "azuread_application_password" "mailbox" {
  application_id = azuread_application.mailbox.id
  display_name   = "ilera-mailbox-keyvault"
  end_date       = timeadd(time_rotating.client_secret.rotation_rfc3339, "${var.client_secret_rotation_days * 24}h")

  rotate_when_changed = {
    rotation = time_rotating.client_secret.id
  }
}

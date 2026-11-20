# Intake document assistance — a dedicated Azure OpenAI account.
#
# Uploaded intake documents (pay stubs, tax forms, benefit letters) carry PHI, so they get
# their own account, separate from eligibility research (ilera-resource) and email
# scanning. The API reads it with its system-assigned managed identity; key auth is off.
#
# The app settings are NOT written here (the API's template is owned by the deploy
# workflow — see api.tf). Set them on the API Container App from the outputs below:
#   DOCUMENT_OPENAI_ENDPOINT   = document_openai_endpoint
#   DOCUMENT_OPENAI_DEPLOYMENT = document_openai_deployment
#   (The API's system-assigned identity needs no client id.)
#
# HIPAA, outside Terraform: this account must be covered by the Microsoft BAA and have
# abuse monitoring / content logging opted out (Modified Abuse Monitoring request) before
# real documents are processed.

resource "azurerm_cognitive_account" "documents" {
  name                  = "ilera-documents-openai"
  location              = var.location
  resource_group_name   = var.resource_group
  kind                  = "OpenAI" # serves https://<subdomain>.openai.azure.com natively
  sku_name              = "S0"
  custom_subdomain_name = "ilera-documents-01a341d5"

  local_auth_enabled                 = false # managed identity only, no shared keys
  public_network_access_enabled      = true  # the API egresses publicly; Entra auth gates access
  outbound_network_access_restricted = true

  tags = var.tags
}

# Vision-capable model. DataZoneStandard keeps processing inside the US data zone.
resource "azurerm_cognitive_deployment" "documents" {
  name                   = "gpt-5-mini"
  cognitive_account_id   = azurerm_cognitive_account.documents.id
  version_upgrade_option = "NoAutoUpgrade"

  model {
    format  = "OpenAI"
    name    = "gpt-5-mini"
    version = "2025-08-07"
  }

  sku {
    name     = "DataZoneStandard"
    capacity = 100 # thousand tokens/minute; covers the app's 300 documents/hour/replica limit
  }
}

resource "azurerm_role_assignment" "api_documents_openai_user" {
  scope                = azurerm_cognitive_account.documents.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = data.azapi_resource.api_identity.output.identity.principalId
}

# Audit trail of control-plane and auth events (no prompt or document content).
resource "azurerm_monitor_diagnostic_setting" "documents_openai" {
  name                       = "ilera-documents-openai-audit"
  target_resource_id         = azurerm_cognitive_account.documents.id
  log_analytics_workspace_id = local.log_analytics_workspace_id

  enabled_log {
    category_group = "audit"
  }
}

output "document_openai_endpoint" {
  description = "DOCUMENT_OPENAI_ENDPOINT for the API Container App."
  value       = "https://${azurerm_cognitive_account.documents.custom_subdomain_name}.openai.azure.com"
}

output "document_openai_deployment" {
  description = "DOCUMENT_OPENAI_DEPLOYMENT for the API Container App."
  value       = azurerm_cognitive_deployment.documents.name
}

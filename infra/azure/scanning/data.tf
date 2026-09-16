# Read what the OAuth module created (vault, API identity) from its remote state, plus
# the existing Container Apps environment and existing Azure OpenAI account.

data "terraform_remote_state" "oauth" {
  backend = "azurerm"
  config = {
    resource_group_name  = "Ilera"
    storage_account_name = "ileratfstate"
    container_name       = "tfstate"
    key                  = "email-infra.tfstate"
    use_azuread_auth     = true
  }
}

data "azurerm_container_app_environment" "shared" {
  name                = var.container_apps_environment_name
  resource_group_name = var.resource_group
}

# Single Azure OpenAI account — the existing one. The worker calls it with its managed
# identity; no dedicated resource, no API key.
data "azurerm_cognitive_account" "openai" {
  name                = var.existing_openai_account_name
  resource_group_name = var.resource_group
}

locals {
  vault_id                  = data.terraform_remote_state.oauth.outputs.key_vault_id
  api_identity_principal_id = data.terraform_remote_state.oauth.outputs.api_identity_principal_id
  vault_uri                 = data.terraform_remote_state.oauth.outputs.key_vault_uri

  # Built-in role definition GUIDs (stable across Azure).
  role_secrets_user_id = "4633458b-17de-408a-b874-0445c86b69e6" # Key Vault Secrets User
  role_sb_sender_id    = "69a216fc-b8fb-44d8-bc22-1f3c2cd27a39" # Azure Service Bus Data Sender
  role_sb_receiver_id  = "4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0" # Azure Service Bus Data Receiver
  role_openai_user_id  = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd" # Cognitive Services OpenAI User
}

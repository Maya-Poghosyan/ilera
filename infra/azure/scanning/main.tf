# Service Bus, scan worker, and RBAC. No flags: applying this module stands the whole
# pipeline up; a missing input fails at plan/apply.

# --- Service Bus -------------------------------------------------------------
resource "azurerm_servicebus_namespace" "email" {
  name                = "ilera-email-bus"
  location            = var.location
  resource_group_name = var.resource_group
  sku                 = "Standard" # Standard supports duplicate detection; Basic does not.
  local_auth_enabled  = false      # managed identity only, no SAS connection strings
  tags                = var.tags
}

resource "azurerm_servicebus_queue" "scan" {
  name         = "email.scan"
  namespace_id = azurerm_servicebus_namespace.email.id

  # Broker-side dedup over a 10-minute window using the publisher's deterministic message
  # IDs. Does not replace worker idempotency.
  requires_duplicate_detection            = true
  duplicate_detection_history_time_window = "PT10M"

  # After 5 failed peek-lock deliveries the message dead-letters instead of looping.
  max_delivery_count                   = 5
  dead_lettering_on_message_expiration = true

  lock_duration = "PT5M"
}

# API (from the OAuth module) is the sender: it enqueues message identifiers only.
resource "azurerm_role_assignment" "api_sb_sender" {
  name               = uuidv5("url", "${lower(azurerm_servicebus_queue.scan.id)}${local.api_identity_principal_id}${local.role_sb_sender_id}")
  scope              = azurerm_servicebus_queue.scan.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_sb_sender_id}"
  principal_id       = local.api_identity_principal_id
}

# Worker is the receiver: consumes with peek-lock, completes after commit.
resource "azurerm_role_assignment" "worker_sb_receiver" {
  name               = uuidv5("url", "${lower(azurerm_servicebus_queue.scan.id)}${azapi_update_resource.scan_worker_identity.output.identity.principalId}${local.role_sb_receiver_id}")
  scope              = azurerm_servicebus_queue.scan.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_sb_receiver_id}"
  principal_id       = azapi_update_resource.scan_worker_identity.output.identity.principalId
}

# --- Scan worker Container App ----------------------------------------------
resource "azurerm_container_app" "scan_worker" {
  name                         = "ilera-email-worker"
  resource_group_name          = var.resource_group
  container_app_environment_id = data.azurerm_container_app_environment.shared.id
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  template {
    container {
      name    = "worker"
      image   = var.scan_worker_image
      command = ["python", "-m", "app.email_ingestion.worker"]
      cpu     = 0.5
      memory  = "1Gi"

      # Non-secret worker config. Secret material is read from Key Vault at runtime via
      # the worker's managed identity, never injected here.
      env {
        name  = "EMAIL_SERVICE_BUS_NAMESPACE"
        value = "${azurerm_servicebus_namespace.email.name}.servicebus.windows.net"
      }
      env {
        name  = "EMAIL_SERVICE_BUS_QUEUE"
        value = azurerm_servicebus_queue.scan.name
      }
      env {
        name  = "EMAIL_KEY_VAULT_URL"
        value = local.vault_uri
      }
      env {
        name  = "EMAIL_USE_MANAGED_IDENTITY"
        value = "true"
      }
      env {
        name  = "EMAIL_OPENAI_ENDPOINT"
        value = data.azurerm_cognitive_account.openai.endpoint
      }
      env {
        name  = "EMAIL_OPENAI_DEPLOYMENT"
        value = var.email_openai_deployment_name
      }
    }

    min_replicas = 0 # queue-driven; idle at no cost
    max_replicas = 3

    custom_scale_rule {
      name             = "servicebus-scan"
      custom_rule_type = "azure-servicebus"
      metadata = {
        queueName    = azurerm_servicebus_queue.scan.name
        namespace    = azurerm_servicebus_namespace.email.name
        messageCount = "5"
      }
    }
  }

  tags = var.tags

  # The worker image is deployed/rolled forward by CI, like the API. Keep image drift out
  # of this plan so a CI image update and a terraform apply don't fight. (This prevents a
  # silent revert of the running image, not a loud error.)
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# Read the worker identity principalId for the RBAC grants below.
resource "azapi_update_resource" "scan_worker_identity" {
  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = azurerm_container_app.scan_worker.id
  body        = {}

  response_export_values = ["identity.principalId"]
  depends_on             = [azurerm_container_app.scan_worker]
}

# Worker reads mailbox secrets (client secret, Fernet key) from the vault.
resource "azurerm_role_assignment" "worker_secrets_user" {
  name               = uuidv5("url", "${lower(local.vault_id)}${azapi_update_resource.scan_worker_identity.output.identity.principalId}${local.role_secrets_user_id}")
  scope              = local.vault_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_secrets_user_id}"
  principal_id       = azapi_update_resource.scan_worker_identity.output.identity.principalId
}

# Worker calls the existing Azure OpenAI with its managed identity — no shared key.
resource "azurerm_role_assignment" "worker_openai_user" {
  name               = uuidv5("url", "${lower(data.azurerm_cognitive_account.openai.id)}${azapi_update_resource.scan_worker_identity.output.identity.principalId}${local.role_openai_user_id}")
  scope              = data.azurerm_cognitive_account.openai.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_openai_user_id}"
  principal_id       = azapi_update_resource.scan_worker_identity.output.identity.principalId
}

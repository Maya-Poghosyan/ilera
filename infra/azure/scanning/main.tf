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
  name               = uuidv5("url", "${lower(azurerm_servicebus_queue.scan.id)}${azurerm_user_assigned_identity.scan_worker.principal_id}${local.role_sb_receiver_id}")
  scope              = azurerm_servicebus_queue.scan.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_sb_receiver_id}"
  principal_id       = azurerm_user_assigned_identity.scan_worker.principal_id
}

# The maintenance job (subscriptions + reconciliation) runs under the same worker identity
# and enqueues gap message identifiers during reconciliation, so it also needs Sender.
resource "azurerm_role_assignment" "worker_sb_sender" {
  name               = uuidv5("url", "${lower(azurerm_servicebus_queue.scan.id)}${azurerm_user_assigned_identity.scan_worker.principal_id}${local.role_sb_sender_id}")
  scope              = azurerm_servicebus_queue.scan.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_sb_sender_id}"
  principal_id       = azurerm_user_assigned_identity.scan_worker.principal_id
}
# A user-assigned identity created up front so AcrPull can be granted BEFORE the container
# app tries its first image pull. A system-assigned identity would not exist until the app
# is created, deadlocking the initial pull.
resource "azurerm_user_assigned_identity" "scan_worker" {
  name                = "ilera-email-worker-id"
  resource_group_name = var.resource_group
  location            = var.location
  tags                = var.tags
}

# The worker pulls its image from ACR using the user-assigned identity.
resource "azurerm_role_assignment" "worker_acr_pull" {
  name               = uuidv5("url", "${lower(data.azurerm_container_registry.acr.id)}${azurerm_user_assigned_identity.scan_worker.principal_id}${local.role_acr_pull_id}")
  scope              = data.azurerm_container_registry.acr.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_acr_pull_id}"
  principal_id       = azurerm_user_assigned_identity.scan_worker.principal_id
}

# --- Scan worker Container App ----------------------------------------------
resource "azurerm_container_app" "scan_worker" {
  name                         = "ilera-email-worker"
  resource_group_name          = var.resource_group
  container_app_environment_id = data.azurerm_container_app_environment.shared.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.scan_worker.id]
  }

  # Authenticate the image pull with the same user-assigned identity (which holds AcrPull).
  registry {
    server   = local.acr_login_server
    identity = azurerm_user_assigned_identity.scan_worker.id
  }

  secret {
    name  = "database-url"
    value = var.database_url
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
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "EMAIL_CONNECTIONS_ENABLED"
        value = "true"
      }
      env {
        name  = "EMAIL_SCANNING_ENABLED"
        value = var.email_scanning_enabled
      }
      env {
        name  = "EMAIL_MICROSOFT_TENANT_ID"
        value = var.mailbox_tenant_id
      }
      env {
        name  = "EMAIL_MICROSOFT_CLIENT_ID"
        value = var.mailbox_client_id
      }
      env {
        name  = "EMAIL_MICROSOFT_REDIRECT_URI"
        value = var.mailbox_redirect_uri
      }
      env {
        name  = "EMAIL_MICROSOFT_CLIENT_SECRET_NAME"
        value = "ilera-microsoft-client-secret"
      }
      env {
        name  = "EMAIL_TOKEN_ENCRYPTION_KEY_NAME"
        value = "ilera-email-token-key"
      }
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
      # The worker's managed identity is user-assigned; tell the SDKs which client id to use.
      env {
        name  = "EMAIL_MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.scan_worker.client_id
      }
      env {
        name = "EMAIL_OPENAI_ENDPOINT"
        # The extractor requires an *.openai.azure.com endpoint. An AIServices/OpenAI
        # account's default endpoint is *.cognitiveservices.azure.com, but the same
        # account also serves the OpenAI API under its custom subdomain on
        # openai.azure.com. Derive that form from the custom subdomain.
        value = "https://${data.azurerm_cognitive_account.openai.custom_subdomain_name}.openai.azure.com/"
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

  # AcrPull must exist before the first image pull during app creation.
  depends_on = [azurerm_role_assignment.worker_acr_pull]

  # The worker image is deployed/rolled forward by CI, like the API. Keep image drift out
  # of this plan so a CI image update and a terraform apply don't fight. (This prevents a
  # silent revert of the running image, not a loud error.)
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# Worker reads mailbox secrets (client secret, Fernet key) from the vault.
resource "azurerm_role_assignment" "worker_secrets_user" {
  name               = uuidv5("url", "${lower(local.vault_id)}${azurerm_user_assigned_identity.scan_worker.principal_id}${local.role_secrets_user_id}")
  scope              = local.vault_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_secrets_user_id}"
  principal_id       = azurerm_user_assigned_identity.scan_worker.principal_id
}

# Worker calls the existing Azure OpenAI with its managed identity — no shared key.
resource "azurerm_role_assignment" "worker_openai_user" {
  name               = uuidv5("url", "${lower(data.azurerm_cognitive_account.openai.id)}${azurerm_user_assigned_identity.scan_worker.principal_id}${local.role_openai_user_id}")
  scope              = data.azurerm_cognitive_account.openai.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_openai_user_id}"
  principal_id       = azurerm_user_assigned_identity.scan_worker.principal_id
}

# --- Subscription/reconciliation maintenance job ----------------------------
# Hourly Container Apps job that renews Graph subscriptions, reconciles missed
# notifications, and prunes orphaned subscriptions. Runs the full API image (which has the
# whole app) under the worker's user-assigned identity (Key Vault read + Service Bus send).
# It is effective only when EMAIL_SCANNING_ENABLED=true; otherwise it exits with a fixed
# "unavailable" outcome by design.
resource "azurerm_container_app_job" "maintenance" {
  name                         = "ilera-email-maint"
  resource_group_name          = var.resource_group
  location                     = var.location
  container_app_environment_id = data.azurerm_container_app_environment.shared.id

  replica_timeout_in_seconds = 600
  replica_retry_limit        = 1

  schedule_trigger_config {
    cron_expression          = "0 * * * *"
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.scan_worker.id]
  }

  registry {
    server   = local.acr_login_server
    identity = azurerm_user_assigned_identity.scan_worker.id
  }

  secret {
    name  = "database-url"
    value = var.database_url
  }

  template {
    container {
      name    = "maint"
      image   = var.api_image
      command = ["python"]
      args    = ["-m", "app.email_ingestion.subscriptions"]
      cpu     = 0.5
      memory  = "1Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "EMAIL_MICROSOFT_TENANT_ID"
        value = var.mailbox_tenant_id
      }
      env {
        name  = "EMAIL_MICROSOFT_CLIENT_ID"
        value = var.mailbox_client_id
      }
      env {
        name  = "EMAIL_MICROSOFT_REDIRECT_URI"
        value = var.mailbox_redirect_uri
      }
      env {
        name  = "EMAIL_KEY_VAULT_URL"
        value = local.vault_uri
      }
      env {
        name  = "EMAIL_MICROSOFT_CLIENT_SECRET_NAME"
        value = "ilera-microsoft-client-secret"
      }
      env {
        name  = "EMAIL_TOKEN_ENCRYPTION_KEY_NAME"
        value = "ilera-email-token-key"
      }
      env {
        name  = "EMAIL_USE_MANAGED_IDENTITY"
        value = "true"
      }
      env {
        name  = "EMAIL_MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.scan_worker.client_id
      }
      env {
        name  = "EMAIL_CONNECTIONS_ENABLED"
        value = "true"
      }
      # Flipped to true only after BAA/abuse-monitoring confirmation and validation.
      env {
        name  = "EMAIL_SCANNING_ENABLED"
        value = var.email_scanning_enabled
      }
      env {
        name  = "EMAIL_SERVICE_BUS_NAMESPACE"
        value = "${azurerm_servicebus_namespace.email.name}.servicebus.windows.net"
      }
      env {
        name  = "EMAIL_SERVICE_BUS_QUEUE"
        value = azurerm_servicebus_queue.scan.name
      }
      env {
        name  = "EMAIL_MICROSOFT_NOTIFICATION_URL"
        value = var.email_microsoft_notification_url
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.worker_acr_pull,
    azurerm_role_assignment.worker_sb_sender,
    azurerm_role_assignment.worker_secrets_user,
  ]

  tags = var.tags

  # CI rolls the image forward; keep it out of the plan like the worker/API.
  lifecycle {
    ignore_changes = [template[0].container[0].image, template[0].container[0].env]
  }
}

# Scheduled jobs for the API's own housekeeping, run from the API image (app/jobs) so they
# fire once per schedule no matter how many API replicas are serving.
#
# They reuse the worker identity (already has AcrPull) and the same database-url input as
# the maintenance job. Like that job, the image is var.api_image: bump it to an image that
# contains app/jobs/<module> before applying.

resource "azurerm_container_app_job" "purge_unclaimed" {
  name                         = "ilera-purge-unclaimed"
  resource_group_name          = var.resource_group
  location                     = var.location
  container_app_environment_id = data.azurerm_container_app_environment.shared.id

  replica_timeout_in_seconds = 300
  replica_retry_limit        = 1

  # Daily, off-peak for US time zones (10:00 UTC = 3am PT).
  schedule_trigger_config {
    cron_expression          = "0 10 * * *"
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
      name    = "purge"
      image   = var.api_image
      command = ["python"]
      args    = ["-m", "app.jobs.purge_unclaimed_cases"]
      cpu     = 0.25
      memory  = "0.5Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      # Matches the API's default; set here so changing the retention window is one edit.
      env {
        name  = "UNCLAIMED_CASE_TTL_DAYS"
        value = "5"
      }
    }
  }

  tags = var.tags

  depends_on = [azurerm_role_assignment.worker_acr_pull]
}

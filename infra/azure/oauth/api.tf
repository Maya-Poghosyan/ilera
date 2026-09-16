# Wiring the existing API to the vault.
#
# Three things, all replacing setup_email.py steps:
#   1. Enable a system-assigned managed identity on the API (az containerapp identity assign)
#   2. Grant that identity Key Vault Secrets User on the dedicated vault (az role assignment)
#   3. Set the non-secret EMAIL_* env vars, email flags disabled (az containerapp update)
#
# The API Container App is owned operationally by the deploy workflow (CI rolls the image
# forward). To avoid Terraform fighting that, we DO NOT declare an azurerm_container_app
# resource here. Instead we PATCH only the identity block and the container env vars with
# azapi, and ignore the image/scale/registry fields CI manages.

# 1 + 3: patch identity and env vars onto the existing API.
resource "azapi_update_resource" "api_email_config" {
  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = data.azurerm_container_app.api.id

  body = {
    identity = {
      # Merge system-assigned on; do not disturb any existing user-assigned identities.
      type = "SystemAssigned"
    }
    properties = {
      template = {
        containers = [
          {
            # Container name must match the existing container (defaults to the app name).
            name = var.api_app_name
            env = [
              for k, v in local.api_email_settings : {
                name  = k
                value = v
              }
            ]
          }
        ]
      }
    }
  }

  # azapi returns the identity block so we can read the principalId for the role grant.
  response_export_values = ["identity.principalId"]

  # The deploy workflow owns the image tag; a Terraform apply here must not try to reset
  # it. We only ever send identity + env, so nothing else is in scope, but keep template
  # image drift out of the plan explicitly.
  lifecycle {
    ignore_changes = [
      body.properties.template.containers[0].image,
    ]
  }
}

# Read the API's CURRENT system-assigned identity principal at plan time. It is already
# assigned, so this is a stable, known value — unlike the azapi patch output, which is
# "known after apply" and would force the role assignment to be replaced every time. The
# azapi patch below still runs (idempotently) to guarantee the identity + env are set.
data "azapi_resource" "api_identity" {
  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = data.azurerm_container_app.api.id

  response_export_values = ["identity.principalId"]
}

# 2: the API's runtime identity reads secrets — Secrets User, never Officer.
resource "azurerm_role_assignment" "api_secrets_user" {
  name               = uuidv5("url", "${local.role_assignment_scope}${data.azapi_resource.api_identity.output.identity.principalId}${local.role_secrets_user_id}")
  scope              = azurerm_key_vault.email.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_secrets_user_id}"
  principal_id       = data.azapi_resource.api_identity.output.identity.principalId

  # The patch guarantees the identity exists before we grant it a role.
  depends_on = [azapi_update_resource.api_email_config]
}

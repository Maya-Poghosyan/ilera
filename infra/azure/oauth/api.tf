# Wiring the existing API to the vault.
#
# The API Container App is owned operationally by the deploy workflow (CI rolls its image
# AND its container template, including env vars and Key Vault secret references). This
# module must NOT write the container app: a PUT with a partial body drops the app's
# existing secrets (jwt-secret, database-url, the ACR pull secret, …) and Azure rejects it
# with ContainerAppSecretInvalid. So Terraform does two read-only-friendly things here:
#
#   1. READ the API's system-assigned identity (already assigned) to get its principal ID.
#   2. GRANT that identity Key Vault Secrets User on the dedicated vault.
#
# The EMAIL_* runtime settings belong to the APP deployment, not this infra module. They
# are defined with safe defaults in backend/app/config.py (both email flags default false),
# so the app boots without them; set them via the app's deployment when enabling email.

# Read the API's current system-assigned identity principal. Stable, known at plan time.
data "azapi_resource" "api_identity" {
  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = data.azurerm_container_app.api.id

  response_export_values = ["identity.principalId"]
}

# The API's runtime identity reads secrets — Secrets User, never Officer.
resource "azurerm_role_assignment" "api_secrets_user" {
  name               = uuidv5("url", "${local.role_assignment_scope}${data.azapi_resource.api_identity.output.identity.principalId}${local.role_secrets_user_id}")
  scope              = azurerm_key_vault.email.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.role_secrets_user_id}"
  principal_id       = data.azapi_resource.api_identity.output.identity.principalId
}

# HIPAA hardening.
#
# The Python bootstrap explicitly deferred this ("private networking is not provisioned
# by this bootstrap. Revisit network boundaries before rollout."). This file adds the
# audit-logging and network-boundary controls a HIPAA posture expects.
#
# Compliance is a shared-responsibility posture, not a single resource. The controls
# here address the technical safeguards in the HIPAA Security Rule that Terraform can
# express: audit controls (§164.312(b)), access control (§164.312(a)), and transmission
# security (§164.312(e)). The administrative safeguards — a signed Microsoft BAA, access
# reviews, breach procedures — live outside Terraform. See README.

# --- Audit logging (§164.312(b)) ---------------------------------------------
# Reuse an existing workspace if provided; otherwise create one.
#
# NOTE on retention: a Log Analytics workspace's interactive retention is capped at 730
# days by Azure. Longer HIPAA audit retention (commonly cited as 6 years) is achieved by
# archiving beyond 730 days — either per-table archive tier or continuous export to a
# storage account with an immutability/retention policy. That archive is a separate
# resource decision (and cost tradeoff); this workspace holds the interactive window.
resource "azurerm_log_analytics_workspace" "email" {
  count               = var.log_analytics_workspace_id == "" ? 1 : 0
  name                = "ilera-email-logs"
  location            = var.location
  resource_group_name = var.resource_group
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = var.tags
}

locals {
  log_analytics_workspace_id = (
    var.log_analytics_workspace_id != ""
    ? var.log_analytics_workspace_id
    : azurerm_log_analytics_workspace.email[0].id
  )
}

# Stream Key Vault audit events (every secret read/write, every auth decision) to Log
# Analytics. This is the audit trail proving which identity read the mailbox secrets and
# when — essential for a HIPAA access-audit.
resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "ilera-email-kv-audit"
  target_resource_id         = azurerm_key_vault.email.id
  log_analytics_workspace_id = local.log_analytics_workspace_id

  enabled_log {
    category = "AuditEvent"
  }
  enabled_log {
    category = "AzurePolicyEvaluationDetails"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

# Provider and version pinning.
#
# azurerm manages the ARM control plane (Key Vault, Container Apps, Service Bus,
# Cognitive Services, diagnostics, RBAC role assignments). azuread manages the
# Entra objects (the mailbox application registration and its service principal),
# which live in Microsoft Graph, not ARM.
#
# Versions are pinned with pessimistic constraints so `terraform init` in CI and on
# a laptop resolve the same major/minor line. Bump deliberately and re-run plan.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    azapi = {
      # Used to patch identity + env vars onto the existing API Container App WITHOUT
      # taking ownership of its image/scale (those stay with the deploy workflow).
      source  = "azure/azapi"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # Remote state: the single source of truth, shared by CI and operators, with locking.
  # We do NOT use local state — the client secret and Fernet key transit state, so it
  # lives in an encrypted, access-controlled Azure Storage container. The backing storage
  # must exist before `terraform init` (one-time bootstrap in the README). State lives in
  # the existing Ilera resource group to keep everything consolidated.
  #
  # For validate-only steps (CI lint, local syntax checks) that must not touch Azure, run
  # `terraform init -backend=false` to skip backend initialization.
  backend "azurerm" {
    resource_group_name  = "Ilera"
    storage_account_name = "ileratfstate"
    container_name       = "tfstate"
    key                  = "email-infra.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  # Never disables purge protection or soft-delete on destroy — HIPAA-relevant key
  # material must survive an accidental `terraform destroy`.
  features {
    key_vault {
      purge_soft_delete_on_destroy          = false
      purge_soft_deleted_secrets_on_destroy = false
      recover_soft_deleted_key_vaults       = true
      recover_soft_deleted_secrets          = true
    }
    cognitive_account {
      purge_soft_delete_on_destroy = false
    }
  }

  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

provider "azuread" {
  tenant_id = var.tenant_id
}

provider "azapi" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

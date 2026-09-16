# Scanning pipeline — Service Bus + scan worker + OpenAI wiring.
#
# This is a SEPARATE root module from the OAuth slice one directory up. Apply it when the
# scan worker image exists and you're ready to stand up the pipeline. There is no
# enable/disable flag: if a required input (worker image, OpenAI account) is missing,
# `apply` fails loudly rather than provisioning half a pipeline.
#
# It reads the vault and API identity created by the OAuth module via that module's
# remote state (see data.tf), so apply the OAuth module first.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "Ilera"
    storage_account_name = "ileratfstate"
    container_name       = "tfstate"
    key                  = "email-scanning.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

provider "azapi" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

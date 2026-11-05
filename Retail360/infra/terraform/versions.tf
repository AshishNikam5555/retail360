terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.10"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.50"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }

  subscription_id     = var.subscription_id
  tenant_id           = var.tenant_id
  storage_use_azuread = true
}

# Workspace-level provider. The host comes from the workspace created in this same root module,
# so the first run needs a two-phase apply (-target=azurerm_databricks_workspace.this). See README.
provider "databricks" {
  host = "https://${azurerm_databricks_workspace.this.workspace_url}"
}

data "azurerm_client_config" "current" {}

locals {
  base_name  = "${var.name_prefix}-${var.environment}"
  containers = ["landing", "bronze", "silver", "gold", "checkpoints"]
  schemas    = ["bronze", "silver", "gold", "ops"]
  tags = merge(
    { project = "retail360", environment = var.environment, managed_by = "terraform" },
    var.tags,
  )
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.base_name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.base_name}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = local.tags
}

# --- ADLS Gen2 ---------------------------------------------------------------
resource "azurerm_storage_account" "lake" {
  name                            = "st${var.name_prefix}${var.environment}dl"
  resource_group_name             = azurerm_resource_group.this.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = var.storage_replication_type
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  tags                            = local.tags

  blob_properties {
    delete_retention_policy {
      days = var.soft_delete_days
    }
    container_delete_retention_policy {
      days = var.soft_delete_days
    }
  }
}

resource "azurerm_storage_container" "this" {
  for_each              = toset(local.containers)
  name                  = each.key
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.lake.id

  rule {
    name    = "expire-landing"
    enabled = true
    filters {
      prefix_match = ["landing/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
        delete_after_days_since_modification_greater_than       = var.landing_retention_days
      }
    }
  }
}

# --- Databricks --------------------------------------------------------------
resource "azurerm_databricks_workspace" "this" {
  name                        = "dbw-${local.base_name}"
  resource_group_name         = azurerm_resource_group.this.name
  location                    = var.location
  sku                         = "premium"
  managed_resource_group_name = "rg-${local.base_name}-dbw-managed"
  tags                        = local.tags
}

resource "azurerm_databricks_access_connector" "this" {
  name                = "dbac-${local.base_name}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }
}

# --- Event Hubs --------------------------------------------------------------
resource "azurerm_eventhub_namespace" "this" {
  name                = "evhns-${local.base_name}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  sku                 = "Standard"
  capacity            = 1
  minimum_tls_version = "1.2"
  tags                = local.tags
}

resource "azurerm_eventhub" "pos" {
  name              = "pos-transactions"
  namespace_id      = azurerm_eventhub_namespace.this.id
  partition_count   = var.eventhub_partition_count
  message_retention = 1
}

resource "azurerm_eventhub_consumer_group" "databricks" {
  name                = "databricks"
  namespace_name      = azurerm_eventhub_namespace.this.name
  eventhub_name       = azurerm_eventhub.pos.name
  resource_group_name = azurerm_resource_group.this.name
}

# --- Key Vault (RBAC) --------------------------------------------------------
resource "azurerm_key_vault" "this" {
  name                       = "kv-${local.base_name}"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 30
  tags                       = local.tags
}

resource "azurerm_role_assignment" "deployer_kv_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Placeholder secrets: real values are set out-of-band and never stored in Terraform state.
resource "azurerm_key_vault_secret" "placeholder" {
  for_each     = toset(["eventhub-connection-string", "sql-source-password", "sftp-source-password"])
  name         = each.key
  value        = "<set-out-of-band>"
  key_vault_id = azurerm_key_vault.this.id

  lifecycle {
    ignore_changes = [value]
  }

  depends_on = [azurerm_role_assignment.deployer_kv_officer]
}

# --- Least-privilege RBAC ----------------------------------------------------
resource "azurerm_role_assignment" "connector_storage" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.this.identity[0].principal_id
}

resource "azurerm_role_assignment" "sp_kv_secrets" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.service_principal_object_id
}

resource "azurerm_role_assignment" "sp_eventhub_receiver" {
  scope                = azurerm_eventhub.pos.id
  role_definition_name = "Azure Event Hubs Data Receiver"
  principal_id         = var.service_principal_object_id
}

# --- Diagnostics -------------------------------------------------------------
resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "diag-keyvault"
  target_resource_id         = azurerm_key_vault.this.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category_group = "audit"
  }
}

resource "azurerm_monitor_diagnostic_setting" "eventhubs" {
  name                       = "diag-eventhubs"
  target_resource_id         = azurerm_eventhub_namespace.this.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category_group = "allLogs"
  }
}

# --- Unity Catalog -----------------------------------------------------------
resource "databricks_storage_credential" "lake" {
  name = "cred-${local.base_name}"

  azure_managed_identity {
    access_connector_id = azurerm_databricks_access_connector.this.id
  }

  depends_on = [azurerm_role_assignment.connector_storage]
}

resource "databricks_external_location" "this" {
  for_each        = toset(local.containers)
  name            = "extloc-${each.key}-${var.environment}"
  url             = "abfss://${each.key}@${azurerm_storage_account.lake.name}.dfs.core.windows.net/"
  credential_name = databricks_storage_credential.lake.name
}

resource "databricks_catalog" "this" {
  name         = "retail360_${var.environment}"
  storage_root = "abfss://gold@${azurerm_storage_account.lake.name}.dfs.core.windows.net/managed"
  comment      = "Retail360 ${var.environment} (fictional portfolio project)"

  depends_on = [databricks_external_location.this]
}

resource "databricks_schema" "this" {
  for_each     = toset(local.schemas)
  catalog_name = databricks_catalog.this.name
  name         = each.key
}

resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.this.name

  grant {
    principal  = var.group_data_engineers
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE", "CREATE_SCHEMA"]
  }
  grant {
    principal  = var.service_principal_application_id
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT", "MODIFY", "CREATE_TABLE"]
  }
  grant {
    principal  = var.group_data_analysts
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT"]
  }
  grant {
    principal  = var.group_data_scientists
    privileges = ["USE_CATALOG", "USE_SCHEMA", "SELECT"]
  }
}

output "workspace_url" {
  description = "Databricks workspace URL."
  value       = "https://${azurerm_databricks_workspace.this.workspace_url}"
}

output "storage_account_name" {
  description = "ADLS Gen2 account name."
  value       = azurerm_storage_account.lake.name
}

output "catalog_name" {
  description = "Unity Catalog catalog."
  value       = databricks_catalog.this.name
}

output "key_vault_uri" {
  description = "Key Vault URI."
  value       = azurerm_key_vault.this.vault_uri
}

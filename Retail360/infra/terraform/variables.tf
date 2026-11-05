variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be one of dev, test, prod."
  }
}

variable "subscription_id" {
  description = "Azure subscription id (placeholder in examples)."
  type        = string
}

variable "tenant_id" {
  description = "Azure AD tenant id (placeholder in examples)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "uksouth"
}

variable "name_prefix" {
  description = "Short prefix for globally unique names (3-8 lowercase alphanumerics)."
  type        = string
  default     = "r360"
}

variable "tags" {
  description = "Extra tags merged into the standard tag set."
  type        = map(string)
  default     = {}
}

variable "storage_replication_type" {
  description = "Storage replication (LRS/ZRS/GRS...)."
  type        = string
  default     = "LRS"
}

variable "soft_delete_days" {
  description = "Soft-delete retention (days) for blobs and containers."
  type        = number
  default     = 14
}

variable "landing_retention_days" {
  description = "Days after which landing files are deleted by lifecycle policy."
  type        = number
  default     = 90
}

variable "eventhub_partition_count" {
  description = "Partitions for the pos-transactions hub."
  type        = number
  default     = 4
}

variable "eventhub_retention_days" {
  description = "Message retention in days for the hub."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "Log Analytics retention in days."
  type        = number
  default     = 30
}

variable "group_data_engineers" {
  description = "Account-level group name for data engineers."
  type        = string
  default     = "retail360-data-engineers"
}

variable "group_data_analysts" {
  description = "Account-level group name for data analysts."
  type        = string
  default     = "retail360-data-analysts"
}

variable "group_data_scientists" {
  description = "Account-level group name for data scientists."
  type        = string
  default     = "retail360-data-scientists"
}

variable "service_principal_application_id" {
  description = "Application (client) id of the pipeline service principal, used in Unity Catalog grants."
  type        = string
}

variable "service_principal_object_id" {
  description = "Object id of the pipeline service principal, used for Azure RBAC."
  type        = string
}

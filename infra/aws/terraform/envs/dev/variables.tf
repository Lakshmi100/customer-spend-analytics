###############################################################################
# Inputs for the dev environment.
# Set these in terraform.tfvars (NOT committed to Git).
###############################################################################

variable "aws_region" {
  description = "AWS region — must match the bootstrap region"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "12-digit AWS account ID"
  type        = string
  validation {
    condition     = length(var.aws_account_id) == 12 && can(regex("^[0-9]+$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit number."
  }
}

variable "project_name" {
  description = "Project prefix for resource names (kept short — S3 bucket names have a 63-char limit)"
  type        = string
  default     = "csa"
}

variable "environment" {
  description = "Environment name (dev, staging, prod). Used as a tag and in resource names."
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Owner tag for cost tracking"
  type        = string
  default     = "lakshmi"
}

###############################################################################
# Snowflake credentials — stored in Secrets Manager
# These are SENSITIVE. NEVER commit terraform.tfvars to Git.
###############################################################################

variable "snowflake_account" {
  description = "Snowflake account identifier (e.g. LQZIGNN-AJC44234)"
  type        = string
  sensitive   = true
}

variable "snowflake_user" {
  description = "Snowflake username"
  type        = string
  sensitive   = true
}

variable "snowflake_password" {
  description = "Snowflake password"
  type        = string
  sensitive   = true
}

variable "snowflake_warehouse" {
  description = "Snowflake compute warehouse for ingestion"
  type        = string
  default     = "COMPUTE_WH"
}

variable "snowflake_role" {
  description = "Snowflake role for ingestion (writes to RAW)"
  type        = string
  default     = "ACCOUNTADMIN"
}

variable "snowflake_database" {
  description = "Snowflake database"
  type        = string
  default     = "ABC_BANK_ANALYTICS"
}

variable "snowflake_dbt_role" {
  description = "Snowflake role for dbt (separate from ingestion for least-privilege)"
  type        = string
  default     = "DBT_ROLE"
}

variable "snowflake_dbt_wh" {
  description = "Snowflake warehouse for dbt transformations"
  type        = string
  default     = "DBT_WH"
}

variable "pii_salt" {
  description = "Salt used for SHA-256 tokenization of customer IDs (must match local dev)"
  type        = string
  sensitive   = true
}

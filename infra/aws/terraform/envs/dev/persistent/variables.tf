###############################################################################
# Variables for the persistent stack
###############################################################################

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_account_id" {
  type = string
  validation {
    condition     = length(var.aws_account_id) == 12 && can(regex("^[0-9]+$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit number."
  }
}

variable "project_name" {
  type    = string
  default = "csa"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "owner" {
  type    = string
  default = "lakshmi"
}

# Snowflake credentials
variable "snowflake_account" {
  type      = string
  sensitive = true
}

variable "snowflake_user" {
  type      = string
  sensitive = true
}

variable "snowflake_password" {
  type      = string
  sensitive = true
}

variable "snowflake_warehouse" {
  type    = string
  default = "COMPUTE_WH"
}

variable "snowflake_role" {
  type    = string
  default = "ACCOUNTADMIN"
}

variable "snowflake_database" {
  type    = string
  default = "ABC_BANK_ANALYTICS"
}

variable "snowflake_dbt_role" {
  type    = string
  default = "DBT_ROLE"
}

variable "snowflake_dbt_wh" {
  type    = string
  default = "DBT_WH"
}

variable "pii_salt" {
  type      = string
  sensitive = true
}

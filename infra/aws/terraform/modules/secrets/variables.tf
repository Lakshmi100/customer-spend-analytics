variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

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
  type = string
}

variable "snowflake_role" {
  type = string
}

variable "snowflake_database" {
  type = string
}

variable "snowflake_dbt_role" {
  type = string
}

variable "snowflake_dbt_wh" {
  type = string
}

variable "pii_salt" {
  type      = string
  sensitive = true
}

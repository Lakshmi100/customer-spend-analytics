variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "snowflake_secret_arn" {
  description = "ARN of Secrets Manager secret holding Snowflake credentials"
  type        = string
}

variable "snowflake_database" {
  type    = string
  default = "ABC_BANK_ANALYTICS"
}

variable "snowflake_schema" {
  type    = string
  default = "RAW"
}

variable "snowflake_warehouse" {
  type    = string
  default = "COMPUTE_WH"
}

variable "snowflake_role" {
  description = "Snowflake role with write access to RAW schema + USAGE on stage"
  type        = string
  default     = "ACCOUNTADMIN"
}

variable "stage_name" {
  description = "Snowflake stage name (must already exist via the storage integration)"
  type        = string
  default     = "csa_processed_stage"
}

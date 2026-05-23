variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "raw_bucket" {
  description = "Name of the raw S3 bucket to write delta parquet into"
  type        = string
}

variable "raw_bucket_arn" {
  description = "ARN of the raw S3 bucket (for IAM resources)"
  type        = string
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
  type    = string
  default = "ACCOUNTADMIN"
}

variable "artifacts_bucket" {
  description = "S3 bucket name to upload the Lambda zip into"
  type        = string
}

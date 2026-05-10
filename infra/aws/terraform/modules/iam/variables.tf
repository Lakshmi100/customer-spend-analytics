variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "raw_bucket_arn" {
  description = "ARN of the raw data bucket"
  type        = string
}

variable "processed_bucket_arn" {
  description = "ARN of the processed data bucket"
  type        = string
}

variable "artifacts_bucket_arn" {
  description = "ARN of the artifacts bucket"
  type        = string
}

variable "snowflake_secret_arn" {
  description = "ARN of the Snowflake credentials secret"
  type        = string
}

variable "pii_salt_secret_arn" {
  description = "ARN of the PII salt secret"
  type        = string
}

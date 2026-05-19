variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "raw_bucket_arn" {
  description = "ARN of the raw S3 bucket (read-only access)"
  type        = string
}

variable "processed_bucket_arn" {
  description = "ARN of the processed S3 bucket (read+write access)"
  type        = string
}

variable "artifacts_bucket_arn" {
  description = "ARN of the artifacts S3 bucket (for Spark job script + UI history)"
  type        = string
}

variable "pii_salt_secret_arn" {
  description = "ARN of the PII salt secret in Secrets Manager"
  type        = string
}

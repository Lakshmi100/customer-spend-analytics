variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "aws_account_id" {
  type = string
}

# --- Lambda function ARNs ---
variable "delta_function_arn" {
  description = "ARN of the generate_daily_delta Lambda"
  type        = string
}

variable "loader_function_arn" {
  description = "ARN of the snowflake_loader Lambda"
  type        = string
}

# --- EMR Serverless ---
variable "emr_application_id" {
  description = "EMR Serverless application ID"
  type        = string
}

variable "emr_execution_role_arn" {
  description = "IAM role ARN that EMR Serverless jobs run as"
  type        = string
}

variable "emr_log_group" {
  description = "CloudWatch log group name for EMR job logs"
  type        = string
}

# --- Spark job ---
variable "spark_entry_point" {
  description = "S3 URI of the Spark entry point script (s3://artifacts/spark_jobs/tokenize_and_partition.py)"
  type        = string
}

# --- S3 buckets ---
variable "raw_bucket" {
  description = "Name of the raw S3 bucket"
  type        = string
}

variable "processed_bucket" {
  description = "Name of the processed S3 bucket"
  type        = string
}

# --- Secrets ---
variable "pii_salt_secret_arn" {
  description = "ARN of the PII salt secret"
  type        = string
}

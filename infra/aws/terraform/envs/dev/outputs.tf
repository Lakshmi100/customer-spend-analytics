###############################################################################
# Outputs — values from this stack that downstream phases (or you, manually)
# will need to reference.
###############################################################################

# S3 buckets
output "raw_bucket" {
  description = "S3 bucket for raw ingestion data"
  value       = module.storage.raw_bucket
}

output "processed_bucket" {
  description = "S3 bucket for processed/partitioned parquet"
  value       = module.storage.processed_bucket
}

output "artifacts_bucket" {
  description = "S3 bucket for ML model artifacts and dbt outputs"
  value       = module.storage.artifacts_bucket
}

# Secrets
output "snowflake_secret_arn" {
  description = "ARN of the Snowflake credentials secret in Secrets Manager"
  value       = module.secrets.snowflake_secret_arn
}

output "snowflake_secret_name" {
  description = "Name of the Snowflake secret (use this in code via boto3)"
  value       = module.secrets.snowflake_secret_name
}

output "pii_salt_secret_arn" {
  description = "ARN of the PII salt secret"
  value       = module.secrets.pii_salt_secret_arn
}

# IAM roles
output "ingestion_role_arn" {
  description = "IAM role for ingestion Lambda functions"
  value       = module.iam.ingestion_role_arn
}

output "ml_role_arn" {
  description = "IAM role for ML training/scoring jobs"
  value       = module.iam.ml_role_arn
}

output "api_role_arn" {
  description = "IAM role for FastAPI service (ECS task)"
  value       = module.iam.api_role_arn
}

# ECR
output "ecr_repository_url" {
  description = "ECR repository URL for the FastAPI Docker image"
  value       = module.ecr.repository_url
}

# Quick-reference summary
output "_summary" {
  description = "Human-readable summary of what was created"
  value = <<-EOT

    ════════════════════════════════════════════════════════════════
    ✓ Customer Spend Analytics — AWS Phase 1 deployed
    ════════════════════════════════════════════════════════════════

    📦 S3 Buckets
       raw:       ${module.storage.raw_bucket}
       processed: ${module.storage.processed_bucket}
       artifacts: ${module.storage.artifacts_bucket}

    🔐 Secrets Manager
       Snowflake: ${module.secrets.snowflake_secret_name}
       PII salt:  ${module.secrets.pii_salt_secret_name}

    👤 IAM Roles
       ingestion: ${module.iam.ingestion_role_arn}
       ml:        ${module.iam.ml_role_arn}
       api:       ${module.iam.api_role_arn}

    🐳 ECR Repository
       ${module.ecr.repository_url}

    Next: build Phase 2 (Lambda functions for ingestion).

  EOT
}

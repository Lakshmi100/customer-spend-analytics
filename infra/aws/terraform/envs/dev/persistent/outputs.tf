###############################################################################
# Outputs from the persistent stack.
#
# The ephemeral stack reads these via terraform_remote_state — anything
# ephemeral resources need to reference must be exported here.
###############################################################################

# S3 buckets
output "raw_bucket" {
  value = module.storage.raw_bucket
}

output "raw_bucket_arn" {
  value = module.storage.raw_bucket_arn
}

output "processed_bucket" {
  value = module.storage.processed_bucket
}

output "processed_bucket_arn" {
  value = module.storage.processed_bucket_arn
}

output "artifacts_bucket" {
  value = module.storage.artifacts_bucket
}

output "artifacts_bucket_arn" {
  value = module.storage.artifacts_bucket_arn
}

# Secrets
output "snowflake_secret_arn" {
  value = module.secrets.snowflake_secret_arn
}

output "snowflake_secret_name" {
  value = module.secrets.snowflake_secret_name
}

output "pii_salt_secret_arn" {
  value = module.secrets.pii_salt_secret_arn
}

output "pii_salt_secret_name" {
  value = module.secrets.pii_salt_secret_name
}

# IAM
output "ingestion_role_arn" {
  value = module.iam.ingestion_role_arn
}

output "ingestion_role_name" {
  value = module.iam.ingestion_role_name
}

output "ml_role_arn" {
  value = module.iam.ml_role_arn
}

output "ml_role_name" {
  value = module.iam.ml_role_name
}

output "api_role_arn" {
  value = module.iam.api_role_arn
}

output "api_role_name" {
  value = module.iam.api_role_name
}

# ECR
output "ecr_api_repository_url" {
  value = module.ecr_api.repository_url
}

output "ecr_ingestion_repository_url" {
  value = module.ecr_ingestion.repository_url
}

output "snowflake_storage_role_arn" {
  description = "IAM role ARN for Snowflake STORAGE INTEGRATION"
  value       = module.snowflake_storage.role_arn
}

output "snowflake_handshake_stage" {
  description = "bootstrap (placeholder trust) | active (Snowflake trust patched)"
  value       = module.snowflake_storage.handshake_stage
  sensitive   = true
}

# Quick-reference summary
output "_summary" {
  value = <<-EOT

    ════════════════════════════════════════════════════════════════
    ✓ PERSISTENT stack deployed
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

    🐳 ECR Repositories
       api:        ${module.ecr_api.repository_url}
       ingestion:  ${module.ecr_ingestion.repository_url}

    Cost while standing alone: ~$1/month
    Next: deploy the ephemeral stack to start a work session
          → make ephemeral-apply

  EOT
}

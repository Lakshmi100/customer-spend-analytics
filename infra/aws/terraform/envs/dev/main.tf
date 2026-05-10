###############################################################################
# Customer Spend Analytics — dev environment
#
# Wires together the Phase 1 modules:
#   • storage   — S3 buckets for raw/processed/artifacts data
#   • secrets   — Snowflake creds + PII salt in Secrets Manager
#   • iam       — service roles for ingestion / ML / API
#   • ecr       — container registry (used in Phase 3 for FastAPI)
#
# Future phases will add: lambdas, ECS services, Step Functions.
###############################################################################

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Tags applied automatically to every resource that supports them.
  # Massive ergonomic win: you never have to write Project/Env/Owner on
  # individual resources.
  default_tags {
    tags = {
      Project   = var.project_name
      Env       = var.environment
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}

###############################################################################
# Modules
###############################################################################

module "storage" {
  source = "../../modules/storage"

  project_name   = var.project_name
  environment    = var.environment
  aws_account_id = var.aws_account_id
}

module "secrets" {
  source = "../../modules/secrets"

  project_name = var.project_name
  environment  = var.environment

  snowflake_account   = var.snowflake_account
  snowflake_user      = var.snowflake_user
  snowflake_password  = var.snowflake_password
  snowflake_warehouse = var.snowflake_warehouse
  snowflake_role      = var.snowflake_role
  snowflake_database  = var.snowflake_database
  snowflake_dbt_role  = var.snowflake_dbt_role
  snowflake_dbt_wh    = var.snowflake_dbt_wh
  pii_salt            = var.pii_salt
}

module "iam" {
  source = "../../modules/iam"

  project_name = var.project_name
  environment  = var.environment

  # Pass IDs from upstream modules so IAM policies can reference them
  raw_bucket_arn        = module.storage.raw_bucket_arn
  processed_bucket_arn  = module.storage.processed_bucket_arn
  artifacts_bucket_arn  = module.storage.artifacts_bucket_arn
  snowflake_secret_arn  = module.secrets.snowflake_secret_arn
  pii_salt_secret_arn   = module.secrets.pii_salt_secret_arn
}

module "ecr" {
  source = "../../modules/ecr"

  project_name = var.project_name
  environment  = var.environment
}

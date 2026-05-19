###############################################################################
# Persistent stack — stateful resources that survive across work sessions.
#
# Run rarely:
#   make persistent-apply     (after first creation, only when modules change)
#   make persistent-destroy   (only when permanently abandoning the project)
#
# Cost when standing alone (no ephemeral compute): ~$1/month
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

  default_tags {
    tags = {
      Project   = var.project_name
      Env       = var.environment
      Stack     = "persistent"
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}

###############################################################################
# Modules
###############################################################################

module "storage" {
  source = "../../../modules/storage"

  project_name   = var.project_name
  environment    = var.environment
  aws_account_id = var.aws_account_id
}

module "secrets" {
  source = "../../../modules/secrets"

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
  source = "../../../modules/iam"

  project_name = var.project_name
  environment  = var.environment

  raw_bucket_arn       = module.storage.raw_bucket_arn
  processed_bucket_arn = module.storage.processed_bucket_arn
  artifacts_bucket_arn = module.storage.artifacts_bucket_arn
  snowflake_secret_arn = module.secrets.snowflake_secret_arn
  pii_salt_secret_arn  = module.secrets.pii_salt_secret_arn
}

module "ecr_api" {
  source = "../../../modules/ecr"

  project_name    = var.project_name
  environment     = var.environment
  repository_name = "api"
}

module "ecr_ingestion" {
  source = "../../../modules/ecr"

  project_name    = var.project_name
  environment     = var.environment
  repository_name = "ingestion"
}

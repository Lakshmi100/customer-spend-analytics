###############################################################################
# Ephemeral stack — stateless compute, destroyed nightly.
#
# Phase 2 — Chunk B2: EMR Serverless added
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
      Stack     = "ephemeral"
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}

###############################################################################
# EMR Serverless — auto-scaling Spark for ingestion
###############################################################################

module "emr_serverless" {
  source = "../../../modules/emr_serverless"

  project_name = var.project_name
  environment  = var.environment

  raw_bucket_arn       = local.raw_bucket_arn
  processed_bucket_arn = local.processed_bucket_arn
  artifacts_bucket_arn = local.artifacts_bucket_arn
  pii_salt_secret_arn  = local.pii_salt_secret_arn
}

###############################################################################
# Coming in Chunk B3:
#   module "lambda_delta_generator"  — generates daily synthetic delta
#   module "lambda_snowflake_loader" — triggers Snowflake COPY INTO
#   module "step_functions"          — orchestrates the pipeline
###############################################################################

module "snowflake_loader" {
  source = "../../../modules/lambda_snowflake_loader"

  project_name = var.project_name
  environment  = var.environment

  snowflake_secret_arn = local.snowflake_secret_arn
  # Other Snowflake settings (database, schema, warehouse, role, stage_name)
  # use the module's defaults — override here only if your setup differs.
}
module "generate_daily_delta" {
  source = "../../../modules/lambda_generate_daily_delta"

  project_name = var.project_name
  environment  = var.environment

  raw_bucket           = local.raw_bucket                # name (assumes exists in locals)
  raw_bucket_arn       = local.raw_bucket_arn            # arn
  artifacts_bucket     = local.artifacts_bucket   # ← add this line
  snowflake_secret_arn = local.snowflake_secret_arn      # already a local from earlier
}

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

module "data_libs_layer" {
  source = "../../../modules/lambda_layer_data"

  project_name     = var.project_name
  environment      = var.environment
  artifacts_bucket = local.artifacts_bucket
}

module "generate_daily_delta" {
  source = "../../../modules/lambda_generate_daily_delta"

  project_name = var.project_name
  environment  = var.environment

  raw_bucket           = local.raw_bucket                # name (assumes exists in locals)
  raw_bucket_arn       = local.raw_bucket_arn            # arn
  artifacts_bucket     = local.artifacts_bucket   # ← add this line
  snowflake_secret_arn = local.snowflake_secret_arn      # already a local from earlier
  data_libs_layer_arn = module.data_libs_layer.layer_arn
}

module "step_functions" {
  source = "../../../modules/step_functions"

  project_name   = var.project_name
  environment    = var.environment
  aws_region     = data.aws_region.current.name
  aws_account_id = data.aws_caller_identity.current.account_id

  # Lambda ARNs from other modules
  delta_function_arn  = module.generate_daily_delta.function_arn
  loader_function_arn = module.snowflake_loader.function_arn

  # EMR Serverless config (from emr_serverless module)
  emr_application_id     = module.emr_serverless.application_id
  emr_execution_role_arn = module.emr_serverless.execution_role_arn
  emr_log_group          = module.emr_serverless.log_group_name

  # The Spark entry point lives in artifacts S3 (uploaded by run_emr_job.sh
  # previously; we'll formalize that upload as Terraform-managed later if needed)
  spark_entry_point = data.terraform_remote_state.persistent.outputs.spark_tokenize_script_uri

  # S3 buckets
  raw_bucket       = local.raw_bucket
  processed_bucket = local.processed_bucket

  # Secrets
  pii_salt_secret_arn = data.terraform_remote_state.persistent.outputs.pii_salt_secret_arn
}

module "daily_schedule" {
  source = "../../../modules/eventbridge_schedule"

  project_name = var.project_name
  environment  = var.environment

  state_machine_arn = module.step_functions.state_machine_arn

  # Defaults give 06:00 UTC daily, enabled. Override here if needed:
  # schedule_expression = "cron(0 6 * * ? *)"
  # rule_enabled        = true
}

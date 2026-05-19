###############################################################################
# Remote state data source — reads outputs from the persistent stack.
#
# This is the canonical AWS pattern for passing values between Terraform
# stacks. Anywhere in this stack, reference persistent outputs as:
#   data.terraform_remote_state.persistent.outputs.<output_name>
#
# Example:
#   role_arn = data.terraform_remote_state.persistent.outputs.ingestion_role_arn
#
# The persistent stack must be applied first — otherwise this data source
# fails to read.
###############################################################################

data "terraform_remote_state" "persistent" {
  backend = "s3"
  config = {
    bucket = "csa-tfstate-039323921608"
    key    = "envs/dev/persistent/terraform.tfstate"
    region = "us-east-1"
  }
}

###############################################################################
# Convenience locals — expose persistent outputs as terse names
###############################################################################

locals {
  persistent = data.terraform_remote_state.persistent.outputs

  raw_bucket            = local.persistent.raw_bucket
  raw_bucket_arn        = local.persistent.raw_bucket_arn
  processed_bucket      = local.persistent.processed_bucket
  processed_bucket_arn  = local.persistent.processed_bucket_arn
  artifacts_bucket      = local.persistent.artifacts_bucket
  artifacts_bucket_arn  = local.persistent.artifacts_bucket_arn

  snowflake_secret_arn  = local.persistent.snowflake_secret_arn
  pii_salt_secret_arn   = local.persistent.pii_salt_secret_arn

  ingestion_role_arn    = local.persistent.ingestion_role_arn
  ml_role_arn           = local.persistent.ml_role_arn
  api_role_arn          = local.persistent.api_role_arn

  ecr_api_repository_url        = local.persistent.ecr_api_repository_url
  ecr_ingestion_repository_url  = local.persistent.ecr_ingestion_repository_url
}

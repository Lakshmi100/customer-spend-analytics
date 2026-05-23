###############################################################################
# Snowflake storage integration module.
#
# Creates the AWS IAM role that Snowflake will ASSUME to read processed/
# data from S3. Part of a 4-step handshake:
#
#   1. [THIS MODULE] Create IAM role with PLACEHOLDER trust + final S3 perms
#   2. [Snowflake]   CREATE STORAGE INTEGRATION using this role ARN
#                    → Snowflake generates IAM_USER_ARN + EXTERNAL_ID
#   3. [terraform.tfvars] Set snowflake_iam_user_arn + snowflake_external_id
#                    [terraform apply] patches the trust policy
#   4. [Snowflake]   CREATE STAGE + LIST @stage → verifies handshake works
#
# Security:
#   - Least privilege: read-only on processed/ bucket, no raw/ access (PII)
#   - sts:ExternalId condition defends against the "confused deputy" attack:
#     Snowflake's IAM principal is SHARED across tenants, so knowing the
#     role ARN alone isn't enough — the request must also carry the
#     per-customer external ID Snowflake generated for THIS integration.
###############################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

###############################################################################
# Trust policy
#
# Bootstrap pattern: when first applied (before Snowflake is told this role's
# ARN), we don't yet know Snowflake's IAM user ARN or external ID. We use
# the AWS account root as a placeholder — assumeable but harmless until the
# real values arrive from Snowflake and are patched in via tfvars.
#
# Once snowflake_iam_user_arn and snowflake_external_id are set, the policy
# becomes the real cross-account trust: only Snowflake's specific IAM user
# can assume, and only when presenting OUR external ID.
###############################################################################

data "aws_caller_identity" "current" {}

locals {
  trust_ready = var.snowflake_iam_user_arn != "" && var.snowflake_external_id != ""

  # Placeholder trust: trust our own account (Step 1 — bootstrap only)
  placeholder_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
      Action    = "sts:AssumeRole"
    }]
  })

  # Real trust: Snowflake's IAM user + ExternalId condition (Step 3 — patched)
  snowflake_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = var.snowflake_iam_user_arn }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "sts:ExternalId" = var.snowflake_external_id
        }
      }
    }]
  })
}

###############################################################################
# IAM role
###############################################################################

resource "aws_iam_role" "snowflake_storage" {
  name        = "${local.name_prefix}-snowflake-storage-role"
  description = "Role assumed by Snowflake STORAGE INTEGRATION to read processed/ S3 data"

  # Conditional: placeholder before handshake, real trust after
  assume_role_policy = local.trust_ready ? local.snowflake_trust : local.placeholder_trust

  tags = {
    Component = "snowflake-storage-integration"
    Stage     = local.trust_ready ? "active" : "bootstrap"
  }
}

###############################################################################
# S3 read policy — least privilege, processed/ only, no raw/ (no PII reach)
###############################################################################

data "aws_iam_policy_document" "s3_read" {
  # Bucket-level: needed for ListBucket on the processed bucket
  statement {
    sid     = "ListProcessedBucket"
    actions = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.processed_bucket_arn]
  }

  # Object-level: read-only on processed/ data
  statement {
    sid     = "ReadProcessedObjects"
    actions = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.processed_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "s3_read" {
  name   = "s3-read-processed"
  role   = aws_iam_role.snowflake_storage.id
  policy = data.aws_iam_policy_document.s3_read.json
}

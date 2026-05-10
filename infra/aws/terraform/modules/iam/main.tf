###############################################################################
# IAM module — three roles, one per workload type.
#
# Each role has minimum permissions required for its job:
#   ingestion_role : read+write S3 (raw, processed), read Secrets Manager
#   ml_role        : read S3 (processed), write S3 (artifacts), read Secrets
#   api_role       : read S3 (artifacts), read Secrets Manager
#
# All roles trust both Lambda and ECS so we can use the same role across
# compute platforms in Phases 2 and 3.
###############################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

###############################################################################
# Trust policy — who can assume these roles
###############################################################################

data "aws_iam_policy_document" "lambda_and_ecs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = [
        "lambda.amazonaws.com",
        "ecs-tasks.amazonaws.com",
      ]
    }
  }
}

###############################################################################
# Role: INGESTION
# Used by Lambda functions that generate synthetic data, run PII tokenization,
# write parquet to S3, and orchestrate Snowflake COPY INTO.
###############################################################################

resource "aws_iam_role" "ingestion" {
  name               = "${local.name_prefix}-ingestion-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_and_ecs_trust.json
  description        = "For ingestion Lambdas (data generation + PySpark + Snowflake load)"
}

# CloudWatch Logs (every Lambda needs this to log)
resource "aws_iam_role_policy_attachment" "ingestion_logs" {
  role       = aws_iam_role.ingestion.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "ingestion_inline" {
  # S3: full access to raw and processed buckets
  statement {
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
      "s3:ListBucket", "s3:GetBucketLocation",
    ]
    resources = [
      var.raw_bucket_arn, "${var.raw_bucket_arn}/*",
      var.processed_bucket_arn, "${var.processed_bucket_arn}/*",
    ]
  }
  # Secrets: read Snowflake creds + PII salt (no write)
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.snowflake_secret_arn, var.pii_salt_secret_arn]
  }
}

resource "aws_iam_role_policy" "ingestion_inline" {
  name   = "ingestion-policy"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion_inline.json
}

###############################################################################
# Role: ML
# Used for KMeans training, segmentation, coupon ranking.
# Reads processed data, writes artifacts (model files + recommendations).
###############################################################################

resource "aws_iam_role" "ml" {
  name               = "${local.name_prefix}-ml-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_and_ecs_trust.json
  description        = "For ML training/scoring jobs"
}

resource "aws_iam_role_policy_attachment" "ml_logs" {
  role       = aws_iam_role.ml.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "ml_inline" {
  # Read processed data
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.processed_bucket_arn, "${var.processed_bucket_arn}/*"]
  }
  # Read+write artifacts
  statement {
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
      "s3:ListBucket", "s3:GetBucketLocation",
    ]
    resources = [var.artifacts_bucket_arn, "${var.artifacts_bucket_arn}/*"]
  }
  # Snowflake creds (for pulling customer_360 to train on)
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.snowflake_secret_arn]
  }
}

resource "aws_iam_role_policy" "ml_inline" {
  name   = "ml-policy"
  role   = aws_iam_role.ml.id
  policy = data.aws_iam_policy_document.ml_inline.json
}

###############################################################################
# Role: API
# Used by the FastAPI service running on ECS Fargate (Phase 3).
# Read-only on artifacts (model files), reads Snowflake creds for live queries.
###############################################################################

resource "aws_iam_role" "api" {
  name               = "${local.name_prefix}-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_and_ecs_trust.json
  description        = "For FastAPI service (ECS task role)"
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api_inline" {
  # Read artifacts only (cluster assignments, recommendations)
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.artifacts_bucket_arn, "${var.artifacts_bucket_arn}/*"]
  }
  # Snowflake creds for live customer_360 queries
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.snowflake_secret_arn]
  }
}

resource "aws_iam_role_policy" "api_inline" {
  name   = "api-policy"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_inline.json
}

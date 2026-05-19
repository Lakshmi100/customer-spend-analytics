###############################################################################
# EMR Serverless module — auto-scaling Spark compute for ingestion.
#
# Resources:
#   • EMR Serverless application (the "Spark cluster")
#   • IAM execution role (what Spark jobs run as)
#   • CloudWatch log group for job logs
#
# Design choices:
#   - Cold-start mode (no pre-initialized capacity) → $0 idle cost
#   - Auto-scaling 1-8 workers based on data volume
#   - 5-minute idle timeout (auto-stops after job finishes)
#   - x86_64 architecture for broadest connector compatibility
###############################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

###############################################################################
# CloudWatch log group — Spark driver and executor logs land here
###############################################################################

resource "aws_cloudwatch_log_group" "emr" {
  name              = "/aws/emr-serverless/${local.name_prefix}"
  retention_in_days = 7

  tags = {
    Component = "emr-serverless"
  }
}

###############################################################################
# IAM execution role
#
# This is the role that EMR Serverless ASSUMES when running Spark jobs.
# It needs to be able to:
#   1. Read raw input data from S3
#   2. Read/write processed output to S3
#   3. Write Spark logs to S3 (the artifacts bucket)
#   4. Read the PII salt from Secrets Manager
#   5. Write logs to CloudWatch
#
# Trust policy: only EMR Serverless service can assume this role
###############################################################################

data "aws_iam_policy_document" "emr_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["emr-serverless.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "emr_execution" {
  name               = "${local.name_prefix}-emr-execution-role"
  description        = "Execution role for EMR Serverless Spark jobs"
  assume_role_policy = data.aws_iam_policy_document.emr_trust.json
}

# Policy: S3 access for inputs, outputs, and Spark logs
data "aws_iam_policy_document" "emr_s3" {
  # Read raw bucket
  statement {
    sid     = "ReadRawBucket"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      var.raw_bucket_arn,
      "${var.raw_bucket_arn}/*",
    ]
  }

  # Read+write processed bucket
  statement {
    sid     = "ReadWriteProcessedBucket"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:AbortMultipartUpload",     # for parquet writes
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      var.processed_bucket_arn,
      "${var.processed_bucket_arn}/*",
    ]
  }

  # Read+write artifacts bucket (Spark job script + Spark UI history)
  statement {
    sid     = "ReadWriteArtifactsBucket"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      var.artifacts_bucket_arn,
      "${var.artifacts_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "emr_s3" {
  name   = "s3-access"
  role   = aws_iam_role.emr_execution.id
  policy = data.aws_iam_policy_document.emr_s3.json
}

# Policy: read PII salt from Secrets Manager
data "aws_iam_policy_document" "emr_secrets" {
  statement {
    sid       = "ReadPiiSalt"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.pii_salt_secret_arn]
  }
}

resource "aws_iam_role_policy" "emr_secrets" {
  name   = "secrets-access"
  role   = aws_iam_role.emr_execution.id
  policy = data.aws_iam_policy_document.emr_secrets.json
}

# Policy: CloudWatch Logs access

data "aws_iam_policy_document" "emr_cloudwatch" {
  # DescribeLogGroups operates account-wide, so it needs a broader resource
  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:*:*:log-group:*"]
  }

  # Stream-level operations scoped to our specific log group
  statement {
    sid     = "WriteCloudWatchLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:CreateLogGroup",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = [
      aws_cloudwatch_log_group.emr.arn,
      "${aws_cloudwatch_log_group.emr.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "emr_cloudwatch" {
  name   = "cloudwatch-access"
  role   = aws_iam_role.emr_execution.id
  policy = data.aws_iam_policy_document.emr_cloudwatch.json
}

###############################################################################
# EMR Serverless application
#
# Think of this as a "Spark cluster definition" — but it doesn't actually
# allocate workers until you submit a job. Cold-start mode = $0 idle.
###############################################################################

resource "aws_emrserverless_application" "spark" {
  name          = "${local.name_prefix}-spark-app"
  release_label = "emr-7.0.0"           # EMR runtime version (includes Spark 3.5)
  type          = "spark"
  architecture  = "X86_64"

  # No pre-initialized capacity = cold-start = $0 when idle
  # (uncomment the initial_capacity block below to switch to pre-init)
  #
  # initial_capacity {
  #   initial_capacity_type = "Driver"
  #   initial_capacity_config {
  #     worker_count = 1
  #     worker_configuration {
  #       cpu    = "2 vCPU"
  #       memory = "4 GB"
  #     }
  #   }
  # }

  # Auto-stop the application 5 minutes after job completion
  auto_stop_configuration {
    enabled              = true
    idle_timeout_minutes = 5
  }

  # Maximum capacity ceiling — protection against runaway scaling
  maximum_capacity {
    cpu    = "16 vCPU"   # at most 8 workers of 2 vCPU each
    memory = "64 GB"
  }

  tags = {
    Component = "emr-serverless"
  }
}

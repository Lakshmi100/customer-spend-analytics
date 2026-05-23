###############################################################################
# Lambda module: generate_daily_delta.
#
# Produces a small synthetic daily delta and writes RAW parquet to S3.
# Designed to feed the EMR Spark tokenization job as part of Step Functions.
###############################################################################

locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  function_name  = "${local.name_prefix}-generate-daily-delta"
  source_dir     = abspath("${path.module}/../../../lambdas/generate_daily_delta")
  build_dir      = abspath("${path.module}/.build")
  package_path   = abspath("${path.module}/.build/generate_daily_delta.zip")
} 

###############################################################################
# Build package
###############################################################################

resource "null_resource" "build_package" {
  triggers = {
    handler_hash      = filesha256("${local.source_dir}/handler.py")
    requirements_hash = filesha256("${local.source_dir}/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf ${local.build_dir}
      mkdir -p ${local.build_dir}/package

      pip install \
        --target ${local.build_dir}/package \
        --platform manylinux2014_x86_64 \
        --python-version 3.12 \
        --only-binary=:all: \
        --implementation cp \
        -r ${local.source_dir}/requirements.txt

      cp ${local.source_dir}/handler.py ${local.build_dir}/package/

      cd ${local.build_dir}/package && zip -r ../generate_daily_delta.zip . -q

      # Upload the zip to S3 (artifacts bucket) for Lambda to read.
      # Direct-upload Lambda limit is 70 MB; S3-mediated limit is 250 MB.
      aws s3 cp ${local.package_path} s3://${var.artifacts_bucket}/lambda_packages/generate_daily_delta.zip
    EOT
  }
}


###############################################################################
# Log group
###############################################################################

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 7
}

###############################################################################
# IAM
###############################################################################

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

# Read Snowflake credentials
data "aws_iam_policy_document" "secrets_read" {
  statement {
    sid       = "ReadSnowflakeSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.snowflake_secret_arn]
  }
}

resource "aws_iam_role_policy" "secrets_read" {
  name   = "snowflake-secret-read"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

# Write to raw bucket
data "aws_iam_policy_document" "raw_write" {
  statement {
    sid     = "WriteRawDelta"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      var.raw_bucket_arn,
      "${var.raw_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "raw_write" {
  name   = "raw-s3-write"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.raw_write.json
}

# CloudWatch Logs
data "aws_iam_policy_document" "logs_write" {
  statement {
    sid     = "WriteLambdaLogs"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs_write" {
  name   = "cloudwatch-logs"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.logs_write.json
}

###############################################################################
# Lambda function
###############################################################################

resource "aws_lambda_function" "this" {
  function_name = local.function_name
  description   = "Generates daily synthetic delta and writes parquet to S3 raw"
  role          = aws_iam_role.lambda.arn

  # Reference the S3-uploaded zip (allows up to 250 MB compressed).
  s3_bucket        = var.artifacts_bucket
  s3_key           = "lambda_packages/generate_daily_delta.zip"
  source_code_hash = null_resource.build_package.triggers.handler_hash

  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]
  timeout       = 120
  memory_size   = 512


  environment {
    variables = {
      RAW_BUCKET           = var.raw_bucket
      SNOWFLAKE_SECRET_ARN = var.snowflake_secret_arn
      SNOWFLAKE_DATABASE   = var.snowflake_database
      SNOWFLAKE_SCHEMA     = var.snowflake_schema
      SNOWFLAKE_WAREHOUSE  = var.snowflake_warehouse
      SNOWFLAKE_ROLE       = var.snowflake_role
    }
  }

  depends_on = [
    null_resource.build_package,
    aws_iam_role_policy.secrets_read,
    aws_iam_role_policy.raw_write,
    aws_iam_role_policy.logs_write,
    aws_cloudwatch_log_group.this,
  ]

  tags = {
    Component = "delta-generator"
  }
}

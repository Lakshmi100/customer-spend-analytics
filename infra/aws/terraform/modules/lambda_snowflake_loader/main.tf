###############################################################################
# Lambda module: snowflake_loader.
#
# Wraps the Snowflake COPY INTO logic (verified-working manual SQL) as a
# Lambda function callable by Step Functions or direct invocation.
#
# What this module creates:
#   - Lambda function (Python 3.12, 5-min timeout)
#   - IAM execution role with: Secrets Manager read, CloudWatch Logs write
#   - CloudWatch log group with 7-day retention
#   - Zip package built via archive_file (handler.py + requirements installed)
#
# Lives in ephemeral stack - destroyed nightly with the rest of compute.
###############################################################################

locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  function_name  = "${local.name_prefix}-snowflake-loader"
  source_dir     = "${path.module}/../../../lambdas/snowflake_loader"
  build_dir      = "${path.module}/.build"
  package_path   = "${path.module}/.build/snowflake_loader.zip"
}

###############################################################################
# Package the Lambda code + Python dependencies
#
# Snowflake connector has C extensions, so 'pip install --platform' is needed
# to fetch Linux wheels (we're likely building from a Mac). Done in null_resource
# rather than archive_file alone because archive_file doesn't run pip.
###############################################################################

resource "null_resource" "build_package" {
  # Rebuild whenever handler.py or requirements.txt changes
  triggers = {
    handler_hash      = filesha256("${local.source_dir}/handler.py")
    requirements_hash = filesha256("${local.source_dir}/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf ${local.build_dir}
      mkdir -p ${local.build_dir}/package

      # Install deps targeting Lambda's Python 3.12 / x86_64 / Linux
      pip install \
        --target ${local.build_dir}/package \
        --platform manylinux2014_x86_64 \
        --python-version 3.12 \
        --only-binary=:all: \
        --implementation cp \
        -r ${local.source_dir}/requirements.txt

      cp ${local.source_dir}/handler.py ${local.build_dir}/package/

      cd ${local.build_dir}/package && zip -r ../snowflake_loader.zip . -q
    EOT
  }
}

data "archive_file" "package_marker" {
  # Marker - actual zip is created by null_resource above.
  # This data source just records the final zip's hash for Lambda updates.
  type        = "zip"
  source_file = "${local.source_dir}/handler.py"
  output_path = "${local.build_dir}/handler_only.zip"
  depends_on  = [null_resource.build_package]
}

###############################################################################
# CloudWatch log group (created BEFORE Lambda so retention is right from start)
###############################################################################

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 7
}

###############################################################################
# IAM execution role
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

# Read Snowflake credentials from Secrets Manager
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

# CloudWatch Logs write
data "aws_iam_policy_document" "logs_write" {
  statement {
    sid     = "WriteLambdaLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
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
  description   = "Loads EMR-tokenized data from S3 to Snowflake via COPY INTO"
  role          = aws_iam_role.lambda.arn

  filename         = local.package_path
  source_code_hash = null_resource.build_package.triggers.handler_hash
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]

  # Snowflake COPY INTO can take 30-90s on cold warehouse; 5 min is safe margin
  timeout     = 300
  memory_size = 512

  environment {
    variables = {
      SNOWFLAKE_SECRET_ARN = var.snowflake_secret_arn
      SNOWFLAKE_DATABASE   = var.snowflake_database
      SNOWFLAKE_SCHEMA     = var.snowflake_schema
      SNOWFLAKE_WAREHOUSE  = var.snowflake_warehouse
      SNOWFLAKE_ROLE       = var.snowflake_role
      STAGE_NAME           = var.stage_name
    }
  }

  depends_on = [
    null_resource.build_package,
    aws_iam_role_policy.secrets_read,
    aws_iam_role_policy.logs_write,
    aws_cloudwatch_log_group.this,
  ]

  tags = {
    Component = "snowflake-loader"
  }
}

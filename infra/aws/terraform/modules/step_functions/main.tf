###############################################################################
# Step Functions module: csa_pipeline
#
# Orchestrates the 3-step daily pipeline:
#   1. GenerateDelta       (Lambda)            - 10 sec
#   2. TokenizeWithSpark   (EMR Serverless.sync) - 3-5 min  ← .sync = waits for completion
#   3. LoadToSnowflake     (Lambda)            - 60 sec
#
# Type: Standard (cheapest for daily batch — billed per state transition,
# not per duration. Standard also gives durable execution history we can
# replay-debug via the console.)
#
# Retries: each step retries ONCE on transient errors (throttling, network
# blips). Hard failures still surface — they just need to fail twice.
###############################################################################

locals {
  name_prefix         = "${var.project_name}-${var.environment}"
  state_machine_name  = "${local.name_prefix}-pipeline"
}

###############################################################################
# CloudWatch log group — durable execution history beyond Step Functions'
# built-in 90-day retention. Created BEFORE the state machine so retention
# is correct from the first execution.
###############################################################################

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.state_machine_name}"
  retention_in_days = 7
}

###############################################################################
# IAM execution role for Step Functions
#
# Permissions needed:
#   - Invoke both Lambdas
#   - Start + poll EMR Serverless jobs (the .sync pattern uses both)
#   - Pass the EMR execution role to the Spark job
#   - Write CloudWatch Logs
###############################################################################

data "aws_iam_policy_document" "sfn_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.state_machine_name}-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_trust.json
}

# Invoke Lambdas
data "aws_iam_policy_document" "invoke_lambdas" {
  statement {
    sid       = "InvokeLambdas"
    actions   = ["lambda:InvokeFunction"]
    resources = [
      var.delta_function_arn,
      "${var.delta_function_arn}:*",
      var.loader_function_arn,
      "${var.loader_function_arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "invoke_lambdas" {
  name   = "invoke-lambdas"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.invoke_lambdas.json
}

# EMR Serverless: start jobs + poll status (the .sync pattern uses both)
data "aws_iam_policy_document" "emr_serverless" {
  statement {
    sid     = "StartAndPollEmrJobs"
    actions = [
      "emr-serverless:StartJobRun",
      "emr-serverless:GetJobRun",
      "emr-serverless:CancelJobRun",
    ]
    # Scoped to our specific application; broader applications/* wildcard if needed
    resources = [
      "arn:aws:emr-serverless:${var.aws_region}:${var.aws_account_id}:/applications/${var.emr_application_id}",
      "arn:aws:emr-serverless:${var.aws_region}:${var.aws_account_id}:/applications/${var.emr_application_id}/jobruns/*",
    ]
  }

  # Required for emr-serverless:StartJobRun to attach the execution role
  statement {
    sid       = "PassEmrExecutionRole"
    actions   = ["iam:PassRole"]
    resources = [var.emr_execution_role_arn]
  }
}

resource "aws_iam_role_policy" "emr_serverless" {
  name   = "emr-serverless"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.emr_serverless.json
}

# Step Functions service integrations need ability to call DescribeRule/PutTargets
# on EventBridge for the .sync pattern's internal callback mechanism.
data "aws_iam_policy_document" "sync_callback" {
  statement {
    sid     = "SyncCallback"
    actions = [
      "events:PutTargets",
      "events:PutRule",
      "events:DescribeRule",
    ]
    resources = ["arn:aws:events:${var.aws_region}:${var.aws_account_id}:rule/StepFunctionsGetEventsForEMRServerlessJobRule"]
  }
}

resource "aws_iam_role_policy" "sync_callback" {
  name   = "sync-callback-eventbridge"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sync_callback.json
}

# CloudWatch Logs delivery — Standard SFN logs through "vended logs" pattern
data "aws_iam_policy_document" "logs" {
  statement {
    sid     = "DeliverVendedLogs"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "vended-logs"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.logs.json
}

###############################################################################
# State machine definition - ASL JSON rendered from template
###############################################################################

locals {
  definition = templatefile("${path.module}/state_machine.json", {
    delta_function_arn     = var.delta_function_arn
    loader_function_arn    = var.loader_function_arn
    emr_application_id     = var.emr_application_id
    emr_execution_role_arn = var.emr_execution_role_arn
    emr_log_group          = var.emr_log_group
    spark_entry_point      = var.spark_entry_point
    raw_bucket             = var.raw_bucket
    processed_bucket       = var.processed_bucket
    pii_salt_secret_arn    = var.pii_salt_secret_arn
    aws_region             = var.aws_region
  })
}

resource "aws_sfn_state_machine" "this" {
  name     = local.state_machine_name
  type     = "STANDARD"
  role_arn = aws_iam_role.sfn.arn

  definition = local.definition

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  depends_on = [
    aws_iam_role_policy.invoke_lambdas,
    aws_iam_role_policy.emr_serverless,
    aws_iam_role_policy.sync_callback,
    aws_iam_role_policy.logs,
  ]

  tags = {
    Component = "step-functions-pipeline"
  }
}

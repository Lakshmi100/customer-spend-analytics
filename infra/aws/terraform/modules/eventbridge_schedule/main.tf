###############################################################################
# EventBridge daily schedule module.
#
# Creates a cron-scheduled EventBridge rule that triggers the Step Functions
# state machine once daily. Plus the IAM role EventBridge assumes to call
# states:StartExecution.
#
# Lives in the EPHEMERAL stack: the schedule only exists while the pipeline
# does. This avoids the "schedule fires at 6 AM but the state machine was torn
# down overnight -> failed run noise" problem. In an always-on production
# system, both schedule and compute would live in a persistent always-on stack.
#
# Schedule: cron(0 6 * * ? *) = 06:00 UTC every day.
# EventBridge classic rules are UTC-only (no timezone). 06:00 UTC = 02:00 ET.
###############################################################################

locals {
  rule_name = "${var.project_name}-${var.environment}-daily-pipeline"
}

###############################################################################
# The schedule rule
###############################################################################

resource "aws_cloudwatch_event_rule" "daily" {
  name                = local.rule_name
  description         = "Triggers the csa pipeline state machine daily at 06:00 UTC"
  schedule_expression = var.schedule_expression
  state               = var.rule_enabled ? "ENABLED" : "DISABLED"

  tags = {
    Component = "eventbridge-schedule"
  }
}

###############################################################################
# IAM role EventBridge assumes to start the state machine
###############################################################################

data "aws_iam_policy_document" "eventbridge_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge" {
  name               = "${local.rule_name}-role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_trust.json
}

data "aws_iam_policy_document" "start_execution" {
  statement {
    sid       = "StartPipelineExecution"
    actions   = ["states:StartExecution"]
    resources = [var.state_machine_arn]
  }
}

resource "aws_iam_role_policy" "start_execution" {
  name   = "start-execution"
  role   = aws_iam_role.eventbridge.id
  policy = data.aws_iam_policy_document.start_execution.json
}

###############################################################################
# The target: wire the rule to the state machine
#
# The `input` is the static JSON payload sent on every scheduled run. We omit
# ingest_date so the Lambdas default to "today" — exactly what a daily run
# wants. We do NOT set force_new_customers, so the delta generator uses its
# natural random roll (60% no new customers, 40% chance of 3-5).
###############################################################################

resource "aws_cloudwatch_event_target" "state_machine" {
  rule     = aws_cloudwatch_event_rule.daily.name
  arn      = var.state_machine_arn
  role_arn = aws_iam_role.eventbridge.arn

  # Empty-ish input: let the pipeline default ingest_date to today and use
  # natural randomness for new customers.
  input = jsonencode({})
}

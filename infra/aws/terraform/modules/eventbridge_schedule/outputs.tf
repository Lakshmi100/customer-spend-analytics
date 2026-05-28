output "rule_name" {
  description = "Name of the EventBridge schedule rule"
  value       = aws_cloudwatch_event_rule.daily.name
}

output "rule_arn" {
  value = aws_cloudwatch_event_rule.daily.arn
}

output "schedule_expression" {
  description = "The active schedule expression"
  value       = aws_cloudwatch_event_rule.daily.schedule_expression
}

output "rule_state" {
  description = "ENABLED or DISABLED"
  value       = aws_cloudwatch_event_rule.daily.state
}

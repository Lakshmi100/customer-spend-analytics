output "state_machine_arn" {
  description = "State machine ARN (use in aws stepfunctions start-execution)"
  value       = aws_sfn_state_machine.this.arn
}

output "state_machine_name" {
  description = "State machine name"
  value       = aws_sfn_state_machine.this.name
}

output "role_arn" {
  description = "IAM execution role ARN for the state machine"
  value       = aws_iam_role.sfn.arn
}

output "log_group_name" {
  description = "CloudWatch log group for execution logs"
  value       = aws_cloudwatch_log_group.sfn.name
}

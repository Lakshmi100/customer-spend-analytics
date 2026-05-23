output "function_name" {
  description = "Lambda function name (use in aws lambda invoke calls)"
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Lambda function ARN (use in Step Functions Resource field)"
  value       = aws_lambda_function.this.arn
}

output "role_arn" {
  description = "Lambda execution role ARN"
  value       = aws_iam_role.lambda.arn
}

output "log_group_name" {
  description = "CloudWatch log group for this Lambda"
  value       = aws_cloudwatch_log_group.this.name
}

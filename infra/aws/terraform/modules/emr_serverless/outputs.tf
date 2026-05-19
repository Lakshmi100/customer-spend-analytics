output "application_id" {
  description = "EMR Serverless application ID — used in start-job-run calls"
  value       = aws_emrserverless_application.spark.id
}

output "application_arn" {
  description = "EMR Serverless application ARN"
  value       = aws_emrserverless_application.spark.arn
}

output "application_name" {
  description = "EMR Serverless application name"
  value       = aws_emrserverless_application.spark.name
}

output "execution_role_arn" {
  description = "IAM role ARN that Spark jobs execute as"
  value       = aws_iam_role.emr_execution.arn
}

output "log_group_name" {
  description = "CloudWatch log group for EMR job logs"
  value       = aws_cloudwatch_log_group.emr.name
}

output "role_arn" {
  description = "IAM role ARN — paste this into Snowflake's CREATE STORAGE INTEGRATION ... STORAGE_AWS_ROLE_ARN = '...'"
  value       = aws_iam_role.snowflake_storage.arn
}

output "role_name" {
  description = "IAM role name"
  value       = aws_iam_role.snowflake_storage.name
}

output "handshake_stage" {
  description = "Whether the trust policy is still bootstrap (placeholder) or active (Snowflake)"
  value       = aws_iam_role.snowflake_storage.tags["Stage"]
}

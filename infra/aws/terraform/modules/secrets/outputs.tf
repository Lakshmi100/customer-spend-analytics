output "snowflake_secret_arn" {
  description = "ARN of the Snowflake credentials secret"
  value       = aws_secretsmanager_secret.snowflake.arn
}

output "snowflake_secret_name" {
  description = "Name of the Snowflake secret (use this in code)"
  value       = aws_secretsmanager_secret.snowflake.name
}

output "pii_salt_secret_arn" {
  description = "ARN of the PII salt secret"
  value       = aws_secretsmanager_secret.pii_salt.arn
}

output "pii_salt_secret_name" {
  description = "Name of the PII salt secret"
  value       = aws_secretsmanager_secret.pii_salt.name
}

output "ingestion_role_arn" {
  description = "ARN of the ingestion role"
  value       = aws_iam_role.ingestion.arn
}

output "ingestion_role_name" {
  description = "Name of the ingestion role"
  value       = aws_iam_role.ingestion.name
}

output "ml_role_arn" {
  description = "ARN of the ML role"
  value       = aws_iam_role.ml.arn
}

output "ml_role_name" {
  description = "Name of the ML role"
  value       = aws_iam_role.ml.name
}

output "api_role_arn" {
  description = "ARN of the API role"
  value       = aws_iam_role.api.arn
}

output "api_role_name" {
  description = "Name of the API role"
  value       = aws_iam_role.api.name
}

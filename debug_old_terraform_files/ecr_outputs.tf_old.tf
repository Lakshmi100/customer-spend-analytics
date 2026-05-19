output "repository_url" {
  description = "ECR repository URL — push images to this URL"
  value       = aws_ecr_repository.api.repository_url
}

output "repository_name" {
  description = "ECR repository name"
  value       = aws_ecr_repository.api.name
}

output "repository_arn" {
  description = "ECR repository ARN"
  value       = aws_ecr_repository.api.arn
}

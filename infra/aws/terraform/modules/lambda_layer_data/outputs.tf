output "layer_arn" {
  description = "Latest version ARN — Lambdas attach to this via layers = [...]"
  value       = aws_lambda_layer_version.this.arn
}

output "layer_name" {
  value = aws_lambda_layer_version.this.layer_name
}

output "layer_version" {
  value = aws_lambda_layer_version.this.version
}

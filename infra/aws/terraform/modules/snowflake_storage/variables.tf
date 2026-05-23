variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "processed_bucket_arn" {
  description = "ARN of the processed S3 bucket Snowflake will read"
  type        = string
}

variable "snowflake_iam_user_arn" {
  description = <<-EOT
    Snowflake's IAM user ARN, from DESC INTEGRATION after CREATE STORAGE INTEGRATION.
    Leave empty on the first apply (bootstrap); set after Step 2 of the handshake.
    Example: arn:aws:iam::123456789012:user/abc1-s-v2st0000
  EOT
  type    = string
  default = ""
}

variable "snowflake_external_id" {
  description = <<-EOT
    Snowflake's external ID, from DESC INTEGRATION after CREATE STORAGE INTEGRATION.
    Leave empty on the first apply (bootstrap); set after Step 2 of the handshake.
    Example: WKC24938_SFCRole=2_xxxxxxxxxxxx=
  EOT
  type      = string
  default   = ""
  sensitive = true
}

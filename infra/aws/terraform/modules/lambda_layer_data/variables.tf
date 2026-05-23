variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "artifacts_bucket" {
  description = "S3 bucket name to upload the layer zip into"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy bootstrap resources to"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS account ID — used to make S3 bucket names globally unique"
  type        = string
  validation {
    condition     = length(var.aws_account_id) == 12 && can(regex("^[0-9]+$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit number."
  }
}

variable "project_name" {
  description = "Project name used as a prefix for resource names"
  type        = string
  default     = "csa"  # customer-spend-analytics, kept short for resource name limits
}

variable "owner" {
  description = "Owner tag for billing / accountability"
  type        = string
  default     = "lakshmi"
}

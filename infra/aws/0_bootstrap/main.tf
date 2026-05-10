###############################################################################
# Bootstrap: Terraform state backend
#
# Creates the S3 bucket + DynamoDB table that will store and lock the state
# for our main Terraform configuration.
#
# This config uses LOCAL state (a terraform.tfstate file in this directory),
# because we need somewhere to put the state for the resources that will
# hold all OTHER state. Standard chicken-and-egg solution.
#
# Run ONCE per AWS account:
#   terraform init
#   terraform apply
#
# After this succeeds, copy the outputs into ../terraform/envs/dev/backend.tf
# (or just run `make bootstrap` from the parent Makefile).
###############################################################################

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      Env       = "bootstrap"
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}

###############################################################################
# S3 bucket for Terraform state
###############################################################################

resource "aws_s3_bucket" "tf_state" {
  bucket = "${var.project_name}-tfstate-${var.aws_account_id}"

  # Prevent accidental deletion of this bucket — it holds infrastructure state.
  # If you really need to destroy, set this to false first, apply, then destroy.
  lifecycle {
    prevent_destroy = true
  }
}

# Versioning lets us recover from accidental state file corruption
resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt state at rest
resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block ALL public access — state files contain sensitive resource info
resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

###############################################################################
# DynamoDB table for state locking
#
# Prevents two `terraform apply` runs from clobbering each other.
# Pay-per-request mode means we pay essentially nothing for portfolio usage.
###############################################################################

resource "aws_dynamodb_table" "tf_lock" {
  name         = "${var.project_name}-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }
}

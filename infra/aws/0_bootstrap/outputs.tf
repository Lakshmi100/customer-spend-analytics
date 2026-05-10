###############################################################################
# Outputs
#
# After running `terraform apply`, copy these values into
# ../terraform/envs/dev/backend.tf
###############################################################################

output "tf_state_bucket" {
  description = "S3 bucket name for Terraform state — copy into backend.tf"
  value       = aws_s3_bucket.tf_state.id
}

output "tf_lock_table" {
  description = "DynamoDB table name for state locking — copy into backend.tf"
  value       = aws_dynamodb_table.tf_lock.name
}

output "aws_region" {
  description = "Region where state lives"
  value       = var.aws_region
}

output "_backend_block_to_copy" {
  description = "Paste this entire block into envs/dev/backend.tf"
  value = <<-EOT

    terraform {
      backend "s3" {
        bucket         = "${aws_s3_bucket.tf_state.id}"
        key            = "envs/dev/terraform.tfstate"
        region         = "${var.aws_region}"
        dynamodb_table = "${aws_dynamodb_table.tf_lock.name}"
        encrypt        = true
      }
    }

  EOT
}

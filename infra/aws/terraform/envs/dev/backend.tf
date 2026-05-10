###############################################################################
# Backend configuration — points Terraform at the S3 + DynamoDB created
# by the 0_bootstrap step.
#
# Run `terraform init` once after first creating this file. Subsequent
# runs use the cached config in .terraform/.
###############################################################################

terraform {
  backend "s3" {
    bucket         = "csa-tfstate-039323921608"
    key            = "envs/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "csa-tflock"
    encrypt        = true
  }
}

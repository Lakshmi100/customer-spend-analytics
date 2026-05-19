###############################################################################
# Backend for the PERSISTENT stack.
#
# This stack contains stateful resources that survive across work sessions:
#   • S3 buckets (with your data)
#   • Secrets Manager entries
#   • IAM roles
#   • ECR repositories
#
# State key: envs/dev/persistent/terraform.tfstate
###############################################################################

terraform {
  backend "s3" {
    bucket         = "csa-tfstate-039323921608"
    key            = "envs/dev/persistent/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "csa-tflock"
    encrypt        = true
  }
}

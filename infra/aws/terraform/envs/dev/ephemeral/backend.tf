###############################################################################
# Backend for the EPHEMERAL stack.
#
# This stack contains stateless compute that's destroyed nightly:
#   • Lambda functions
#   • EMR Serverless applications
#   • Step Functions state machines
#   • ECS services + ALB (in Phase 3)
#   • CloudWatch alarms tied to compute
#
# State key: envs/dev/ephemeral/terraform.tfstate
###############################################################################

terraform {
  backend "s3" {
    bucket         = "csa-tfstate-039323921608"
    key            = "envs/dev/ephemeral/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "csa-tflock"
    encrypt        = true
  }
}

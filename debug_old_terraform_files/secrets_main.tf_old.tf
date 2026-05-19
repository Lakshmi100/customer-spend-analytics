###############################################################################
# Secrets module — stores Snowflake credentials and PII salt in
# AWS Secrets Manager.
#
# Why two separate secrets:
#   - Snowflake creds rotate together (account/user/password)
#   - PII salt rotates on its own schedule (and rotation is more expensive
#     because it requires re-tokenizing existing customer IDs)
#
# Code reads these via boto3:
#   import boto3, json
#   client = boto3.client('secretsmanager')
#   creds = json.loads(client.get_secret_value(SecretId="csa-dev-snowflake")["SecretString"])
###############################################################################

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

###############################################################################
# Snowflake credentials (composite secret with 7 fields as JSON)
###############################################################################

resource "aws_secretsmanager_secret" "snowflake" {
  name                    = "${local.name_prefix}-snowflake"
  description             = "Snowflake credentials for the ${var.environment} environment"
  recovery_window_in_days = 7  # short recovery window for portfolio; prod = 30
}

resource "aws_secretsmanager_secret_version" "snowflake" {
  secret_id = aws_secretsmanager_secret.snowflake.id
  secret_string = jsonencode({
    account            = var.snowflake_account
    user               = var.snowflake_user
    password           = var.snowflake_password
    warehouse          = var.snowflake_warehouse
    role               = var.snowflake_role
    database           = var.snowflake_database
    dbt_role           = var.snowflake_dbt_role
    dbt_warehouse      = var.snowflake_dbt_wh
  })
}

###############################################################################
# PII salt (separate because it rotates on a different schedule)
###############################################################################

resource "aws_secretsmanager_secret" "pii_salt" {
  name                    = "${local.name_prefix}-pii-salt"
  description             = "Salt used for SHA-256 tokenization of customer IDs"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "pii_salt" {
  secret_id     = aws_secretsmanager_secret.pii_salt.id
  secret_string = var.pii_salt
}

#!/usr/bin/env bash
#
# upload_to_s3.sh — push the Spark job to the artifacts S3 bucket
#
# Usage:
#   cd infra/aws/spark_jobs
#   ./upload_to_s3.sh
#
# This must be re-run every time you edit tokenize_and_partition.py
# Eventually we'll automate this via Terraform/Makefile.
#
# Prerequisites:
#   - AWS CLI configured (aws sts get-caller-identity must work)
#   - Persistent stack deployed (csa-dev-artifacts-XXX bucket must exist)

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ARTIFACTS_BUCKET="csa-dev-artifacts-${AWS_ACCOUNT_ID}"

JOB_FILE="tokenize_and_partition.py"
S3_KEY="spark_jobs/${JOB_FILE}"

echo "→ Uploading Spark job to S3..."
echo "  Source:      ./${JOB_FILE}"
echo "  Destination: s3://${ARTIFACTS_BUCKET}/${S3_KEY}"
echo

aws s3 cp "${JOB_FILE}" "s3://${ARTIFACTS_BUCKET}/${S3_KEY}"

echo
echo "✓ Upload complete"
echo
echo "  s3://${ARTIFACTS_BUCKET}/${S3_KEY}"
echo
echo "EMR Serverless can now reference this URI as the entry point script."

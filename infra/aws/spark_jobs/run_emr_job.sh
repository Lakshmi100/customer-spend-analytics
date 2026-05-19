#!/usr/bin/env bash
#
# run_emr_job.sh — submit the tokenize_and_partition Spark job to EMR Serverless
#
# Usage:
#   cd infra/aws/spark_jobs
#   ./run_emr_job.sh
#
# Optionally specify a different ingest date:
#   ./run_emr_job.sh 2026-05-12
#
# What this does:
#   1. Reads EMR app ID + execution role ARN from terraform output
#   2. Uploads the latest spark job to S3 (artifacts bucket)
#   3. Submits a job run to EMR Serverless
#   4. Tails CloudWatch logs in real-time
#   5. Reports final status

set -euo pipefail

# Resolve the script's own directory as an ABSOLUTE path, once.
# All other paths derive from this so `cd` calls don't break things.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPARK_JOBS_DIR="${SCRIPT_DIR}"
EPHEMERAL_DIR="$(cd "${SCRIPT_DIR}/../terraform/envs/dev/ephemeral" && pwd)"

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
PROJECT_NAME="csa"
ENVIRONMENT="dev"

INGEST_DATE="${1:-$(date +%Y-%m-%d)}"

RAW_BUCKET="${PROJECT_NAME}-${ENVIRONMENT}-raw-${AWS_ACCOUNT_ID}"
PROCESSED_BUCKET="${PROJECT_NAME}-${ENVIRONMENT}-processed-${AWS_ACCOUNT_ID}"
ARTIFACTS_BUCKET="${PROJECT_NAME}-${ENVIRONMENT}-artifacts-${AWS_ACCOUNT_ID}"

JOB_FILE="tokenize_and_partition.py"
S3_JOB_KEY="spark_jobs/${JOB_FILE}"
S3_JOB_URI="s3://${ARTIFACTS_BUCKET}/${S3_JOB_KEY}"

# -------------------------------------------------------------------
# Pre-flight: confirm Terraform state has EMR resources deployed
# -------------------------------------------------------------------
echo "→ Reading EMR Serverless config from Terraform state..."

cd "${EPHEMERAL_DIR}"

APP_ID=$(terraform output -raw emr_application_id 2>/dev/null || echo "")
EXECUTION_ROLE_ARN=$(terraform output -raw emr_execution_role_arn 2>/dev/null || echo "")
LOG_GROUP=$(terraform output -raw emr_log_group_name 2>/dev/null || echo "")

if [[ -z "${APP_ID}" || -z "${EXECUTION_ROLE_ARN}" ]]; then
    echo "✗ EMR Serverless not deployed. Run 'make ephemeral-apply' first."
    exit 1
fi

cd "${SPARK_JOBS_DIR}"

# Get the PII salt ARN from persistent state (read via AWS CLI rather than terraform)
PII_SALT_ARN=$(aws secretsmanager describe-secret \
    --secret-id "${PROJECT_NAME}-${ENVIRONMENT}-pii-salt" \
    --query ARN \
    --output text)

echo "  ✓ Application ID:   ${APP_ID}"
echo "  ✓ Execution role:   ${EXECUTION_ROLE_ARN}"
echo "  ✓ Log group:        ${LOG_GROUP}"
echo "  ✓ PII salt secret:  ${PII_SALT_ARN}"
echo "  ✓ Ingest date:      ${INGEST_DATE}"
echo

# -------------------------------------------------------------------
# Upload the Spark job to S3 (overwrites any previous version)
# -------------------------------------------------------------------
echo "→ Uploading Spark job to ${S3_JOB_URI}..."
aws s3 cp "${JOB_FILE}" "${S3_JOB_URI}"
echo

# -------------------------------------------------------------------
# Submit the job
# -------------------------------------------------------------------
echo "→ Submitting job to EMR Serverless..."

# Spark configuration: enable S3-optimized committer (HUGE perf win vs local Spark)
SPARK_SUBMIT_PARAMS="--conf spark.hadoop.fs.s3a.fast.upload=true"
SPARK_SUBMIT_PARAMS="${SPARK_SUBMIT_PARAMS} --conf spark.sql.parquet.fs.optimized.committer.optimization-enabled=true"
SPARK_SUBMIT_PARAMS="${SPARK_SUBMIT_PARAMS} --conf spark.executor.memory=4g"
SPARK_SUBMIT_PARAMS="${SPARK_SUBMIT_PARAMS} --conf spark.driver.memory=2g"

JOB_RUN_ID=$(aws emr-serverless start-job-run \
    --application-id "${APP_ID}" \
    --execution-role-arn "${EXECUTION_ROLE_ARN}" \
    --name "tokenize-and-partition-${INGEST_DATE}-$(date +%s)" \
    --region "${AWS_REGION}" \
    --job-driver "{
        \"sparkSubmit\": {
            \"entryPoint\": \"${S3_JOB_URI}\",
            \"entryPointArguments\": [
                \"--raw-bucket\", \"${RAW_BUCKET}\",
                \"--processed-bucket\", \"${PROCESSED_BUCKET}\",
                \"--pii-salt-secret-arn\", \"${PII_SALT_ARN}\",
                \"--ingest-date\", \"${INGEST_DATE}\",
                \"--region\", \"${AWS_REGION}\"
            ],
            \"sparkSubmitParameters\": \"${SPARK_SUBMIT_PARAMS}\"
        }
    }" \
    --configuration-overrides "{
        \"monitoringConfiguration\": {
            \"cloudWatchLoggingConfiguration\": {
                \"enabled\": true,
                \"logGroupName\": \"${LOG_GROUP}\"
            },
            \"s3MonitoringConfiguration\": {
                \"logUri\": \"s3://${ARTIFACTS_BUCKET}/emr-spark-logs/\"
            }
        }
    }" \
    --query 'jobRunId' \
    --output text)

echo "  ✓ Job submitted: ${JOB_RUN_ID}"
echo

# -------------------------------------------------------------------
# Poll for completion + tail logs
# -------------------------------------------------------------------
echo "→ Waiting for job to start..."
START_TIME=$(date +%s)

# Wait for state to leave SUBMITTED (could take ~30 sec for cold-start)
while true; do
    STATE=$(aws emr-serverless get-job-run \
        --application-id "${APP_ID}" \
        --job-run-id "${JOB_RUN_ID}" \
        --query 'jobRun.state' \
        --output text)

    if [[ "${STATE}" != "SUBMITTED" && "${STATE}" != "SCHEDULED" && "${STATE}" != "PENDING" ]]; then
        break
    fi

    ELAPSED=$(($(date +%s) - START_TIME))
    echo "  ⏳ State: ${STATE} (${ELAPSED}s elapsed) — cold-start can take ~30s..."
    sleep 5
done

echo "  ✓ Job is now ${STATE}"
echo

# -------------------------------------------------------------------
# Tail logs while running
# -------------------------------------------------------------------
echo "═══════════════════════════════════════════════════════════════"
echo "  Streaming logs from CloudWatch..."
echo "═══════════════════════════════════════════════════════════════"

# Wait a bit for log streams to exist, then tail
sleep 10

# Tail logs in background
aws logs tail "${LOG_GROUP}" --follow --since 2m &
TAIL_PID=$!

# Poll job state until terminal
while true; do
    STATE=$(aws emr-serverless get-job-run \
        --application-id "${APP_ID}" \
        --job-run-id "${JOB_RUN_ID}" \
        --query 'jobRun.state' \
        --output text)

    if [[ "${STATE}" == "SUCCESS" || "${STATE}" == "FAILED" || "${STATE}" == "CANCELLED" ]]; then
        break
    fi

    sleep 10
done

# Stop tailing logs
kill ${TAIL_PID} 2>/dev/null || true
wait ${TAIL_PID} 2>/dev/null || true

ELAPSED=$(($(date +%s) - START_TIME))

echo
echo "═══════════════════════════════════════════════════════════════"
echo "  Job finished"
echo "═══════════════════════════════════════════════════════════════"
echo "  Final state:   ${STATE}"
echo "  Total time:    ${ELAPSED}s"
echo "  Job run ID:    ${JOB_RUN_ID}"
echo "  Log group:     ${LOG_GROUP}"
echo "═══════════════════════════════════════════════════════════════"
echo

# Print full job run details
aws emr-serverless get-job-run \
    --application-id "${APP_ID}" \
    --job-run-id "${JOB_RUN_ID}" \
    --query 'jobRun.{state:state,createdAt:createdAt,updatedAt:updatedAt,totalResourceUtilization:totalResourceUtilization,billedResourceUtilization:billedResourceUtilization}' \
    --output table

if [[ "${STATE}" != "SUCCESS" ]]; then
    echo
    echo "⚠ Job did not succeed. View detailed logs:"
    echo "  aws logs tail ${LOG_GROUP} --since 30m"
    exit 1
fi

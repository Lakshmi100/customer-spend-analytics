###############################################################################
# Terraform-managed Spark job script.
#
# Replaces the manual ./upload_to_s3.sh step. The Spark entry point now lives
# in Terraform state — a clean destroy/apply restores it, and any local edit
# to the script is pushed to S3 on the next apply (etag change triggers it).
#
# Lives in the PERSISTENT stack (artifacts bucket is persistent), so it
# survives ephemeral teardowns. EMR Serverless — recreated each session in the
# ephemeral stack — always finds the script at the same stable S3 URI.
#
# APPEND this block to:
#   infra/aws/terraform/envs/dev/persistent/main.tf
#
# (Adjust the `source` path if your repo layout differs. path.root here is the
#  persistent env dir: infra/aws/terraform/envs/dev/persistent/)
###############################################################################

resource "aws_s3_object" "spark_tokenize_script" {
  bucket = module.storage.artifacts_bucket   # adjust if your output name differs
  key    = "spark_jobs/tokenize_and_partition.py"

  # Path from the persistent env dir up to the spark_jobs source.
  # infra/aws/terraform/envs/dev/persistent → ../../../../spark_jobs
  source = "${path.root}/../../../../spark_jobs/tokenize_and_partition.py"

  # Re-upload whenever the local script changes
  etag = filemd5("${path.root}/../../../../spark_jobs/tokenize_and_partition.py")

  content_type = "text/x-python"

  tags = {
    Component = "spark-job"
  }
}

###############################################################################
# APPEND to infra/aws/terraform/envs/dev/persistent/outputs.tf
###############################################################################

output "spark_tokenize_script_uri" {
  description = "S3 URI of the Terraform-managed Spark tokenization script"
  value       = "s3://${aws_s3_object.spark_tokenize_script.bucket}/${aws_s3_object.spark_tokenize_script.key}"
}

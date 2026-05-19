###############################################################################
# Outputs from the ephemeral stack.
###############################################################################

# EMR Serverless
output "emr_application_id" {
  description = "EMR Serverless application ID (use in start-job-run calls)"
  value       = module.emr_serverless.application_id
}

output "emr_application_name" {
  description = "EMR Serverless application name"
  value       = module.emr_serverless.application_name
}

output "emr_execution_role_arn" {
  description = "IAM role that Spark jobs run as"
  value       = module.emr_serverless.execution_role_arn
}

output "emr_log_group_name" {
  description = "CloudWatch log group for EMR job logs"
  value       = module.emr_serverless.log_group_name
}

output "_summary" {
  value = <<-EOT

    ════════════════════════════════════════════════════════════════
    ✓ EPHEMERAL stack deployed (Phase 2 — Chunk B2)
    ════════════════════════════════════════════════════════════════

    📦 Reading persistent state from:
       s3://csa-tfstate-039323921608/envs/dev/persistent/terraform.tfstate

    🔥 EMR Serverless
       Application ID:   ${module.emr_serverless.application_id}
       Application name: ${module.emr_serverless.application_name}
       Execution role:   ${module.emr_serverless.execution_role_arn}
       Log group:        ${module.emr_serverless.log_group_name}

    💡 To submit a job:
       cd ../../../../spark_jobs
       ./run_emr_job.sh

    💡 To watch logs:
       aws logs tail ${module.emr_serverless.log_group_name} --follow

    💰 Cold-start mode — $0 cost while no job is running
    💰 Auto-stops 5 min after job finishes

    Currently deployed in ephemeral:
       • EMR Serverless application (cold)
       • IAM execution role
       • CloudWatch log group

    To destroy at session end:
       make ephemeral-destroy

  EOT
}

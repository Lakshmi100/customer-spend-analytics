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

output "snowflake_loader_function_name" {
  description = "Snowflake loader Lambda function name"
  value       = module.snowflake_loader.function_name
}

output "snowflake_loader_function_arn" {
  description = "Snowflake loader Lambda function ARN (for Step Functions)"
  value       = module.snowflake_loader.function_arn
}

output "snowflake_loader_log_group" {
  description = "CloudWatch log group for the Snowflake loader"
  value       = module.snowflake_loader.log_group_name
}

output "delta_generator_function_name" {
  value = module.generate_daily_delta.function_name
}

output "delta_generator_function_arn" {
  description = "Use in Step Functions Resource field"
  value       = module.generate_daily_delta.function_arn
}

output "delta_generator_log_group" {
  value = module.generate_daily_delta.log_group_name
}

output "data_libs_layer_arn" {
  description = "Lambda layer ARN providing pandas + pyarrow + numpy + Faker"
  value       = module.data_libs_layer.layer_arn
}

output "data_libs_layer_version" {
  value = module.data_libs_layer.layer_version
}

output "pipeline_state_machine_arn" {
  description = "Step Functions state machine ARN (use in start-execution)"
  value       = module.step_functions.state_machine_arn
}

output "pipeline_state_machine_name" {
  value = module.step_functions.state_machine_name
}

output "pipeline_log_group" {
  value = module.step_functions.log_group_name
}

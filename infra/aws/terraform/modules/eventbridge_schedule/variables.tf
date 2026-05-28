variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine to trigger"
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge schedule expression (UTC). Default: 06:00 UTC daily."
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "rule_enabled" {
  description = "Whether the schedule fires (true) or is dormant (false)"
  type        = bool
  default     = true
}

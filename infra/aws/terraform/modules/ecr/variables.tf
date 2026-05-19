variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "repository_name" {
  description = "Suffix for the ECR repo name. e.g. 'api' produces 'csa-dev-api'"
  type        = string
  default     = "api"
}

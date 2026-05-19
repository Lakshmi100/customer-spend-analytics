###############################################################################
# Variables for the ephemeral stack.
#
# Most values come from persistent stack outputs (see data.tf).
# This file only contains values that are NOT in persistent state.
###############################################################################

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "csa"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "owner" {
  type    = string
  default = "lakshmi"
}

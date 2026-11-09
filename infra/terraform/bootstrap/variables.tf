variable "aws_account_id" {
  description = "AWS account the core stack lives in (guard-rail)."
  type        = string
  default     = "059898286291"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "ap-southeast-1"
}

variable "state_bucket" {
  description = "Globally-unique S3 bucket name for Terraform state."
  type        = string
  default     = "easyfundraise-tfstate-059898286291"
}

variable "lock_table" {
  description = "DynamoDB table name for state locking."
  type        = string
  default     = "easyfundraise-tflock"
}

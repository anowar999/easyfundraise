output "state_bucket" {
  description = "Put this in infra/terraform/core/backend.tf -> bucket."
  value       = aws_s3_bucket.state.id
}

output "lock_table" {
  description = "Put this in infra/terraform/core/backend.tf -> dynamodb_table."
  value       = aws_dynamodb_table.lock.name
}

output "region" {
  value = var.region
}

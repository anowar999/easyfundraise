# Remote-state bootstrap: creates the S3 bucket and DynamoDB table that the
# `core` stack uses as its Terraform backend. Run this ONCE per AWS account,
# with a LOCAL state (there is nowhere to store remote state yet).
#
#   cd infra/terraform/bootstrap
#   terraform init
#   terraform apply -var='state_bucket=easyfundraise-tfstate-059898286291'
#
# Then wire the output bucket/table into infra/terraform/core/backend.tf.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  # Guard-rail: refuse to run against the wrong account.
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project   = "easyfundraise"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  name         = var.lock_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

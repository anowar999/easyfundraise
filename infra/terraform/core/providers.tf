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

  # Guard-rail: this stack must only ever touch the core AWS account.
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project   = "easyfundraise"
      ManagedBy = "terraform"
      Stack     = "core"
      Env       = var.env
    }
  }
}

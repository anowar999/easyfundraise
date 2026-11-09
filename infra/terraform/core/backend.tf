# Remote state. Create the bucket + lock table first with infra/terraform/bootstrap,
# then fill these in (they are hard-coded here, not variables, because the backend
# block is read before variables are available).
#
# If you have not run bootstrap yet, comment this whole block out to use local state.
terraform {
  backend "s3" {
    bucket         = "easyfundraise-tfstate-059898286291"
    key            = "core/terraform.tfstate"
    region         = "ap-southeast-1"
    dynamodb_table = "easyfundraise-tflock"
    encrypt        = true
  }
}

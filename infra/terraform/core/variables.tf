variable "aws_account_id" {
  description = "AWS account for the core + db instances."
  type        = string
  default     = "059898286291"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "ap-southeast-1"
}

variable "env" {
  description = "Environment name (prod / uat / dev)."
  type        = string
  default     = "prod"
}

# --- Networking ---------------------------------------------------------------

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "Subnet that holds the core (public) instance."
  type        = string
  default     = "10.20.1.0/24"
}

variable "data_subnet_cidr" {
  description = "Subnet that holds the db instance."
  type        = string
  default     = "10.20.2.0/24"
}

variable "ssh_ingress_cidrs" {
  description = "CIDRs allowed to SSH into the core instance. Lock this to your IP(s)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "key_pair_name" {
  description = "Existing EC2 key pair name for SSH. Create one in the console/CLI first."
  type        = string
}

# --- Instances ----------------------------------------------------------------

variable "core_instance_type" {
  description = "Core box (api + web + worker in Docker). Keep it small but able to run containers."
  type        = string
  default     = "t3.small"
}

variable "db_instance_type" {
  description = "DB box (PostgreSQL 16 direct, no Docker)."
  type        = string
  default     = "t3.micro"
}

variable "core_root_gb" {
  description = "Root volume size for the core box."
  type        = number
  default     = 20
}

variable "db_root_gb" {
  description = "Root volume size for the db box (holds the Postgres data dir)."
  type        = number
  default     = 30
}

variable "db_data_public_ip" {
  description = "Give the db box a public IP for outbound package installs (cheap, no NAT). Inbound stays locked to the core SG. Set false once you add a NAT gateway."
  type        = bool
  default     = true
}

# --- Database -----------------------------------------------------------------

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "easyfundraise"
}

variable "db_user" {
  description = "Application database role."
  type        = string
  default     = "ef"
}

variable "db_password" {
  description = "Application database password. Set via TF_VAR_db_password or a secret store; do NOT commit it."
  type        = string
  sensitive   = true
}

# --- DNS ----------------------------------------------------------------------

variable "manage_dns" {
  description = "Whether to create the Route53 A record. Requires an existing hosted zone."
  type        = bool
  default     = true
}

variable "domain_name" {
  description = "Public hostname for the core app."
  type        = string
  default     = "efcore.doctra.ai"
}

variable "hosted_zone_name" {
  description = "Route53 hosted zone the record lives in (with trailing dot)."
  type        = string
  default     = "doctra.ai."
}

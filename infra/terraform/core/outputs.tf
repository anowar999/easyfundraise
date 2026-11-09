output "core_public_ip" {
  description = "Elastic IP of the core box. Point the deploy workflow's CORE_SSH_HOST here."
  value       = aws_eip.core.public_ip
}

output "core_instance_id" {
  value = aws_instance.core.id
}

output "db_private_ip" {
  description = "Private IP the app connects to for Postgres."
  value       = aws_instance.db.private_ip
}

output "db_instance_id" {
  value = aws_instance.db.id
}

output "app_url" {
  value = var.manage_dns ? "https://${var.domain_name}" : "http://${aws_eip.core.public_ip}"
}

output "database_url" {
  description = "EF_DATABASE_URL for the core .env (password redacted)."
  value       = "postgresql+psycopg://${var.db_user}:<password>@${aws_instance.db.private_ip}:5432/${var.db_name}"
}

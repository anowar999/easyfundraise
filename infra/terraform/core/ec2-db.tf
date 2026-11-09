# easyfundraise-db: PostgreSQL 16 + pgvector, direct on the host (no Docker).
resource "aws_instance" "db" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.db_instance_type
  subnet_id              = aws_subnet.data.id
  vpc_security_group_ids = [aws_security_group.db.id]
  key_name               = var.key_pair_name

  user_data = templatefile("${path.module}/cloud-init/db.sh.tftpl", {
    db_name     = var.db_name
    db_user     = var.db_user
    db_password = var.db_password
    vpc_cidr    = var.vpc_cidr
  })
  # Re-run bootstrap if the template changes.
  user_data_replace_on_change = true

  root_block_device {
    volume_size = var.db_root_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "easyfundraise-db" }
}

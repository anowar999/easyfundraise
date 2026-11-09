# easyfundraise-core: runs api + web + worker as Docker containers.
resource "aws_instance" "core" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.core_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.core.id]
  key_name               = var.key_pair_name

  user_data = templatefile("${path.module}/cloud-init/core.sh.tftpl", {
    db_host = aws_instance.db.private_ip
  })
  user_data_replace_on_change = true

  root_block_device {
    volume_size = var.core_root_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "easyfundraise-core" }
}

# Stable public IP for the core box so the DNS record never has to change.
resource "aws_eip" "core" {
  instance = aws_instance.core.id
  domain   = "vpc"
  tags     = { Name = "easyfundraise-core" }
}

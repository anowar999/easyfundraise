# Core box: public HTTP/HTTPS + SSH.
resource "aws_security_group" "core" {
  name        = "easyfundraise-${var.env}-core"
  description = "core app box"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_ingress_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "easyfundraise-${var.env}-core" }
}

# DB box: reachable ONLY from the core box. No public ingress at all.
resource "aws_security_group" "db" {
  name        = "easyfundraise-${var.env}-db"
  description = "postgres box - private to core"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from core only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.core.id]
  }

  ingress {
    description     = "SSH via core (bastion) only"
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.core.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "easyfundraise-${var.env}-db" }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "easyfundraise-${var.env}" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "easyfundraise-${var.env}" }
}

# Public subnet: the core box lives here (public IP, serves web + SSH).
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "easyfundraise-${var.env}-public" }
}

# Data subnet: the db box lives here. No inbound from the internet (enforced by
# its security group); it only talks to the core box.
resource "aws_subnet" "data" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.data_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = var.db_data_public_ip
  tags                    = { Name = "easyfundraise-${var.env}-data" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "easyfundraise-${var.env}-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# The data subnet shares the public route table ONLY so the db box can reach the
# internet for package installs/updates. Inbound is still blocked by its SG.
# Harden later: give the data subnet its own route table behind a NAT gateway and
# set db_data_public_ip = false.
resource "aws_route_table_association" "data" {
  subnet_id      = aws_subnet.data.id
  route_table_id = aws_route_table.public.id
}

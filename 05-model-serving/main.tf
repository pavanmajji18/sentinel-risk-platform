# ─── VPC ───────────────────────────────────────────────────────
resource "aws_vpc" "sentinel" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name    = "sentinel-vpc"
    Project = "sentinel"
  }
}

# ─── Subnet ────────────────────────────────────────────────────
resource "aws_subnet" "sentinel" {
  vpc_id                  = aws_vpc.sentinel.id
  cidr_block              = var.subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name    = "sentinel-subnet"
    Project = "sentinel"
  }
}

# ─── Internet Gateway ─────────────────────────────────────────
resource "aws_internet_gateway" "sentinel" {
  vpc_id = aws_vpc.sentinel.id

  tags = {
    Name    = "sentinel-igw"
    Project = "sentinel"
  }
}

# ─── Route Table ──────────────────────────────────────────────
resource "aws_route_table" "sentinel" {
  vpc_id = aws_vpc.sentinel.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.sentinel.id
  }

  tags = {
    Name    = "sentinel-rt"
    Project = "sentinel"
  }
}

resource "aws_route_table_association" "sentinel" {
  subnet_id      = aws_subnet.sentinel.id
  route_table_id = aws_route_table.sentinel.id
}

# ─── Security Group ───────────────────────────────────────────
resource "aws_security_group" "sentinel" {
  name        = "sentinel-gpu-sg"
  description = "SENTINEL GPU VM access"
  vpc_id      = aws_vpc.sentinel.id

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # API
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Egress
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "sentinel-sg"
    Project = "sentinel"
  }
}

# ─── S3 Buckets ──────────────────────────────────────────────
resource "aws_s3_bucket" "sentinel_data" {
  bucket        = "sentinel-data-${var.environment}"
  force_destroy = true

  tags = {
    Name    = "sentinel-data"
    Project = "sentinel"
  }
}

resource "aws_s3_bucket" "sentinel_logs" {
  bucket        = "sentinel-logs-${var.environment}"
  force_destroy = true

  tags = {
    Name    = "sentinel-logs"
    Project = "sentinel"
  }
}

# ─── IAM Role for EC2 ────────────────────────────────────────
resource "aws_iam_role" "sentinel" {
  name = "sentinel-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "sentinel"
  }
}

resource "aws_iam_role_policy_attachment" "sentinel_s3_read" {
  role       = aws_iam_role.sentinel.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

resource "aws_iam_instance_profile" "sentinel" {
  name = "sentinel-instance-profile"
  role = aws_iam_role.sentinel.name
}

# ─── GPU EC2 Instance ────────────────────────────────────────
resource "aws_instance" "sentinel_gpu" {
  ami                    = var.ami_id != "" ? var.ami_id : "ami-0c55b159cbfafe1f3"
  instance_type          = var.gpu_instance_type
  subnet_id              = aws_subnet.sentinel.id
  vpc_security_group_ids = [aws_security_group.sentinel.id]
  iam_instance_profile   = aws_iam_instance_profile.sentinel.name

  key_name = var.key_pair_name != "" ? var.key_pair_name : null

  user_data = <<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y python3-pip python3-venv docker.io
    systemctl start docker
    pip3 install fastapi uvicorn xgboost scikit-learn numpy pandas
  EOF

  root_block_device {
    volume_size = 100
    volume_type = "gp3"
  }

  instance_initiated_shutdown_behavior = "terminate"

  tags = {
    Name    = "sentinel-gpu"
    Project = "sentinel"
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

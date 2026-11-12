# Sentinel user group with custom least-privilege policy (loaded from iam_policy.json)
resource "aws_iam_group" "sentinel" {
  name = "sentinel-team"
}

resource "aws_iam_group_policy" "sentinel" {
  name   = "sentinel-least-privilege"
  group  = aws_iam_group.sentinel.name
  policy = replace(
    file("${path.module}/iam_policy.json"),
    "$${var.aws_account_id}",
    var.aws_account_id != "*" ? var.aws_account_id : "*"
  )
}

# Sentinel IAM user added to the group
resource "aws_iam_user" "sentinel" {
  name = "sentinel-deployer"
}

resource "aws_iam_user_group_membership" "sentinel" {
  user   = aws_iam_user.sentinel.name
  groups = [aws_iam_group.sentinel.name]
}

# EC2 instance IAM role
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
    Name = "sentinel-ec2-role"
  }
}

resource "aws_iam_instance_profile" "sentinel" {
  name = "sentinel-instance-profile"
  role = aws_iam_role.sentinel.name
}

# EC2 instance role with least-privilege (no AdminAccess)
data "aws_iam_policy_document" "sentinel_ec2_role" {
  statement {
    sid = "S3CorpusAccess"
    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]
    resources = [
      "arn:aws:s3:::sentinel-corpus-*",
      "arn:aws:s3:::sentinel-corpus-*/*"
    ]
  }

  statement {
    sid = "EC2DescribeRead"
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeInstanceTypes"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sentinel_ec2" {
  name   = "sentinel-ec2-least-privilege"
  role   = aws_iam_role.sentinel.name
  policy = data.aws_iam_policy_document.sentinel_ec2_role.json
}

# ---------------------------------------------------------------------------
# Security Groups (ALB open on 80; EC2 reachable only from ALB)
# ---------------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "sentinel-alb-sg"
  description = "Allow inbound HTTP to Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from allowed CIDR blocks"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sentinel-alb-sg"
  }
}

resource "aws_security_group" "ec2" {
  name        = "sentinel-ec2-sg"
  description = "Allow inbound traffic from ALB only on port 8000"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Traffic from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sentinel-ec2-sg"
  }
}

# Sentinel user group with custom least-privilege policy (no AdminAccess)
resource "aws_iam_group" "sentinel" {
  name = "sentinel-team"
}

data "aws_iam_policy_document" "sentinel_least_privilege" {
  # EC2: run, terminate, describe instances, manage security groups / subnets / VPC
  statement {
    sid = "SentinelEC2Manage"
    actions = [
      "ec2:RunInstances",
      "ec2:TerminateInstances",
      "ec2:DescribeInstances",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeVpcs",
      "ec2:DescribeInternetGateways",
      "ec2:DescribeLaunchTemplates",
      "ec2:DescribeImages",
      "ec2:CreateTags",
      "ec2:CreateSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:DeleteSecurityGroup"
    ]
    resources = ["*"]
  }

  # VPC / networking
  statement {
    sid = "SentinelVPCManage"
    actions = [
      "ec2:CreateVpc",
      "ec2:DeleteVpc",
      "ec2:CreateInternetGateway",
      "ec2:DeleteInternetGateway",
      "ec2:AttachInternetGateway",
      "ec2:DetachInternetGateway",
      "ec2:CreateRouteTable",
      "ec2:DeleteRouteTable",
      "ec2:CreateRoute",
      "ec2:DeleteRoute",
      "ec2:AssociateRouteTable",
      "ec2:DisassociateRouteTable",
      "ec2:CreateSubnet",
      "ec2:DeleteSubnet"
    ]
    resources = ["*"]
  }

  # ALB
  statement {
    sid = "SentinelALBManage"
    actions = [
      "elasticloadbalancing:CreateLoadBalancer",
      "elasticloadbalancing:DeleteLoadBalancer",
      "elasticloadbalancing:CreateTargetGroup",
      "elasticloadbalancing:DeleteTargetGroup",
      "elasticloadbalancing:RegisterTargets",
      "elasticloadbalancing:DeregisterTargets",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth",
      "elasticloadbalancing:ModifyTargetGroup",
      "elasticloadbalancing:ModifyLoadBalancerAttributes",
      "elasticloadbalancing:AddTags",
      "elasticloadbalancing:RemoveTags"
    ]
    resources = ["*"]
  }

  # IAM roles for the EC2 instance profile
  statement {
    sid = "SentinelIAMRole"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:PassRole"
    ]
    resources = ["arn:aws:iam::*:role/sentinel-*"]
  }

  # S3: sentinel-corpus buckets only
  statement {
    sid = "SentinelS3Bucket"
    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      "arn:aws:s3:::sentinel-corpus-*",
      "arn:aws:s3:::sentinel-corpus-*/*"
    ]
  }
}

resource "aws_iam_group_policy" "sentinel" {
  name   = "sentinel-least-privilege"
  group  = aws_iam_group.sentinel.name
  policy = data.aws_iam_policy_document.sentinel_least_privilege.json
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

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
  user  = aws_iam_user.sentinel.name
  group = aws_iam_group.sentinel.name
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

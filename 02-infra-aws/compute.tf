# Generate a random API key

resource "random_password" "api_key" {
  length           = 32
  special          = false
  override_special = "ABCDEF"
}

# EC2 instances

resource "aws_instance" "api" {
  count                  = var.instance_count
  ami                    = var.ami_id != "" ? var.ami_id : data.aws_ami.amazon_linux[0].id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.sentinel.name

  user_data = <<-EOF
              #!/bin/bash
              set -e

              # Set the API key as a persistent environment variable
              echo "export SENTINEL_API_KEY=${random_password.api_key.result}" >> /etc/profile.d/sentinel_api_key.sh
              export SENTINEL_API_KEY=${random_password.api_key.result}

              # Install Docker
              yum update -y
              yum install -y docker
              systemctl start docker
              systemctl enable docker

              # Create app directory and write files
              mkdir -p /opt/app

              cat > /opt/app/requirements.txt << 'REQEOF'
${file("${path.module}/app/requirements.txt")}
REQEOF

              cat > /opt/app/Dockerfile << 'DOCKEREOF'
${file("${path.module}/app/Dockerfile")}
DOCKEREOF

              echo "${base64gzip(file("${path.module}/app/main.py"))}" | base64 -d | gzip -d > /opt/app/main.py

              # Build and run the Docker container
              cd /opt/app
              docker build -t sentinel-api .
              docker run -d --name sentinel-api \
                -p 8000:8000 \
                -e SENTINEL_API_KEY=${random_password.api_key.result} \
                --restart=always \
                sentinel-api
              EOF

  tags = {
    Name = "sentinel-api"
  }
}

# Look up latest Amazon Linux 2023 AMI (when ami_id is not explicitly provided)

data "aws_ami" "amazon_linux" {
  count       = var.ami_id == "" ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

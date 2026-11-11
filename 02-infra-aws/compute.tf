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
              fastapi>=0.115.0
              uvicorn>=0.34.0
              pydantic>=2.10.0
              REQEOF

              cat > /opt/app/main.py << 'PYEOF'
              from fastapi import FastAPI, Depends, HTTPException, Header
              from typing import Optional
              import os

              app = FastAPI(title="Sentinel Risk API")

              SENTINEL_API_KEY = os.environ.get("SENTINEL_API_KEY", "")


              def verify_api_key(
                  x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
              ):
                  if x_api_key is None:
                      raise HTTPException(status_code=401, detail="X-API-Key header required")
                  if x_api_key != SENTINEL_API_KEY:
                      raise HTTPException(status_code=401, detail="Invalid API key")
                  return x_api_key


              @app.get("/health")
              def health():
                  return {"status": "ok"}


              @app.get("/score")
              def score(
                  text: str = "",
                  _key: str = Depends(verify_api_key),
              ):
                  risk_words = ["fraud", "scam", "phishing", "malware", "hacker", "stolen"]
                  score_value = sum(1 for word in risk_words if word.lower() in text.lower())
                  level = "low"
                  if score_value >= 3:
                      level = "high"
                  elif score_value >= 1:
                      level = "medium"
                  return {"text": text, "score": score_value, "level": level}
              PYEOF

              cat > /opt/app/Dockerfile << 'DOCKEREOF'
              FROM python:3.11-slim
              WORKDIR /app
              COPY requirements.txt .
              RUN pip install --no-cache-dir -r requirements.txt
              COPY main.py .
              EXPOSE 8000
              CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
              DOCKEREOF

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

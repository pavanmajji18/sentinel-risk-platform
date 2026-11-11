provider "aws" {
  region = var.aws_region
  # Credentials are read automatically from environment variables:
  #   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
}

provider "random" {}

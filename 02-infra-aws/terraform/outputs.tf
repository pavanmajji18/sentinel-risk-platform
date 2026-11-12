output "api_url" {
  description = "The public URL of the API (ALB DNS name)"
  value       = "http://${aws_lb.api.dns_name}"
}

output "api_key" {
  description = "The generated API key for authentication"
  value       = random_password.api_key.result
  sensitive   = true
}

output "health_url" {
  description = "Health check endpoint URL"
  value       = "http://${aws_lb.api.dns_name}/health"
}

output "deployer_iam_user" {
  description = "The dedicated non-root IAM user for deployment"
  value       = aws_iam_user.sentinel.name
}

output "deployer_access_key_id" {
  description = "Access Key ID for sentinel-deployer"
  value       = aws_iam_access_key.sentinel.id
}

output "deployer_secret_access_key" {
  description = "Secret Access Key for sentinel-deployer"
  value       = aws_iam_access_key.sentinel.secret
  sensitive   = true
}

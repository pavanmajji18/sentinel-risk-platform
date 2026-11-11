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

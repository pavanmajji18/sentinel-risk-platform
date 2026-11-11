output "container_id" {
  description = "ID of the running Docker container"
  value       = docker_container.sentinel.id
}

output "api_url" {
  description = "Base URL of the Sentinel Risk API"
  value       = local.application_url
}

output "swagger_url" {
  description = "URL for the Swagger UI documentation"
  value       = "${local.application_url}/docs"
}

output "health_url" {
  description = "URL for the health-check endpoint"
  value       = "${local.application_url}/health"
}

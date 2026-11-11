variable "project_name" {
  description = "Name of the project used for Docker resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "internal_port" {
  description = "Port the application listens on inside the container"
  type        = number
  default     = 8000
}

variable "external_port" {
  description = "Port exposed on the host machine"
  type        = number

  validation {
    condition     = var.external_port >= 1024 && var.external_port <= 65535
    error_message = "External port must be between 1024 and 65535."
  }
}

variable "container_name" {
  description = "Name for the running Docker container"
  type        = string
  default     = ""
}

variable "sentinel_api_key" {
  description = "API key required for authenticated endpoints"
  type        = string
  sensitive   = true
}

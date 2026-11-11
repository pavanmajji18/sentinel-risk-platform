locals {
  container_name  = var.container_name != "" ? var.container_name : "${var.project_name}-${var.environment}"
  image_name      = "${var.project_name}/${var.project_name}"
  application_url = "http://localhost:${var.external_port}"
}

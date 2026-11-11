resource "docker_image" "sentinel" {
  name = local.image_name

  build {
    context = "./app"
  }

  triggers = {
    filemd5 = filemd5("${path.module}/app/main.py")
  }
}

resource "docker_container" "sentinel" {
  name  = local.container_name
  image = docker_image.sentinel.name

  must_run = true

  ports {
    internal = var.internal_port
    external = var.external_port
  }

  env = ["SENTINEL_API_KEY=${var.sentinel_api_key}"]

  lifecycle {
    replace_triggered_by = [
      docker_image.sentinel,
    ]
  }
}

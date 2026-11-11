output "public_ip" {
  description = "Public IP of the GPU instance"
  value       = aws_instance.sentinel_gpu.public_ip
}

output "api_url" {
  description = "URL of the SENTINEL model API"
  value       = "http://${aws_instance.sentinel_gpu.public_ip}:8000"
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.sentinel_gpu.id
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.sentinel.id
}

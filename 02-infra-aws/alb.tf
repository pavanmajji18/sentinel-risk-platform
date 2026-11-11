# Application Load Balancer

resource "aws_lb" "api" {
  name               = "sentinel-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]

  tags = {
    Name = "sentinel-alb"
  }
}

# Target group

resource "aws_lb_target_group" "api" {
  name     = "sentinel-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 10
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = {
    Name = "sentinel-tg"
  }
}

# Target group attachments for each EC2 instance

resource "aws_lb_target_group_attachment" "api" {
  count            = var.instance_count
  target_group_arn = aws_lb_target_group.api.arn
  target_id        = aws_instance.api[count.index].id
  port             = 8000
}

# Listener on port 80 -> forward to target group

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

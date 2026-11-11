# SENTINEL — AWS Cloud Infrastructure (Module 02)

Declarative, production-grade cloud infrastructure provisioning on Amazon Web Services using **Terraform**. Implements network isolation, automated load balancing, containerized compute provisioning, and least-privilege identity access management.

---

## Infrastructure Architecture

```
                                  Internet
                                     │
                             [ Port 80 HTTP ]
                                     │
                       ┌─────────────▼─────────────┐
                       │  Application Load Balancer │
                       │    (sentinel-alb-sg)      │
                       └─────────────┬─────────────┘
                                     │
              ┌──────────────────────┴──────────────────────┐
              │                                             │
      Subnet: us-east-1a                            Subnet: us-east-1b
              │                                             │
       [ Port 8000 ]                                 (Failover / Spare)
              │
    ┌─────────▼─────────┐
    │   EC2 Instance    │
    │ (sentinel-ec2-sg) │
    │   Docker Daemon   │
    │   FastAPI App     │
    └───────────────────┘
```

---

## Provisioned AWS Resources (22 Planned Elements)

### 1. Networking & VPC Topology (`vpc.tf`)
* **Virtual Private Cloud (VPC):** `10.0.0.0/16` CIDR with DNS resolution and hostnames enabled.
* **Public Subnets:** Multi-AZ layout across `us-east-1a` (`10.0.1.0/24`) and `us-east-1b` (`10.0.2.0/24`) for load balancer high availability.
* **Internet Gateway & Route Tables:** Custom internet gateway (`sentinel-igw`) associated with public subnets.

### 2. Security Groups & Network Firewalls (`security.tf`)
* **ALB Security Group (`sentinel-alb-sg`):** Restricts inbound access to HTTP port 80 from configurable CIDRs (e.g., corporate VPN or public perimeter).
* **EC2 Security Group (`sentinel-ec2-sg`):** Restricts application port 8000 inbound traffic **exclusively** to requests originating from `sentinel-alb-sg`. Direct public ingress to compute nodes is strictly blocked.

### 3. Compute & Bootstrap Automation (`compute.tf`)
* **EC2 Instance:** `t3.micro` compute running Amazon Linux 2023.
* **AMI Handling:** Automatic lookup of latest official Amazon Linux 2023 HVM AMI, with support for explicit `ami_id` overrides.
* **Cloud-Init Bootstrapping:** User data script automatically installs the Docker runtime, provisions application container files, builds the isolated container, and launches the service with system restart policies.
* **API Key Generation:** Built-in `random_password.api_key` generates a cryptographically secure 32-character authentication token injected directly into the instance environment.

### 4. Load Balancing & Health Probes (`alb.tf`)
* **Application Load Balancer (`aws_lb.api`):** External load balancer distributed across both availability zones.
* **Target Group & Health Check:** Routes traffic to compute targets on port 8000, running active HTTP health probes against `GET /health` with a 30-second interval.

### 5. Identity & Access Management (`security.tf`)
* **IAM Instance Profile & Role (`sentinel-ec2-role`):** Enables compute instances to assume least-privilege cloud roles without local credentials.
* **Least-Privilege Group Policy:** Explicit granular actions for EC2, VPC, ALB, and CloudWatch operations, avoiding administrative wildcard policies.

---

## Configuration & Variables

Copy `terraform.tfvars.example` to `terraform.tfvars` (untracked):

```hcl
aws_region          = "us-east-1"
instance_type       = "t3.micro"
instance_count      = 1
allowed_cidr_blocks = ["YOUR_OFFICE_OR_VPN_IP/32"]

# Optional: Set explicit AMI ID if organizational SCP blocks ec2:DescribeImages
ami_id              = "ami-0c101f26f147fa7fd"
```

---

## Deployment & Verification Workflow

### 1. Initialize Providers & Modules
```bash
terraform init
```

### 2. Validate Syntax & Provider Schemas
```bash
terraform validate
```

### 3. Generate Dry-Run Execution Plan
```bash
terraform plan
```

### 4. Apply (Staging / Production)
```bash
terraform apply
```

### 5. Inspect Outputs
```bash
terraform output api_url
terraform output health_url
terraform output -raw api_key
```

### 6. Decommission Infrastructure
```bash
terraform destroy
```

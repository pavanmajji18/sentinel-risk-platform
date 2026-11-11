# SENTINEL — AWS Infrastructure

Terraform-only infrastructure provisioning for deploying the SENTINEL Risk API
on AWS. Creates a production-ready environment with networking, compute,
load balancing, storage and security.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          AWS VPC                                 │
│                                                                  │
│  ┌──────────────────┐       ┌──────────────────┐                │
│  │   Public Subnet  │       │   Public Subnet  │                │
│  │   (AZ-1)         │       │   (AZ-2)         │                │
│  │                  │       │                  │                │
│  │  ┌────────────┐  │       │  ┌────────────┐  │                │
│  │  │   ALB      │  │       │  │   ALB      │  │                │
│  │  │ (Health    │  │       │  │ (Health    │  │                │
│  │  │  Checks)   │  │       │  │  Checks)   │  │                │
│  │  └─────┬──────┘  │       │  └─────┬──────┘  │                │
│  │        │         │       │        │         │                │
│  │  ┌─────┴──────┐  │       │  ┌─────┴──────┐  │                │
│  │  │  EC2       │  │       │  │  EC2       │  │                │
│  │  │  (Risk API)│  │       │  │  (Risk API)│  │                │
│  │  └────────────┘  │       │  └────────────┘  │                │
│  └──────────────────┘       └──────────────────┘                │
│                                                                  │
│  ┌──────────────────┐       ┌──────────────────┐                │
│  │  Private Subnet  │       │  Private Subnet  │                │
│  │  (AZ-1)          │       │  (AZ-2)          │                │
│  └──────────────────┘       └──────────────────┘                │
│                                                                  │
│  ┌─────────────────────────────────────────┐                    │
│  │            S3 Bucket                     │                    │
│  │     (Model Artifacts + Data)             │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
│  ┌─────────────────────────────────────────┐                    │
│  │            IAM Role & Policy             │                    │
│  │   (S3 Read + CloudWatch Logs)            │                    │
│  └─────────────────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
```

## Resources Created

### Networking
- **VPC:** Custom VPC with CIDR block defined in variables
- **Subnets:** Public and private subnets across multiple availability zones
- **Internet Gateway:** Enables outbound internet access
- **Route Tables:** Separate routing for public and private subnets

### Compute
- **EC2 Instances:** t3.micro instances running the Risk API application
- **Launch Template:** Standardised AMI, instance type and security group
- **Auto Scaling:** (Optional) Scale based on load

### Load Balancing
- **Application Load Balancer:** Distributes traffic across EC2 instances
- **Target Group:** Health check configuration for instance readiness
- **Listener:** HTTP/HTTPS routing to target group

### Storage
- **S3 Bucket:** Stores model artifacts (`model.onnx`) and transaction data
- **Versioning:** (Optional) Enable for backup and recovery

### Security
- **Security Groups:**
  - ALB security group: Allow HTTP (80) and HTTPS (443) from anywhere
  - EC2 security group: Allow traffic only from ALB security group
- **IAM Role:** Attached to EC2 instances with minimal permissions:
  - `s3:GetObject`, `s3:ListBucket` for model/data access
  - `logs:*` for CloudWatch log delivery
- **SSH Key Pair:** For administrative access (optional IP restriction)

---

## Implementation Details

### `providers.tf`
Configures the AWS provider with region selection.

### `security.tf`
- Security group definitions for ALB and EC2
- Inbound/outbound rule restrictions
- SSH key management

### `iam_policy.json`
Least-privilege IAM policy granting:
- S3 read access for model and data files
- CloudWatch log write access for monitoring

### `variables.tf`
Configurable parameters:
- `region` — AWS region (default: `us-east-1`)
- `environment` — Deployment environment (`dev`, `staging`, `production`)
- `instance_type` — EC2 instance type (default: `t3.micro`)
- `vpc_cidr` — VPC CIDR block
- `ssh_key_name` — SSH key pair name for admin access

### Application Code
The `app/` directory contains the FastAPI application deployed to EC2 instances,
matching the Risk API from Component 1.

---

## Deployment Steps

### 1. Initialise Terraform
```bash
terraform init
```

### 2. Review the Plan
```bash
terraform plan -var="environment=production" -var="region=us-east-1"
```

### 3. Apply the Configuration
```bash
terraform apply -var="environment=production" -var="region=us-east-1"
```

### 4. Verify Deployment
```bash
# Check EC2 instance status
terraform output instance_id

# Check ALB DNS name
terraform output alb_dns_name
```

### 5. Upload Model Artifacts
```bash
aws s3 cp ../04-model-training/model.onnx s3://<bucket-name>/model.onnx
```

---

## Sentinel Data Integration

The S3 bucket stores:
- **Model artifacts:** `model.onnx` (ONNX-exported XGBoost model from Component 4)
- **Transaction data:** Client data used for scoring (excluded from repo via `.gitignore`)
- **Configuration files:** Environment-specific settings

The IAM policy ensures EC2 instances can read these files without hardcoded credentials.

---

## File Structure

```
02-infra-aws/
├── README.md             # This file
├── providers.tf          # AWS provider configuration
├── security.tf           # Security groups and networking
├── variables.tf          # Configurable variables
├── iam_policy.json       # IAM role policy
└── app/
    ├── main.py           # Risk API application code
    └── requirements.txt  # Python dependencies
```

---

See the top-level [README.md](../README.md) for the full platform architecture.

---

## Security Notes

| Item | Status | Production Guidance |
|------|--------|---------------------|
| ALB listener protocol | HTTP (port 80) | Add ACM certificate + HTTPS listener (port 443) before production |
| IAM policy | Least-privilege (no AdministratorAccess) | Scope EC2 ARNs further if multi-account |
| API key enforcement | Application-layer only | For higher assurance, add an AWS API Gateway with usage plans |
| SSH access | Restricted to ALB-sourced SG on EC2 | Use AWS Systems Manager Session Manager instead of open SSH |
| Credentials | Environment variables via `.env` (never committed) | Use AWS Secrets Manager or IAM Instance Profile in production |

> **Note:** The `.env` file is listed in `.gitignore` and **must never be committed**.
> Use `aws configure` or IAM Instance Profiles instead of hardcoded keys in production.

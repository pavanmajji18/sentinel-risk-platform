# SENTINEL — AWS Cloud Infrastructure & Authenticated Risk Service (Module 02)

Declarative, production-grade cloud infrastructure provisioning on Amazon Web Services using **Terraform** (`hashicorp/aws` and `hashicorp/random` providers). Implements multi-AZ VPC network isolation, an Application Load Balancer with active `/health` checks, ALB-only compute security group ingress, containerized FastAPI risk service deployment via cloud-init user data, cryptographically generated API key protection, and least-privilege IAM policies.

---

## Architecture Diagram

```
                                      Internet
                                         │
                             [ Inbound Port 80 HTTP ]
                                         │
                           ┌─────────────▼─────────────┐
                           │ Application Load Balancer │
                           │     (sentinel-alb-sg)     │
                           └─────────────┬─────────────┘
                                         │
                  ┌──────────────────────┴──────────────────────┐
                  │                                             │
          Subnet: us-east-1a                            Subnet: us-east-1b
          CIDR: 10.0.1.0/24                             CIDR: 10.0.2.0/24
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

### Security Ingress Boundary
* **ALB Security Group (`sentinel-alb-sg`):** Inbound HTTP port 80 allowed from configurable CIDRs (`0.0.0.0/0` by default or restricted corporate VPN / client IP).
* **EC2 Security Group (`sentinel-ec2-sg`):** Inbound application port 8000 allowed **exclusively** from `sentinel-alb-sg` via source security group reference. Direct public ingress to compute nodes is strictly blocked.
* **API Key Enforcement:** All scoring endpoints (`POST /score`, `POST /score/v1`, `POST /score/batch`, `GET /score`) require an `X-API-Key` header matching the generated key. Requests without or with an invalid key receive `HTTP 401 Unauthorized`. The `/health` endpoint remains unauthenticated for ALB probes.

---

## Complete Terraform File Inventory

| File | Purpose | Key Resources & Providers |
|---|---|---|
| `version.tf` | Terraform & provider requirements | `terraform >= 1.5`, `hashicorp/aws >= 5.0`, `hashicorp/random >= 3.0` |
| `provider.tf` | AWS & Random provider configuration | `provider "aws"` (region `var.aws_region`), `provider "random"` |
| `variable.tf` | Parameterized deployment settings | `aws_region` (`us-east-1`), `instance_type` (`t3.micro`), `instance_count` (`1`), `allowed_cidr_blocks`, `ami_id`, `aws_account_id` |
| `vpc.tf` | Multi-AZ network topology | `aws_vpc` (`10.0.0.0/16`), `aws_subnet` (`public_a`, `public_b`), `aws_internet_gateway`, `aws_route_table`, associations |
| `security.tf` | Security groups & IAM privileges | `aws_security_group` (`alb`, `ec2`), `aws_iam_group`, `aws_iam_group_policy` (loads `iam_policy.json`), `aws_iam_user`, `aws_iam_role`, instance profile |
| `compute.tf` | Compute & container bootstrap | `random_password.api_key` (32 chars), `aws_instance.api` (`t3.micro`), user data Docker setup |
| `alb.tf` | Load balancing & target groups | `aws_lb.api`, `aws_lb_target_group` (`/health` probe), `aws_lb_target_group_attachment`, `aws_lb_listener` (port 80) |
| `outputs.tf` | Exposed infrastructure attributes | `api_url` (ALB DNS), `api_key` (sensitive), `health_url` |
| `iam_policy.json` | Declarative least-privilege policy | Explicit actions for EC2, VPC, ALB, and IAM role passing (no AdminAccess) |

---

## 1. IAM Credentials & AWS CLI Configuration

Per project requirements, provisioning must use a dedicated, non-root IAM user with least-privilege permissions loaded from `iam_policy.json`.

### Step 1.1: Create Dedicated IAM User
Create user `sentinel-deployer` (via AWS Console or AWS CLI):
```bash
aws iam create-user --user-name sentinel-deployer
```

### Step 1.2: Attach Least-Privilege Policy from `iam_policy.json`
Apply the project's declarative policy document:
```bash
aws iam put-user-policy \
  --user-name sentinel-deployer \
  --policy-name SentinelDeployerPolicy \
  --policy-document file://iam_policy.json
```

### Step 1.3: Generate Access Keys
```bash
aws iam create-access-key --user-name sentinel-deployer
```
*Save the returned `AccessKeyId` and `SecretAccessKey` securely.*

### Step 1.4: Configure AWS CLI & Region
Run `aws configure` and establish `us-east-1` as the designated region:
```bash
aws configure
# AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
# AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
# Default region name [None]: us-east-1
# Default output format [None]: json
```

Verify caller identity and region:
```bash
aws sts get-caller-identity
# Output:
# {
#     "UserId": "AIDASENTINELDEPLOYER",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/sentinel-deployer"
# }
```

### Step 1.5: Secret Hygiene & Environment Setup
Copy `.env.example` to `.env` (git-ignored) for local overrides if needed:
```bash
cp .env.example .env
```
Copy `terraform.tfvars.example` to `terraform.tfvars` (git-ignored):
```bash
cp terraform.tfvars.example terraform.tfvars
```

---

## 2. Terraform Deployment Workflow (Saved Plan)

### Step 2.1: Initialize Providers & Backend
```bash
terraform init
```
```
Initializing the backend...
Initializing provider plugins...
- Finding hashicorp/aws versions >= 5.0.0...
- Finding hashicorp/random versions >= 3.0.0...
- Installing hashicorp/aws v5.80.0...
- Installing hashicorp/random v3.6.3...
Terraform has been successfully initialized!
```

### Step 2.2: Validate Configuration
```bash
terraform validate
```
```
Success! The configuration is valid.
```

### Step 2.3: Generate & Save Execution Plan (`tfplan`)
To ensure reproducibility and eliminate configuration drift between planning and application, save the binary execution plan to `tfplan`:
```bash
terraform plan -out tfplan
```
```
Terraform used the selected providers to generate the following execution plan.
Resource actions are indicated with the following symbols:
  + create

Terraform will perform the following actions:

  # aws_iam_group.sentinel will be created
  + resource "aws_iam_group" "sentinel" { ... }

  # aws_iam_group_policy.sentinel will be created (loads iam_policy.json)
  + resource "aws_iam_group_policy" "sentinel" { ... }

  # aws_iam_instance_profile.sentinel will be created
  + resource "aws_iam_instance_profile" "sentinel" { ... }

  # aws_iam_role.sentinel will be created
  + resource "aws_iam_role" "sentinel" { ... }

  # aws_iam_role_policy.sentinel_ec2 will be created
  + resource "aws_iam_role_policy" "sentinel_ec2" { ... }

  # aws_iam_user.sentinel will be created
  + resource "aws_iam_user" "sentinel" { ... }

  # aws_iam_user_group_membership.sentinel will be created
  + resource "aws_iam_user_group_membership" "sentinel" { ... }

  # aws_instance.api[0] will be created (t3.micro, Docker user_data)
  + resource "aws_instance" "api" { ... }

  # aws_internet_gateway.main will be created
  + resource "aws_internet_gateway" "main" { ... }

  # aws_lb.api will be created (Application Load Balancer)
  + resource "aws_lb" "api" { ... }

  # aws_lb_listener.api will be created (port 80)
  + resource "aws_lb_listener" "api" { ... }

  # aws_lb_target_group.api will be created (health_check /health)
  + resource "aws_lb_target_group" "api" { ... }

  # aws_lb_target_group_attachment.api[0] will be created
  + resource "aws_lb_target_group_attachment" "api" { ... }

  # aws_route_table.public will be created
  + resource "aws_route_table" "public" { ... }

  # aws_route_table_association.public_a will be created
  + resource "aws_route_table_association" "public_a" { ... }

  # aws_route_table_association.public_b will be created
  + resource "aws_route_table_association" "public_b" { ... }

  # aws_security_group.alb will be created (ingress port 80)
  + resource "aws_security_group" "alb" { ... }

  # aws_security_group.ec2 will be created (ingress port 8000 from ALB only)
  + resource "aws_security_group" "ec2" { ... }

  # aws_subnet.public_a will be created (us-east-1a)
  + resource "aws_subnet" "public_a" { ... }

  # aws_subnet.public_b will be created (us-east-1b)
  + resource "aws_subnet" "public_b" { ... }

  # aws_vpc.main will be created (10.0.0.0/16)
  + resource "aws_vpc" "main" { ... }

  # random_password.api_key will be created (32 characters)
  + resource "random_password" "api_key" { ... }

Plan: 22 to add, 0 to change, 0 to destroy.

Saved the plan to: tfplan
To perform exactly these actions, run the following command to apply:
    terraform apply tfplan
```

### Step 2.4: Apply the Saved Plan
```bash
terraform apply tfplan
```
```
random_password.api_key: Creating...
random_password.api_key: Creation complete after 0s [id=none]
aws_vpc.main: Creating...
aws_iam_group.sentinel: Creating...
aws_iam_role.sentinel: Creating...
aws_iam_user.sentinel: Creating...
...
aws_lb.api: Creating...
aws_lb.api: Still creating... [20s elapsed]
aws_lb.api: Creation complete after 2m12s [id=arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/sentinel-alb/1a2b3c4d5e6f]
aws_lb_listener.api: Creating...
aws_lb_listener.api: Creation complete after 1s

Apply complete! Resources: 22 added, 0 changed, 0 destroyed.

Outputs:

api_key = <sensitive>
api_url = "http://sentinel-alb-123456789.us-east-1.elb.amazonaws.com"
health_url = "http://sentinel-alb-123456789.us-east-1.elb.amazonaws.com/health"
```

### Step 2.5: Extract Outputs & API Key
```bash
export ALB_URL=$(terraform output -raw api_url)
export SENTINEL_API_KEY=$(terraform output -raw api_key)

echo "ALB URL: $ALB_URL"
echo "API Key length: ${#SENTINEL_API_KEY} characters"
```

---

## 3. ALB Endpoint Scoring Verification

### 3.1: Health Probe (Unauthenticated)
```bash
curl -i "$ALB_URL/health"
```
```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 53
Date: Wed, 12 Nov 2026 15:40:00 GMT

{"status":"healthy","model_loaded":true,"version":"2.0.0"}
```

### 3.2: Rejection on Missing API Key (HTTP 401)
```bash
curl -i -X POST "$ALB_URL/score" \
  -H "Content-Type: application/json" \
  -d '{
    "txn_id": "TX-9001",
    "customer_id": "CUST-1001",
    "merchant_id": "MERCH-5001",
    "device_id": "DEV-3001",
    "amount": 25000,
    "timestamp": "2024-12-25T03:15:00Z",
    "lat": 18.52,
    "lon": 73.86,
    "mcc_code": "MCC-5411",
    "channel": "CARD"
  }'
```
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Content-Length: 42
Date: Wed, 12 Nov 2026 15:40:02 GMT

{"detail":"Invalid or missing X-API-Key"}
```

### 3.3: Rejection on Incorrect API Key (HTTP 401)
```bash
curl -i -X POST "$ALB_URL/score" \
  -H "X-API-Key: invalid-key-xyz" \
  -H "Content-Type: application/json" \
  -d '{"txn_id":"TX-9001","customer_id":"CUST-1001","merchant_id":"MERCH-5001","device_id":"DEV-3001","amount":25000,"timestamp":"2024-12-25T03:15:00Z","lat":18.52,"lon":73.86,"mcc_code":"MCC-5411","channel":"CARD"}'
```
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Content-Length: 42

{"detail":"Invalid or missing X-API-Key"}
```

### 3.4: Successful Authenticated Scoring Request (HTTP 200)
```bash
curl -i -X POST "$ALB_URL/score" \
  -H "X-API-Key: $SENTINEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "txn_id": "TX-9001",
    "customer_id": "CUST-1001",
    "merchant_id": "MERCH-5001",
    "device_id": "DEV-3001",
    "amount": 25000,
    "timestamp": "2024-12-25T03:15:00Z",
    "lat": 18.52,
    "lon": 73.86,
    "mcc_code": "MCC-5411",
    "channel": "CARD"
  }'
```
```http
HTTP/1.1 200 OK
Content-Type: application/json
Date: Wed, 12 Nov 2026 15:40:06 GMT

{
  "txn_id": "TX-9001",
  "risk_score": 0.45,
  "risk_band": "MONITOR",
  "triggered_rules": [
    "FR02_NEW_DEVICE_HIGH_AMT",
    "R01_NEW_DEVICE",
    "R03_ODD_HOUR",
    "R10_NEW_CUSTOMER"
  ],
  "fraud_probability": 0.9995,
  "features": {
    "amount_to_avg_ratio": 5.0,
    "is_new_device": 1,
    "customer_merchant_distance_km": 0.0,
    "is_night": 1,
    "txn_count_last_1h": 0,
    "txn_amount_last_24h": 0.0,
    "failed_attempts": 0,
    "merchant_risk_score": 0.2,
    "customer_age_days": 0,
    "device_fingerprint_hash": 79
  },
  "recommendation": "flag_and_review",
  "explanation": "Transaction for CUST-1001 triggered 4 risk rule(s):\n  - FR02_NEW_DEVICE_HIGH_AMT\n  - R01_NEW_DEVICE\n  - R03_ODD_HOUR\n  - R10_NEW_CUSTOMER\n  -> Band: MONITOR | Action: flag_and_review"
}
```

### 3.5: Authenticated GET `/score` Verification
```bash
curl -i -H "X-API-Key: $SENTINEL_API_KEY" "$ALB_URL/score"
```
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "txn_id": "TX-DEMO-001",
  "risk_score": 0.4,
  "risk_band": "MONITOR",
  "triggered_rules": ["FR02_NEW_DEVICE_HIGH_AMT", "R01_NEW_DEVICE", "R10_NEW_CUSTOMER"],
  "fraud_probability": 0.9995,
  "recommendation": "flag_and_review"
}
```

---

## 4. Teardown & Cost Control Confirmation

To stay within the AWS Free Tier (`t3.micro` compute, single ALB) and avoid ongoing cloud costs, infrastructure must be destroyed on the same day following verification.

### Step 4.1: Execute Terraform Destroy
```bash
terraform destroy -auto-approve
```
```
aws_route_table_association.public_a: Destroying...
aws_route_table_association.public_b: Destroying...
aws_lb_listener.api: Destroying...
aws_lb_target_group_attachment.api[0]: Destroying...
aws_instance.api[0]: Destroying...
aws_lb.api: Destroying...
...
aws_security_group.ec2: Destruction complete after 2s
aws_security_group.alb: Destruction complete after 2s
aws_vpc.main: Destruction complete after 1s
random_password.api_key: Destruction complete after 0s

Destroy complete! Resources: 22 destroyed.
```

### Step 4.2: Resource Removal Verification Commands
Confirm via AWS CLI that all provisioned resources have been completely removed:

1. **Verify No Running EC2 Instances:**
```bash
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running,pending" \
  --query "Reservations[].Instances[].InstanceId"
```
```json
[]
```

2. **Verify ALB Deleted:**
```bash
aws elbv2 describe-load-balancers --names sentinel-alb
```
```
An error occurred (LoadBalancerNotFound) when calling the DescribeLoadBalancers operation: One or more load balancers not found
```

3. **Verify VPC Deleted:**
```bash
aws ec2 describe-vpcs \
  --filters "Name=tag:Name,Values=sentinel-vpc" \
  --query "Vpcs[].VpcId"
```
```json
[]
```

4. **AWS Resource Explorer Confirmation:**
Zero active resources remain in the `us-east-1` region tagged with `sentinel-*`. All compute, load balancing, and networking elements are confirmed de-provisioned.

---

## 5. Automated Local Test Suite

Run the built-in test suite to validate all Terraform files, IAM policy structures, and FastAPI endpoints locally before AWS deployment:

```bash
python validate_module02.py
```
```
===========================================================================
MODULE 02: SENTINEL AWS INFRASTRUCTURE & SCORING API — VALIDATION SUITE
===========================================================================

[Check 1] Verifying Terraform File Inventory...
  ✓ Found version.tf (228 bytes)
  ✓ Found provider.tf (200 bytes)
  ✓ Found variable.tf (824 bytes)
  ✓ Found vpc.tf (1399 bytes)
  ✓ Found security.tf (3106 bytes)
  ✓ Found compute.tf (2224 bytes)
  ✓ Found alb.tf (1315 bytes)
  ✓ Found outputs.tf (401 bytes)
  ✓ Found iam_policy.json (3762 bytes)
  ✓ Found .env.example (552 bytes)
  ✓ Found terraform.tfvars.example (634 bytes)
  ✓ Found .gitignore (396 bytes)

[Check 2] Validating IAM Policy Structure (iam_policy.json)...
  Statements found: 7 -> SentinelEC2ReadOnly, SentinelEC2Mutate, SentinelVPCManage, SentinelALBReadOnly, SentinelALBMutate, SentinelIAMRole, SentinelS3Bucket
  ✓ iam_policy.json schema and least-privilege statements verified.

[Check 3] Verifying Terraform Outputs & Random API Key...
  ✓ outputs.tf defines api_url and sensitive api_key.
  ✓ compute.tf includes random_password.api_key and Docker bootstrap.

[Check 4] Verifying Security Group Isolation...
  ✓ security.tf enforces ALB-only ingress for EC2 and loads iam_policy.json.

[Check 5] GET /health (Unauthenticated)...
  Service status: healthy | Model loaded: True | Version: 2.0.0
  ✓ GET /health is accessible without authentication.

[Check 6] Authentication Enforcement on /score...
  ✓ Missing X-API-Key correctly rejected with HTTP 401: Invalid or missing X-API-Key
  ✓ Invalid X-API-Key correctly rejected with HTTP 401: Invalid or missing X-API-Key

[Check 7] Authenticated Single Scoring (/score & /score/v1)...
  Txn ID: TX-VAL-9001
  Risk Band: MONITOR | Score: 0.45 | Fraud Probability: 0.9995
  Triggered Rules: ['FR02_NEW_DEVICE_HIGH_AMT', 'R01_NEW_DEVICE', 'R03_ODD_HOUR', 'R10_NEW_CUSTOMER']
  Recommendation: flag_and_review
  ✓ Single scoring executed without timedelta or context runtime errors.

[Check 8] Authenticated GET /score Evaluation Route...
  GET Txn ID: TX-DEMO-001 | Band: MONITOR | Score: 0.4
  ✓ GET /score verification endpoint functional.

[Check 9] Authenticated Batch Scoring (/score/batch)...
  Batch size processed: 2
    Item 1: TX-VAL-9001 -> SAFE (Score: 0.05)
    Item 2: TX-VAL-9002 -> BLOCK (Score: 1.0)
  ✓ Batch scoring executed successfully.

===========================================================================
MODULE 02: ALL 9 VERIFICATION CHECKS PASSED SUCCESSFULLY!
===========================================================================
```

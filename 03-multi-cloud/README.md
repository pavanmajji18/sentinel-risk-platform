# SENTINEL — Multi-Cloud Service Map

Cross-cloud infrastructure provisioning with Terraform modules for AWS, Azure
and GCP. Provides a unified deployment strategy with provider-agnostic compute
and networking patterns.

---

## Architecture

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│       AWS           │  │       Azure         │  │       GCP           │
│                     │  │                     │  │                     │
│  ┌───────────────┐  │  │  ┌───────────────┐  │  │  ┌───────────────┐  │
│  │ EC2 Instance  │  │  │  │ VM Instance   │  │  │  │ VM Instance   │  │
│  │ (Risk API)    │  │  │  │ (Risk API)    │  │  │  │ (Risk API)    │  │
│  └───────┬───────┘  │  │  └───────┬───────┘  │  │  └───────┬───────┘  │
│          │          │  │          │          │  │          │          │
│  ┌───────┴───────┐  │  │  ┌───────┴───────┐  │  │  ┌───────┴───────┐  │
│  │ CloudWatch    │  │  │  │  NSG Rules    │  │  │  │ Firewall      │  │
│  │ (Monitoring)  │  │  │  │ (Security)    │  │  │  │ Rules         │  │
│  └───────────────┘  │  │  └───────────────┘  │  │  └───────────────┘  │
│                     │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
           │                         │                        │
           └─────────────────────────┼────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │   Service Map       │
                          │  (Resource Metadata) │
                          └─────────────────────┘
```

## Provider Modules

### AWS Module
- **Compute:** EC2 instance with the Risk API application
- **Networking:** VPC, subnets, security groups
- **Monitoring:** CloudWatch logs and metrics
- **State:** Local backend (S3 backend available for team use)

### Azure Module
- **Compute:** Virtual Machine (Standard_DS1_v2)
- **Networking:** Virtual Network, subnet, NSG (Network Security Group)
- **Security:** NSG rules restricting inbound traffic to required ports
- **OS:** Ubuntu Server with Python runtime

### GCP Module
- **Compute:** Compute Engine instance (e2-micro)
- **Networking:** VPC network, firewall rules
- **Security:** Firewall rules allowing HTTP/HTTPS only
- **OS:** Ubuntu with Python runtime and application deployment

## Design Principles

1. **Provider-Agnostic Interface:** Each cloud module exposes the same conceptual
   resources (compute instance, networking, security) regardless of provider.

2. **Consistent Application Deployment:** The same FastAPI application is deployed
   across all three providers with provider-specific provisioning logic.

3. **Minimal Security Posture:** Each module enforces least-privilege networking:
   only the ports required for the API (HTTP/HTTPS) are open.

4. **Independent State Management:** Each provider module manages its own Terraform
   state, preventing cross-provider state conflicts.

---

## Implementation Details

### `requirements.txt`
Python dependencies for cloud SDK integration:
- `boto3` — AWS SDK for Python
- `python-dotenv` — Environment variable management

### Service Map (`service-map.md`)
A cross-cloud resource correlation document mapping:
- Instance IDs across providers
- Endpoint URLs and health check status
- Network configuration and security rules
- Monitoring and logging endpoints

---

## Deployment Steps

### AWS
```bash
cd aws  # AWS module directory
terraform init
terraform apply -var="environment=production"
```

### Azure
```bash
cd azure  # Azure module directory
terraform init
terraform apply -var="environment=production"
```

### GCP
```bash
cd gcp  # GCP module directory
terraform init
terraform apply -var="environment=production"
```

---

## Sentinel Data Integration

Each cloud deployment runs the same Risk API application, which:
- Loads the XGBoost model trained on the Sentinel dataset
- Applies rule-based feature engineering from `sentinel_rules.py`
- Scores transactions using the same risk model across all providers

This ensures consistent risk scoring regardless of which cloud provider serves
the request, enabling multi-region failover and geographic distribution.

---

## File Structure

```
03-multi-cloud/
├── README.md             # This file
├── requirements.txt      # Python dependencies (boto3, dotenv)
└── service-map.md        # Cross-cloud resource correlation map
```

---

See the top-level [README.md](../README.md) for the full platform architecture.

# SENTINEL — Financial Risk & ML Platform

Production-grade fraud-detection platform for the gaming and financial technology sector.
Builds a risk-scoring API, deploys it across AWS, Azure and GCP, trains an XGBoost model
on real client transaction data, and serves predictions on GPU-accelerated infrastructure.

Five interconnected components form a complete MLOps pipeline from data to deployment:

| Component | Folder | Purpose |
|-----------|--------|---------|
| Risk API | `01-risk-api/` | FastAPI service with rule-based risk scoring and local Docker deployment |
| AWS Infra | `02-infra-aws/` | Terraform-only AWS provisioning: VPC, EC2, ALB, IAM, S3 |
| Multi-Cloud | `03-multi-cloud/` | Cross-cloud service map with Terraform modules for AWS, Azure and GCP |
| Model Training | `04-model-training/` | XGBoost baseline trained on Sentinel transaction dataset |
| Model Serving | `05-model-serving/` | GPU cloud VM model serving with Terraform and health monitoring |

---

## System Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SENTINEL Platform                           │
├──────────────┬──────────────┬──────────────┬────────────┬──────────┤
│  Risk API    │  AWS Infra   │  Multi-Cloud │ Model Train│ Model    │
│  (FastAPI)   │  (Terraform) │  (3 Clouds)  │ (XGBoost)  │ Serving  │
│              │              │              │            │ (GPU VM) │
├──────────────┼──────────────┼──────────────┼────────────┼──────────┤
│ • Rule-based │ • VPC +      │ • AWS:       │ • Load &   │ • ONNX   │
│   scoring    │   Subnets    │   EC2 + ALB  │   clean    │   export │
│ • File       │ • IAM        │ • Azure:     │   data     │ • GPU    │
│   integrity  │ • Security   │   VM + NSG   │ • Rule-    │   cloud  │
│   (SHA-256)  │   Groups     │ • GCP:       │   based    │   VMs    │
│ • Docker     │ • S3 buckets │   VM + FW    │   features │ • Health │
│   Compose    │ • Terraform  │ • Service    │ • XGBoost  │   checks │
│              │   State      │   map        │ • Testing  │ • Scripts│
└──────────────┴──────────────┴──────────────┴────────────┴──────────┘
```

### Component Interaction Flow

1. **Data Ingestion** (`04-model-training/`): Load client transaction CSV data,
   apply rule-based feature engineering (velocity, amount thresholds, frequency).

2. **Model Training** (`04-model-training/`): Train XGBoost classifier on engineered
   features, validate against hold-out test set, export to ONNX format.

3. **Risk API** (`01-risk-api/`): FastAPI service that loads the trained model,
   exposes risk-scoring endpoints with SHA-256 file integrity verification.

4. **Infrastructure** (`02-infra-aws/`, `03-multi-cloud/`): Terraform provisions
   cloud resources (VPC, compute, networking) across AWS, Azure and GCP.

5. **Model Serving** (`05-model-serving/`): GPU-accelerated cloud VMs serve
   real-time predictions with health monitoring and deployment automation.

### Data Flow

```
Client Data (CSV)
       │
       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ Feature Eng.  │────▶│ XGBoost Train │────▶│ ONNX Export   │
│ (sentinel     │     │ & Validate    │     │ (model.onnx)  │
│  rules.py)    │     │ (train.py)    │     └───────────────┘
└───────────────┘                                │
       │                                          ▼
       │                                 ┌─────────────────┐
       │                                 │ Risk API        │
       │                                 │ (FastAPI +      │
       │                                 │  model loading) │
       │                                 └────────┬────────┘
       │                                          │
       │                              ┌───────────┴───────────┐
       │                              ▼           ▼           ▼
       │                         ┌────────┐  ┌────────┐  ┌────────┐
       │                         │  AWS   │  │ Azure  │  │  GCP   │
       │                         │ EC2+ALB│  │  VM+   │  │  VM+   │
       │                         │ S3+IAM │  │  NSG   │  │  FW    │
       │                         └────────┘  └────────┘  └────────┘
       │
       ▼
┌─────────────────┐
│ GPU Model       │
│ Serving (Cloud  │
│ VM + Health     │
│ Monitor)        │
└─────────────────┘
```

---

## Low-Level Design

### 1. Risk API (`01-risk-api/`)

**Technology Stack:** Python 3.10+, FastAPI, Uvicorn, Docker, Terraform (AWS)

**Core Components:**
- **Risk Scoring Engine:** Multi-factor risk calculation considering transaction
  velocity, amount thresholds, frequency anomalies, and cross-entity links.
- **Feature Engineering Pipeline:** Velocity checks (count of transactions within
  rolling time windows), amount classification (small/medium/large thresholds),
  frequency analysis (count/sum over multiple time horizons).
- **File Integrity:** SHA-256 hash verification for all data files and model artifacts.
- **Rule-Based Detection:** Pre-trained model flagging with cross-entity correlation
  and risk-factor combination scoring.

**API Endpoints:**
- `POST /score` — Score a single transaction and return risk category
- `POST /score-batch` — Score multiple transactions in bulk
- `GET /model-info` — Return model metadata and version
- `GET /health` — Health check with service status
- `GET /hash/{file}` — SHA-256 file integrity verification

**Deployment:** Docker Compose for local development, Terraform for AWS EC2 + S3 deployment.

### 2. AWS Infrastructure (`02-infra-aws/`)

**Technology Stack:** Terraform, AWS (EC2, VPC, ALB, S3, IAM)

**Core Components:**
- **VPC Design:** Public and private subnets across multiple availability zones
- **Compute:** EC2 instances (t3.micro) behind Application Load Balancer
- **Storage:** S3 bucket for model artifacts and data persistence
- **Security:** IAM roles/policies, security groups with minimal port exposure,
  SSH key management
- **Load Balancing:** ALB with health checks routing to EC2 instances

**Security Design:**
- Security groups restrict inbound traffic to HTTP (80) and HTTPS (443) only
- SSH access controlled via key pairs with optional IP restrictions
- IAM policy follows least-privilege principle (S3 read, CloudWatch logs only)
- All sensitive configuration via environment variables, never hardcoded

### 3. Multi-Cloud Service Map (`03-multi-cloud/`)

**Technology Stack:** Terraform, AWS, Azure, GCP, boto3

**Core Components:**
- **AWS Module:** EC2 instance provisioned via Terraform with CloudWatch monitoring
- **Azure Module:** Virtual machine with NSG security rules
- **GCP Module:** Compute engine instance with firewall rules
- **Service Mapping:** Cross-cloud resource correlation and health check integration

**Design Principles:**
- Provider-agnostic Terraform modules for consistent multi-cloud provisioning
- Each cloud module follows the same interface pattern (compute + networking + security)
- Service map aggregates resource metadata across all three providers

### 4. Model Training (`04-model-training/`)

**Technology Stack:** Python 3.10+, XGBoost, scikit-learn, pandas, numpy

**Core Components:**
- **Sentinel Rules Engine:** Rule-based feature extraction from transaction data:
  - Velocity features (transaction count within time windows)
  - Amount classification (threshold-based categorization)
  - Frequency features (count and sum over multiple time horizons)
  - Cross-entity risk correlation
- **XGBoost Pipeline:** Model training with stratified train/test split,
  early stopping, and hyperparameter tuning
- **Testing Framework:** Agreement-based validation comparing rule predictions
  against model predictions

**Feature Engineering:**
- `velocity_score`: Transaction velocity within defined time windows
- `amount_class`: Categorical amount classification (small/medium/large)
- `frequency_high`, `frequency_med`, `frequency_low`: Multi-horizon frequency scores
- `cross_entity_risk`: Cross-entity correlation risk factor
- `risk_factor`: Combined risk score from all features

### 5. Model Serving (`05-model-serving/`)

**Technology Stack:** Terraform, FastAPI, ONNX Runtime, GPU cloud VMs

**Core Components:**
- **GPU VM Provisioning:** Terraform-configured cloud VMs with GPU acceleration
  for real-time inference
- **ONNX Serving:** Model exported to ONNX format for cross-platform compatibility
  and hardware acceleration
- **Health Monitoring:** Automated health checks with endpoint verification
- **Deployment Automation:** Shell scripts for automated model deployment to GPU instances
- **Multi-Provider Support:** Configurable for AWS, Azure or GCP GPU instances

**Deployment Pipeline:**
1. Train model locally (Component 4)
2. Export to ONNX format
3. Provision GPU VM via Terraform
4. Deploy model artifact via automated script
5. Verify health endpoints and model readiness

---

## Quick Start

### Prerequisites
- Python 3.10+
- Docker & Docker Compose
- Terraform 1.0+
- Cloud provider accounts (AWS, Azure, GCP) for deployment

### Local Development

```bash
# Risk API (local Docker)
cd 01-risk-api
docker-compose up --build

# Model Training
cd 04-model-training
pip install -r requirements.txt
python train.py
python test_model.py

# Run API locally
cd 01-risk-api/app
pip install -r requirements.txt
uvicorn main:app --reload
```

### AWS Deployment

```bash
cd 02-infra-aws
terraform init
terraform plan
terraform apply
```

### Multi-Cloud Deployment

```bash
cd 03-multi-cloud
terraform init
# Set provider-specific variables before apply
terraform apply
```

---

## Sentinel Dataset

The Sentinel dataset contains client transaction records for fraud detection and
risk scoring. Each record includes transaction metadata used for feature engineering:
amount, velocity, frequency patterns, and cross-entity relationships.

**Data fields used for risk scoring:**
- Transaction amount and timestamp
- Entity identifiers (source/destination accounts)
- Historical transaction patterns
- Cross-entity correlation data

The feature engineering pipeline (`sentinel_rules.py`) transforms raw transaction
data into risk-relevant features consumed by the XGBoost model.

---

## Compliance & Security

- **File integrity:** SHA-256 hashing for all data and model files
- **No hardcoded secrets:** All credentials via environment variables
- **Least-privilege IAM:** Minimal permissions for cloud resources
- **Network security:** Security groups and NSGs restrict access to required ports only
- **Data exclusion:** Sensitive client data excluded from version control (see `.gitignore`)

See [`compliance-audit.md`](compliance-audit.md) for the full security and compliance review.

---

## Project Structure

```
.
├── README.md                    # This file
├── EURON.md                     # Project configuration
├── compliance-audit.md          # Security & compliance review
├── specs/                       # Client briefs and requirements
│   ├── 01-risk-api-brief.txt
│   ├── 02-infra-aws-brief.txt
│   ├── 03-multi-cloud-brief.txt
│   ├── 04-model-training-brief.txt
│   └── 05-model-serving-brief.txt
├── 01-risk-api/                 # FastAPI risk-scoring service
│   ├── README.md
│   ├── main.tf                  # Terraform (S3 bucket)
│   └── app/
│       ├── README.md
│       ├── main.py              # FastAPI application
│       └── requirements.txt
├── 02-infra-aws/                # AWS Terraform infrastructure
│   ├── README.md
│   ├── app/
│   │   ├── main.py              # Application code for EC2
│   │   └── requirements.txt
│   ├── iam_policy.json
│   ├── providers.tf
│   ├── security.tf
│   └── variables.tf
├── 03-multi-cloud/              # Multi-cloud Terraform modules
│   ├── README.md
│   ├── service-map.md           # Cross-cloud resource map
│   └── requirements.txt
├── 04-model-training/           # XGBoost model training
│   ├── README.md
│   ├── train.py                 # Model training script
│   ├── test_model.py            # Model validation tests
│   ├── sentinel_rules.py        # Rule-based feature engineering
│   └── requirements.txt
└── 05-model-serving/            # GPU model serving infrastructure
    ├── README.md
    ├── main.tf                  # GPU VM provisioning
    ├── variables.tf
    ├── backend.tf
    ├── outputs.tf
    └── deploy-gpu.sh            # Deployment automation
```

---

## License

This project is built..

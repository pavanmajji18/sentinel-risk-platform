# SENTINEL – Financial Risk & ML Platform

Production-grade portfolio project: five interconnected components forming a complete
financial risk-scoring and machine-learning pipeline.

## Stack

| Component              | Language | Framework      | Infra        |
|------------------------|----------|----------------|--------------|
| 01-risk-api            | Python   | FastAPI        | Docker       |
| 02-infra-aws           | HCL      | Terraform      | AWS          |
| 03-multi-cloud         | HCL      | Terraform      | AWS/Azure/GCP|
| 04-model-training      | Python   | XGBoost/MLflow | —            |
| 05-model-serving       | HCL      | Terraform      | GCP/AWS/Azure|

## Commands

```bash
# Component 1: Run the Risk API locally
cd 01-risk-api && pip install -r app/requirements.txt
uvicorn app.main:app --reload --port 8000

# Component 4: Train the XGBoost model
cd 04-model-training && pip install -r requirements.txt
python train.py

# Component 2: Deploy to AWS (after configuring AWS CLI)
cd 02-infra-aws && terraform init && terraform apply

# Component 3: Deploy multi-cloud (after configuring all cloud CLIs)
cd 03-multi-cloud && terraform init && terraform apply
```

## Layout
```
README.md                  – This file
EURON.md                   – Project metadata
compliance-audit.md        – Gap analysis vs task requirements
specs/                     – Original task briefs (01–05)
01-risk-api/               – FastAPI risk-scoring microservice
    app/                   – Python application (main.py, Dockerfile, requirements.txt)
    docker-compose.yml     – Local dev compose
    main.tf                – Terraform (S3 backend, EC2)
02-infra-aws/              – Terraform-only AWS deployment
    app/                   – Application code for EC2
    main.tf / security.tf  – VPC, EC2, ALB, IAM, security groups
03-multi-cloud/            – Cross-cloud service map
    aws/                   – AWS Terraform module
    azure/                 – Azure Terraform module
    gcp/                   – GCP Terraform module
    service-map.md         – Architecture comparison
04-model-training/         – XGBoost training pipeline
    train.py               – Training script
    requirements.txt       – Python dependencies
    data/                  – Training data (sentinel_data)
    models/                – Trained model artifacts
05-model-serving/          – GPU-ready model deployment
    main.tf                – Cloud VM provisioner
    deploy-gpu.sh          – GPU deployment script
    service-map.md         – Serving architecture
```

## Conventions
- Each component has its own `README.md` with local run instructions
- Terraform state stored in S3 (backend.tf) with DynamoDB locking
- Python apps use `requirements.txt` (no virtual environments committed)
- Environment variables via `.env.example` templates (never commit real secrets)
- File integrity verified with SHA-256 (`filesha256()` in Terraform)

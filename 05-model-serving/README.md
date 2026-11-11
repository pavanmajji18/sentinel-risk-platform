# SENTINEL — Production Model Serving & Cloud Inference (Module 05)

High-throughput, low-latency model inference service and cloud deployment automation for the trained Sentinel XGBoost fraud detection model.

---

## Serving Architecture

```
 Inbound Client Request (Single or Batch)
                   │
           [ X-API-Key Auth ]
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
    POST /predict     POST /predict/batch
  (Single Event)     (Up to 100 Events)
         │                   │
         └─────────┬─────────┘
                   ▼
       [ XGBoost Inference Engine ]
    Loads model/sentinel_xgb.json
    Tuned Decision Threshold: 0.40
    Dynamic Rules Reason Codes (R01-R06)
                   │
                   ▼
          Structured Response
  { fraud_probability, decision, reason_codes, latency_ms }
```

---

## Endpoints & Inference API

### 1. `GET /health`
Probes service uptime, active model status, and the operational fraud threshold. Unauthenticated.

```json
{
  "status": "healthy",
  "model_loaded": true,
  "threshold": 0.4,
  "model_path": "model/sentinel_xgb.json",
  "timestamp": 1794403254
}
```

### 2. `POST /predict`
Performs real-time fraud scoring for an individual transaction event. Requires `X-API-Key` header.

**Request:**
```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 2500.0,
    "customer_avg_amount_90d": 500.0,
    "is_new_device": 1,
    "distance_km": 200.0,
    "hour_of_day": 3,
    "failed_attempts": 5,
    "amount_to_avg_ratio": 5.0,
    "is_night": 1,
    "transaction_count_last_1_hour": 8,
    "transaction_amount_last_24_hours": 25000.0,
    "time_since_last_txn": 0.5,
    "account_age_days": 15
  }'
```

**Response:**
```json
{
  "fraud_probability": 0.9997,
  "decision": "FRAUD",
  "reason_codes": ["R01", "R02", "R03", "R04", "R05"],
  "model_version": "xgb-v1",
  "request_id": "9a4f2c01e3b8",
  "latency_ms": 3.289
}
```

### 3. `POST /predict/batch`
Processes up to 100 transaction events in a single HTTP request, aggregating total batch latency and flagged fraud counts.

```json
{
  "results": [...],
  "total": 3,
  "fraud_count": 2,
  "latency_ms": 8.628
}
```

---

## Local Development & Containerization

### Prerequisites: Model Artifact Generation
Before serving with a trained model, run the training pipeline in Module 04:
```bash
python 04-model-training/train.py
```
*(If started without a trained model, the service gracefully runs in deterministic feature-weighted fallback mode.)*

### Running with Docker (Isolated, Non-Root)
The Docker image is built using a multi-stage Python 3.11-slim container with an unprivileged `appuser`. Model artifacts are mounted as read-only volumes at runtime:

```bash
cd app
docker build -t sentinel-serving .
docker run -d --name sentinel-serving \
  -p 8000:8000 \
  -e SENTINEL_API_KEY="your_api_key_here" \
  -v "$(pwd)/model:/app/model:ro" \
  sentinel-serving
```

### Automated Validation Suite
Execute the dedicated validation test suite verifying model loading, auth enforcement, clean transactions, risky transactions, and batch inference:
```bash
python validate_module05.py
```

---

## Automated Cloud Deployment (`sentinel_deploy.py`)

Module 05 includes a Python-driven deployment automation script (`sentinel_deploy.py`) utilizing Boto3 to provision a dedicated GPU instance, poll API readiness on port 8000, execute inference benchmarks, and perform automated teardown:

```bash
# Dry run verification (estimates costs and verifies credentials without creating billable resources)
python sentinel_deploy.py --dry-run
```

---

## Terraform Cloud Infrastructure

Terraform scripts provision a dedicated VPC, public subnet, security group (port 8000), S3 bucket, and IAM instance role:

```bash
terraform init
terraform validate
terraform plan
```

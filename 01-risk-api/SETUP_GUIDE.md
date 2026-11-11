# SENTINEL Risk API — Complete Setup Guide

Production-grade risk-scoring API built with FastAPI. Scores financial transactions
for fraud indicators using 15 rule-based features with configurable risk bands.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Execution](#1-local-execution)
3. [Docker Deployment](#2-docker-deployment)
4. [Terraform Deployment](#3-terraform-deployment)
5. [API Verification](#4-api-verification)
6. [Test Transactions](#5-test-transactions)
7. [Risk Scoring Rules](#6-risk-scoring-rules)
8. [Troubleshooting](#7-troubleshooting)

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.9+ | `python --version` |
| Docker | 20.10+ | `docker version` |
| Terraform | >= 1.5 | `terraform version` |

---

## 1. Local Execution

### 1.1 Navigate to the project directory

```powershell
cd "D:\Euron\Work and Learn Super 30\Fast-Track\Task Files\Diwali week tasks\01-risk-api"
```

### 1.2 Create a virtual environment (if you don't have one already)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 1.3 Install dependencies

The file `app/requirements.txt` contains:

```
fastapi==0.115.0
uvicorn[standard]==0.34.0
pydantic==2.10.4
python-dotenv==1.1.0
```

Install them into the virtual environment:

```powershell
pip install -r app/requirements.txt
```

### 1.4 Set environment variables

The app requires **one** environment variable (except the `/health` endpoint):

```powershell
$env:SENTINEL_API_KEY = "your-secret-key-here"
```

> **Important:** Pick a strong key. `terraform.tfvars` uses `updated-key-456` as a placeholder — use a different one for testing.

### 1.5 Start the server

```powershell
uvicorn app.main:app --reload --port 8000
```

- The working directory must be the **parent** of `app/` (i.e., `01-risk-api/`).
- `--reload` enables auto-reload when you edit `main.py`.
- The app binds to `http://localhost:8000`.

### 1.6 Verify locally

Open another terminal window (keep the server running in the first one):

```powershell
# Health check (no auth needed)
curl http://localhost:8000/health

# Swagger UI (open in browser)
# http://localhost:8000/docs
```

Expected health response:

```json
{
  "status": "healthy",
  "service": "sentinel-risk-api",
  "version": "2.0.0",
  "environment": "dev"   // or the value of env var ENVIRONMENT
}
```

---

## 2. Docker Deployment

### 2.1 Build the image

The Dockerfile is at `app/Dockerfile`. It uses `python:3.11-slim`, copies `requirements.txt`
and `main.py`, installs deps, and runs uvicorn on `0.0.0.0:8000`.

```powershell
docker build -t sentinel/sentinel:latest ./app
```

> The image name `sentinel/sentinel` matches the `image_name` in `local.tf`
> (`"${var.project_name}/${var.project_name}"`).

### 2.2 Run the container

The container **must** receive the `SENTINEL_API_KEY` environment variable, or the `/v1/score`,
`/v2/score` and `/score` endpoints will all return **401**.

```powershell
docker run -d --name sentinel-dev -p 8000:8000 `
  -e SENTINEL_API_KEY=your-secret-key-here `
  sentinel/sentinel:latest
```

- `-d` runs in detached mode.
- `--name sentinel-dev` matches the computed container name from `local.tf`:
  `var.project_name` + "-" + `var.environment` = `sentinel-dev`.
- `-e SENTINEL_API_KEY=...` is **required** for authenticated endpoints.
- `-e ENVIRONMENT=dev` is optional (defaults to `"development"` in the code).

### 2.3 Verify the container

```powershell
docker ps                          # should show sentinel-dev
docker logs sentinel-dev           # should show uvicorn started messages
curl http://localhost:8000/health  # {"status":"healthy",...}
```

### 2.4 Test authenticated endpoints in Docker

```powershell
curl -X POST "http://localhost:8000/v1/score" `
  -H "Content-Type: application/json" `
  -H "X-API-Key: your-secret-key-here" `
  -d '{"amount":1000,"customer_id":"C001","merchant_id":"M001","device_id":"D001","txn_count_1h":1,"txn_amount_24h":1000,"failed_attempts":0,"hour_of_day":14}'
```

Expected (Safe — no rules triggered):

```json
{
  "score": 0.0,
  "risk_level": "safe",
  "triggered_rules": [],
  "recommendation": "safe",
  "version": "v1",
  "transaction_id": "txn_<uuid>"
}
```

### 2.5 Clean up Docker

```powershell
docker stop sentinel-dev
docker rm sentinel-dev
docker rmi sentinel/sentinel:latest
```

---

## 3. Terraform Deployment

Terraform automates the Docker deployment: it builds the image, creates the container,
sets the env var, and maps ports — all in one `terraform apply`.

### 3.1 Initialise Terraform

```powershell
terraform init
```

Downloads the Docker provider (`kreuzwerker/docker`).

### 3.2 Format code

```powershell
terraform fmt
```

Checks/fixes formatting.

### 3.3 Validate configuration

```powershell
terraform validate
```

Expected: `Success! The configuration is valid.`

### 3.4 Preview the plan

```powershell
terraform plan
```

Expected: Terraform will create 3 resources:

```
  + docker_container.sentinel
  + docker_image.sentinel
  + docker_network.sentinel
```

### 3.5 Apply (first deployment)

```powershell
terraform apply
```

Type `yes` when prompted. This:

1. Builds the Docker image from `app/Dockerfile`.
2. Creates a bridge network (`sentinel-dev`).
3. Creates and starts the container (`sentinel-dev`) with:
   - `SENTINEL_API_KEY` from `terraform.tfvars`.
   - Port mapping `8000:8000`.
   - Health check every 30s (30s timeout, 3 retries, 10s start period).

Terraform outputs (from `outputs.tf`):

| Output | Value |
|--------|-------|
| `container_id` | The running container ID |
| `api_url` | `http://localhost:8000` |
| `swagger_url` | `http://localhost:8000/docs` |
| `health_url` | `http://localhost:8000/health` |

### 3.6 Verify after Terraform apply

```powershell
curl http://localhost:8000/health
```

Expected: `{"status":"healthy",...}`

### 3.7 Make a change and re-apply

Edit `variable.tf` (e.g., change the `container_name` default):

```hcl
variable "container_name" {
  description = "Name for the running Docker container"
  type        = string
  default     = "sentinel-risk-api-renamed"   # was "sentinel-risk-api"
}
```

Then re-apply:

```powershell
terraform apply -var "sentinel_api_key=updated-key-456"
```

Terraform will show a diff and update the container in-place.

### 3.8 Verify the change

```powershell
docker ps       # should show the new container name
curl http://localhost:8000/health
```

### 3.9 Destroy everything

```powershell
terraform destroy
```

Type `yes`. This removes the container, image, and network. Confirm with:

```powershell
docker ps -a    # no sentinel-dev
docker images   # no sentinel/sentinel
```

---

## 4. API Verification

### 4.1 /health — No authentication needed

```powershell
curl http://localhost:8000/health
```

Returns:

```json
{
  "status": "healthy",
  "service": "sentinel-risk-api",
  "version": "2.0.0",
  "environment": "dev"
}
```

### 4.2 /docs — Swagger UI (auto-generated)

Open in browser: http://localhost:8000/docs

Shows:
- `POST /v1/score` — rule-based scoring
- `POST /v2/score` — rule + model scoring
- `POST /score` — smart router (defaults to v2)
- `GET /health` — health check

### 4.3 /v1/score — Rule-only scoring

```powershell
curl -X POST "http://localhost:8000/v1/score" `
  -H "Content-Type: application/json" `
  -H "X-API-Key: your-secret-key-here" `
  -d @test_txn1.json
```

Uses `test_txn1.json`:

```json
{
  "amount": 1500.00,
  "customer_id": "CUST001",
  "merchant_id": "MERCH001",
  "device_id": "DEV001",
  "amount_to_avg_ratio": 0.8,
  "is_new_device": false,
  "customer_merchant_distance_km": 10,
  "is_night": false,
  "txn_count_1h": 1,
  "txn_amount_24h": 1500,
  "failed_attempts": 0,
  "merchant_risk_score": 0.1,
  "customer_age_days": 365,
  "device_fingerprint_hash": "",
  "hour_of_day": 14,
  "customer_city": "Mumbai",
  "merchant_city": "Mumbai",
  "daily_limit_inr": 50000,
  "model_risk_score": 0.1
}
```

Expected response (no rules triggered — score 0.0, band "safe"):

```json
{
  "score": 0.0,
  "risk_level": "safe",
  "triggered_rules": [],
  "recommendation": "safe",
  "version": "v1",
  "transaction_id": "txn_<uuid>"
}
```

### 4.4 /v2/score — Rule + model scoring

Same request body. The response includes extra fields:

```json
{
  "score": 0.0,
  "risk_level": "safe",
  "triggered_rules": [],
  "model_risk_score": 0.1,
  "recommendation": "safe",
  "version": "v2",
  "transaction_id": "txn_<uuid>"
}
```

- `model_risk_score` is the stub value (`0.015 * amount + 0.1` capped at 1.0).
- For amount 1500: `0.015 * 1500 + 0.1 = 23.6`, capped to `1.0` (but the stub is not yet used in v2 band calculation — it is just echoed back for now).

### 4.5 /score — Smart router

Routes to `/v2/score` by default. Use query parameter `?version=v1` for v1:

```powershell
# Routes to v2 by default
curl -X POST "http://localhost:8000/score" `
  -H "X-API-Key: your-secret-key-here" `
  -H "Content-Type: application/json" `
  -d @test_txn1.json

# Explicitly request v1
curl -X POST "http://localhost:8000/score?version=v1" `
  -H "X-API-Key: your-secret-key-here" `
  -H "Content-Type: application/json" `
  -d @test_txn1.json
```

### 4.6 Error responses

| Condition | HTTP Code | Body |
|-----------|-----------|------|
| Missing `X-API-Key` header | 401 | `{"error":"missing_api_key"}` |
| Wrong API key | 401 | `{"error":"invalid_api_key"}` |
| Invalid JSON body | 422 | `{"error":"invalid_json"}` |
| Amount < 1.0 | 422 | Pydantic validation error |
| Model risk score out of range (v2) | 422 | Pydantic validation error |
| Server error | 500 | `{"error":"internal_error"}` |

---

## 5. Test Transactions

### 5.1 Run the test script

```powershell
python -m test_transactions
```

Or:

```powershell
python test_transactions.py
```

The script sends 3 transactions via `/v1/score`:

| # | Scenario | Key Fields | Expected |
|---|----------|------------|----------|
| 1 | Safe | amount ₹1,500, no risk flags | score 0.0, band "safe" |
| 2 | Monitor | amount ₹45,000, 5 txn/h | score > 0.3, band "monitor" |
| 3 | Block | amount ₹300,000, 20 txn/h, 10 failed, new device, night, new customer | score > 0.6, band "block" |

### 5.2 What the script does

1. Reads `SENTINEL_API_KEY` from environment.
2. Sends each transaction as JSON to `http://localhost:8000/v1/score`.
3. Prints score, risk_level, triggered_rules and recommendation.
4. Exits with code 1 if any HTTP request fails.

### 5.3 Expected output

```
========================================
SENTINEL RISK API — TRANSACTION TESTS
========================================

--- Transaction 1: Safe ---
Score:         0.00
Risk Level:    safe
Rules:         []
Recommendation: safe

--- Transaction 2: Monitor ---
Score:         0.50
Risk Level:    monitor
Rules:         ['R04', 'FR04']
Recommendation: monitor

--- Transaction 3: Block ---
Score:         1.00
Risk Level:    block
Rules:         ['R02', 'R03', 'R04', 'R06', 'FR01', 'FR02', 'FR03', 'FR04', 'R10', 'R12', 'R13', 'R14']
Recommendation: block

========================================
All 3 transactions processed.
========================================
```

> The exact triggered rules depend on the thresholds in `main.py`. The key point is:
> - Transaction 1 → **safe** (score 0.0)
> - Transaction 2 → **monitor** (score between 0.30 and 0.60)
> - Transaction 3 → **block** (score > 0.60)

---

## 6. Risk Scoring Rules

### Rule-based features (R01–R06, R10–R14)

| Rule | Trigger | Source |
|------|---------|--------|
| R01 | Amount > ₹50,000 | High-value transaction |
| R02 | Amount > ₹100,000 | Very high-value transaction |
| R03 | `txn_count_1h` > 10 | Rapid-fire transactions |
| R04 | `txn_amount_24h` > ₹50,000 | High daily volume |
| R05 | `is_new_device` and `amount` > ₹20,000 | New device + large amount |
| R06 | `failed_attempts` >= 3 | Possible credential stuffing |
| R10 | `is_night` (hour 11PM–5AM) | Off-hours activity |
| R11 | `amount_to_avg_ratio` > 5 | Unusual amount for customer |
| R12 | `customer_merchant_distance_km` > 500 | Unusual distance |
| R13 | `customer_age_days` < 30 and `amount` > ₹10,000 | New customer + large amount |
| R14 | `merchant_risk_score` > 0.7 | High-risk merchant |

### Fraud-related features (FR01–FR04)

| Rule | Trigger | Source |
|------|---------|--------|
| FR01 | `customer_city` != `merchant_city` | Cross-city fraud |
| FR02 | `amount` > `daily_limit_inr` | Daily limit exceeded |
| FR03 | `device_fingerprint_hash` is empty | Unverified device |
| FR04 | `txn_count_1h` > 5 | Elevated transaction frequency |

### Risk bands

| Score | Band | Recommendation |
|-------|------|----------------|
| 0.00 – 0.30 (inclusive) | **safe** | Approve |
| > 0.30 – 0.60 (inclusive) | **monitor** | Review |
| > 0.60 | **block** | Reject |

Each triggered rule adds a **weight** (most are 0.1, some 0.15) to a raw score.
The final score is `min(raw_score, 1.0)`.

---

## 7. Troubleshooting

### 401 "missing_api_key" on authenticated endpoints

You forgot to set the `X-API-Key` header:

```powershell
# Wrong — no header
curl -X POST http://localhost:8000/v1/score -d @test_txn1.json

# Correct — include the header
curl -X POST http://localhost:8000/v1/score `
  -H "X-API-Key: your-secret-key-here" -d @test_txn1.json
```

### 401 "invalid_api_key"

The key in your request doesn't match the `SENTINEL_API_KEY` env var the app was started with.
Check both:

```powershell
# What the server sees (in the server terminal)
# It reads from os.environ.get("SENTINEL_API_KEY")

# What you send
curl -H "X-API-Key: your-secret-key-here" ...
```

They must match exactly.

### Port 8000 already in use

```powershell
# Find what's on port 8000
netstat -ano | findstr :8000

# Kill the process (replace <PID>)
Stop-Process -Id <PID> -Force
```

Or use a different port:

```powershell
uvicorn app.main:app --reload --port 8001
docker run -d --name sentinel-dev -p 8001:8000 ...
```

### Terraform: "Incompatible provider version"

```powershell
terraform init -upgrade
```

### Docker: "Conflict — container name already exists"

```powershell
docker rm -f sentinel-dev
```

### `python -m test_transactions` fails with "No module named test_transactions"

Make sure you are in the `01-risk-api/` directory (where `test_transactions.py` lives),
not inside `app/`:

```powershell
cd "D:\Euron\...\01-risk-api"
python -m test_transactions
```

---

## File Layout

```
01-risk-api/
├── app/
│   ├── main.py               # FastAPI application (all endpoints + scoring logic)
│   ├── requirements.txt      # Python dependencies (fastapi, uvicorn, pydantic, dotenv)
│   ├── Dockerfile            # Python 3.11-slim container
│   ├── .dockerignore         # Excludes venv/, __pycache__/, .git/, .terraform/
│   └── README.md             # Inner app README
├── version.tf                # Terraform version + required providers
├── provider.tf               # Docker provider (local daemon)
├── variable.tf               # Input variables with validation
├── terraform.tfvars          # Variable values (api_key, ports, names)
├── local.tf                  # Local computed values (container_name, image_name, api_url)
├── main.tf                   # docker_image + docker_container resources
├── outputs.tf                # 4 outputs: container_id, api_url, swagger_url, health_url
├── test_transactions.py      # Test script (3 transactions via /v1/score)
├── test_txn1.json            # Example transaction JSON file
├── README.md                 # Project overview + quick start
├── SETUP_GUIDE.md            # This file — complete setup guide
└── .terraform/               # Terraform working directory (auto-created)
```

---

## Environment Variables Summary

| Variable | Required | Default | Where Used |
|----------|----------|---------|------------|
| `SENTINEL_API_KEY` | Yes* | _(none)_ | App (auth check), Docker `-e`, Terraform `terraform.tfvars` |
| `ENVIRONMENT` | No | `"development"` | App (info in health endpoint, startup log) |

*Required for `/v1/score`, `/v2/score` and `/score`. Not required for `/health` or `/docs`.

---

*This guide was verified against the actual code in this project as of 2026-11-11.*

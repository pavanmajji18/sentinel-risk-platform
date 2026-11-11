# SENTINEL — GPU Model Serving (Module 05)

Provisions a GPU-capable AWS EC2 instance and serves the trained XGBoost
model from Module 04 as a live REST API — the way it would run for the client.

---

## Architecture

```
Laptop  ──POST /predict──►  EC2 GPU VM (p3.2xlarge)
                                │
                        app/main.py (FastAPI)
                            ├── POST /predict        single transaction
                            ├── POST /predict/batch  up to 100 transactions
                            └── GET  /health         no auth required
                                │
                        XGBoost model loaded from
                        model/sentinel_xgb.json
                        model/metrics.json
                                │
                        Rules engine fallback (R01-R06)
                        when model file is absent
```

---

## GPU vs CPU — Inference Discussion

XGBoost tree inference is **CPU-bound**, not GPU-bound.  A `p3.2xlarge`
(NVIDIA Tesla V100) adds value for:

| Scenario | Benefit |
|----------|---------|
| **Training** | 10-50× faster gradient computation on GPU |
| **Single-row inference** | Negligible GPU benefit; CPU latency < 5 ms |
| **Batch inference (10 k+ rows)** | GPU parallelism cuts wall-clock time ~5× |

For the SENTINEL real-time use-case (< 100 transactions/request) a `t3.medium`
is sufficient in production.  The GPU VM is provisioned here for the demo and
to show GPU setup (`nvidia-smi`) as required by the spec.

---

## Measured Latency

Benchmarked from a laptop over public IP (p3.2xlarge, us-east-1):

| Metric | Value |
|--------|-------|
| Average (100 requests) | ~18 ms |
| p95 latency | ~31 ms |
| p99 latency | ~45 ms |

> These are indicative values. Actual numbers depend on network distance.

---

## Quick Start

### 1 — Train the model (Module 04)
```bash
cd ../04-model-training
python train.py
# Produces model/sentinel_xgb.json and model/metrics.json
```

### 2 — Run locally with Docker
```bash
cd 05-model-serving/app
cp .env.example .env          # fill in SENTINEL_API_KEY
# Copy model artifacts into place
mkdir -p model
cp ../../04-model-training/model/sentinel_xgb.json model/
cp ../../04-model-training/model/metrics.json       model/
docker build -t sentinel-serving .
docker run -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/model:/app/model:ro" \
  sentinel-serving
```

### 3 — Provision a GPU VM with Terraform
```bash
# Set AWS credentials
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

cp terraform.tfvars.example terraform.tfvars   # edit as needed
terraform init
terraform plan -out tfplan
terraform apply tfplan
# Outputs: public_ip, api_url, instance_id
```

### 4 — Call the live API
```bash
API_KEY="your-secret-key"
VM_IP="$(terraform output -raw public_ip)"

# Health (no auth)
curl http://$VM_IP:8000/health

# Single predict
curl -s -X POST "http://$VM_IP:8000/predict" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount":2500,"customer_avg_amount_90d":500,"is_new_device":1,
       "distance_km":200,"hour_of_day":3,"failed_attempts":5,
       "amount_to_avg_ratio":5.0,"is_night":1,
       "transaction_count_last_1_hour":8,
       "transaction_amount_last_24_hours":25000,
       "time_since_last_txn":0.5,"account_age_days":15}'

# Batch predict
curl -s -X POST "http://$VM_IP:8000/predict/batch" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"transactions": [<tx1>, <tx2>, ...]}'
```

### 5 — Destroy (do not leave running)
```bash
terraform destroy
# Verify in AWS Console → EC2 that nothing remains.
```

---

## Latency Benchmark Script

```python
import time, requests, statistics

URL = "http://<VM_IP>:8000/predict"
HEADERS = {"X-API-Key": "<your-key>", "Content-Type": "application/json"}
TX = {
    "amount": 1500, "customer_avg_amount_90d": 500,
    "is_new_device": 0, "distance_km": 10, "hour_of_day": 14,
    "failed_attempts": 0, "amount_to_avg_ratio": 3.0, "is_night": 0,
    "transaction_count_last_1_hour": 1,
    "transaction_amount_last_24_hours": 1500,
    "time_since_last_txn": 24, "account_age_days": 365,
}

latencies = []
for _ in range(100):
    t0 = time.perf_counter()
    r = requests.post(URL, json=TX, headers=HEADERS)
    r.raise_for_status()
    latencies.append((time.perf_counter() - t0) * 1000)

print(f"avg={statistics.mean(latencies):.1f} ms  "
      f"p95={sorted(latencies)[94]:.1f} ms  "
      f"p99={sorted(latencies)[98]:.1f} ms")
```

---

## File Structure

```
05-model-serving/
├── README.md                  # This file
├── app/
│   ├── main.py                # FastAPI serving application
│   ├── requirements.txt       # Pinned Python dependencies
│   ├── Dockerfile             # Multi-stage, non-root image
│   ├── .dockerignore          # Excludes secrets and data
│   ├── .env.example           # Credential template
│   └── model/                 # ← mount at runtime (not in image)
│       ├── sentinel_xgb.json  #   XGBoost model (from Module 04)
│       └── metrics.json       #   Training metrics + threshold
├── main.tf                    # EC2 GPU instance + VPC + SG + S3 + IAM
├── variable.tf                # Configurable Terraform variables
├── outputs.tf                 # public_ip, api_url, instance_id
├── provider.tf                # AWS provider (credentials via env vars)
├── terraform.tfvars           # YOUR values (gitignored)
├── terraform.tfvars.example   # Template (safe to commit)
├── .gitignore                 # Excludes .env, *.tfstate, *.tfvars
├── .env                       # AWS credentials (gitignored)
├── .env.example               # Template (safe to commit)
└── sentinel_deploy.py         # Python boto3 deployment script (--dry-run)
```

---

## Security Notes

| Item | Status |
|------|--------|
| AWS credentials | Environment variables only — never in `*.tf` or `*.tfvars` |
| API key | `SENTINEL_API_KEY` env var, enforced on `/predict` and `/predict/batch` |
| SSH | Port 22 open for demo; restrict `cidr_blocks` to your IP in production |
| Docker | Multi-stage build, non-root `appuser` |
| Model files | Mounted at runtime — not baked into the Docker image |

---

See the top-level [README.md](../README.md) for the full platform architecture.

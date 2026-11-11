# SENTINEL Risk API

Production-grade risk-scoring API built with FastAPI. Scores financial transactions
for fraud indicators using rule-based feature engineering and a trained XGBoost model.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Risk API (FastAPI)              │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │  /score  │  │/score-   │  │/model-    │ │
│  │          │  │ batch    │  │ info      │ │
│  └────┬─────┘  └────┬─────┘  └────┬──────┘ │
│       │              │             │         │
│       ▼              ▼             ▼         │
│  ┌─────────────────────────────────────────┐ │
│  │         Risk Scoring Engine             │ │
│  │  • Velocity scoring                     │ │
│  │  • Amount classification                │ │
│  │  • Frequency analysis                   │ │
│  │  • Cross-entity correlation             │ │
│  │  • Rule-based flagging                  │ │
│  └─────────────────────────────────────────┘ │
│       │                                      │
│       ▼                                      │
│  ┌─────────────────────────────────────────┐ │
│  │     Feature Engineering Pipeline        │ │
│  │  (sentinel_rules from Component 4)     │ │
│  └─────────────────────────────────────────┘ │
│       │                                      │
│       ▼                                      │
│  ┌─────────────────────────────────────────┐ │
│  │       XGBoost Model (ONNX)              │ │
│  │  (trained in Component 4)               │ │
│  └─────────────────────────────────────────┘ │
│                                             │
└─────────────────────────────────────────────┘
```

## API Endpoints

### POST `/score`
Score a single transaction for risk indicators.

**Request Body:**
```json
{
  "amount": 1500.00,
  "timestamp": "2024-12-15T10:30:00Z",
  "entity_id": "user_123"
}
```

**Response:**
```json
{
  "risk_score": 0.85,
  "risk_category": "high",
  "factors": ["velocity", "amount"],
  "confidence": 0.92
}
```

### POST `/score-batch`
Score multiple transactions in a single request.

**Request Body:**
```json
{
  "transactions": [
    {"amount": 1500.00, "timestamp": "...", "entity_id": "user_123"},
    {"amount": 450.00, "timestamp": "...", "entity_id": "user_456"}
  ]
}
```

**Response:**
```json
{
  "results": [...],
  "summary": {
    "total_scored": 2,
    "high_risk": 1,
    "medium_risk": 1,
    "low_risk": 0
  }
}
```

### GET `/model-info`
Retrieve metadata about the loaded model (version, type, training date).

### GET `/health`
Service health check returning status and uptime.

### GET `/hash/{file}`
Verify SHA-256 integrity of a data or model file.

---

## Implementation Details

### Risk Scoring Logic

The risk engine evaluates transactions across four dimensions:

1. **Velocity Score:** Measures the rate of transactions within rolling time windows.
   High velocity (many transactions in short periods) indicates potential fraud.

2. **Amount Classification:** Categorises transaction amounts into thresholds:
   - Small: under normal transaction range
   - Medium: within expected range
   - Large: above typical thresholds (higher risk weight)

3. **Frequency Analysis:** Counts and sums transactions over multiple time horizons
   (short-term, medium-term, long-term) to detect anomalous patterns.

4. **Cross-Entity Correlation:** Identifies linked entities with correlated suspicious
   activity patterns, flagging coordinated fraud rings.

### Data Integrity

All data files and model artifacts are verified using SHA-256 hashing. The `/hash/`
endpoint provides on-demand integrity checks, ensuring no tampering with model weights
or training data.

### Model Loading

The FastAPI application loads the XGBoost model (exported as ONNX) at startup. The
model is trained using the pipeline in Component 4 (`04-model-training/`).

---

## Local Development

### Prerequisites
- Python 3.10+
- Docker & Docker Compose

### Run with Docker

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`.

### Run Locally (No Docker)

```bash
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Score a transaction
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"amount": 1500.00, "timestamp": "2024-12-15T10:30:00Z", "entity_id": "user_123"}'

# Get model info
curl http://localhost:8000/model-info
```

---

## AWS Deployment

This component includes a Terraform configuration (`main.tf`) for deploying to AWS:

- **S3 Bucket:** Stores model artifacts and data files
- **IAM Policy:** Grants minimal read permissions for data access

```bash
terraform init
terraform plan -var="environment=production"
terraform apply -var="environment=production"
```

---

## Configuration

Environment variables (set via `.env` or cloud configuration):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_DIR` | Path to transaction data | `./data` |
| `MODEL_PATH` | Path to trained model file | `./model.onnx` |
| `SECRET_KEY` | API signing key | (required) |

---

## File Structure

```
01-risk-api/
├── README.md                 # This file
├── main.tf                   # Terraform (S3 + IAM)
└── app/
    ├── README.md             # Application documentation
    ├── main.py               # FastAPI application (scoring engine)
    └── requirements.txt      # Python dependencies
```

## Sentinel Data Integration

The Risk API consumes the Sentinel transaction dataset. Feature engineering is
handled by the rule-based pipeline defined in `sentinel_rules.py` (Component 4),
which transforms raw transaction data into risk-relevant features before model
inference.

---

See the top-level [README.md](../README.md) for the full platform architecture.

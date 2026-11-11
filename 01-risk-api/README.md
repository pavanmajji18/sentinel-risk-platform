# SENTINEL — Real-Time Risk API (Module 01)

High-performance, containerized financial transaction risk-scoring service built with **FastAPI**. Evaluates payment events in real time against fifteen rule heuristics and hybrid machine learning scoring.

---

## Architecture Overview

```
                      Inbound Client Request
                                │
                        [ X-API-Key Auth ]
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
      POST /v1/score                      POST /v2/score
   (Deterministic Rules)               (Hybrid Rule + ML)
              │                                   │
              ▼                                   ▼
   15 Evaluation Heuristics            Rule Engine + Model Score
   • High Velocity (R01, R10)         Weighted Aggregation
   • Geographic Jump (R02)             Decision Banding
   • Night Window (R03)                           │
   • Failed Attempts (R04)                        │
   • Ratio to 90d Avg (R05, R06)                  │
              │                                   │
              └─────────────────┬─────────────────┘
                                ▼
                       Structured Response
                { score, band, rules_triggered }
```

---

## Detection Heuristics & Rules Engine

The scoring engine evaluates transactions against fifteen codified detection rules:

| Rule Code | Description | Weight | Trigger Condition |
| :--- | :--- | :--- | :--- |
| **FR01** | High Velocity Burst | `0.15` | Transaction count in 1h $\ge$ 5 |
| **FR02** | Rapid Cumulative Spend | `0.10` | 24-hour spend $> 5\times$ historical 90-day average |
| **FR03** | Frequent Small Testing | `0.10` | $\ge 3$ transactions in 1h with amount $< 100$ |
| **FR04** | Dormant Account Awakening | `0.15` | High spend after $> 72$ hours of inactivity |
| **R01** | Untrusted Device | `0.12` | First transaction observed from new device |
| **R02** | Geolocation Discrepancy | `0.10` | Distance from primary location $> 100$ km |
| **R03** | Off-Hours Activity | `0.08` | Transaction occurring between 22:00 and 06:00 |
| **R04** | Authentication Failures | `0.15` | $\ge 3$ prior failed authentication attempts |
| **R05** | Baseline Spend Outlier | `0.10` | Current amount $> 3\times$ customer 90-day average |
| **R06** | New Profile High Value | `0.15` | High transaction value on profile with no 90-day history |
| **R10** | High-Velocity Micro-Charge | `0.12` | Velocity burst combined with low nominal amounts |
| **R11** | High-Value Night Transaction | `0.10` | Transaction value $> 10,000$ in late-night window |
| **R12** | Distant New Device | `0.15` | Unrecognized device paired with distance $> 100$ km |
| **R13** | Rapid Retry Burst | `0.10` | Repeat transactions within seconds of authentication failure |
| **R14** | Critical Risk Factor Cluster | `0.18` | Simultaneous trigger of $\ge 4$ independent risk rules |

### Decision Banding
* **Safe (`0.0 - 0.20`):** Low risk profile, approved automatically.
* **Monitor (`0.20 - 0.50`):** Elevated risk; queued for operational monitoring or step-up authentication.
* **Block (`> 0.50`):** High-confidence risk; transaction rejected immediately.

---

## API Endpoints

### 1. `GET /health`
System health check and active rule count (unauthenticated).

```json
{
  "status": "healthy",
  "rules_loaded": 15
}
```

### 2. `POST /v1/score`
Evaluate a transaction using deterministic rule engine. Requires `X-API-Key` header.

**Request:**
```bash
curl -X POST http://localhost:8000/v1/score \
  -H "X-API-Key: sentinel-secret-key-prod" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 25000.0,
    "customer_id": "cust_mock_001",
    "merchant_id": "merch_mock_99",
    "device_id": "dev_mock_alpha",
    "amount_to_avg_ratio": 4.5,
    "is_night": 1,
    "is_new_device": 1,
    "distance_km": 250.0,
    "failed_attempts": 3,
    "txn_count_1h": 6,
    "txn_amount_24h": 75000.0,
    "time_since_last_txn": 80.0,
    "account_age_days": 180
  }'
```

**Response:**
```json
{
  "transaction_id": "tx_20261111183000_a1b2",
  "score": 0.88,
  "band": "Block",
  "rules_triggered": ["FR01", "FR02", "FR04", "R01", "R02", "R03", "R04", "R05", "R12", "R14"],
  "decision": "BLOCK",
  "latency_ms": 1.25
}
```

### 3. `POST /v2/score`
Hybrid evaluation combining deterministic rule weights with statistical machine learning inference.

### 4. `GET /hash/{filename}`
Cryptographic SHA-256 integrity verification for local configuration and rule files.

---

## Local Development & Testing

### Running with Docker Compose
```bash
docker compose up --build
```

### Running Locally with Python Virtual Environment
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate

# Install dependencies
pip install -r app/requirements.txt

# Set local API key
export SENTINEL_API_KEY="sentinel-secret-key-prod"

# Start service
cd app
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Automated Validation Suite
Execute the comprehensive test suite validating endpoints, authentication, and boundary risk bands:
```bash
python validate_module01.py
```

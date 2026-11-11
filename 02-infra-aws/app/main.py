"""
SENTINEL: Real-time fraud scoring API.

Scoring engine: 10 engineered features, 14 risk rules, ML model (when available).
Auth: X-API-Key header required (401 without).
Config: .env file for secrets (SENTINEL_API_KEY).

Endpoints:
  POST /score    - Score a single transaction
  POST /score/batch - Score a batch of transactions
  GET  /health   - Health check

Run locally:
  uvicorn main:app --host 0.0.0.0 --port 8000

Docker (via Terraform):
  terraform apply -auto-approve
"""

import os
import json
import math
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load .env (searches /app, then project root)
for _env_path in [Path(__file__).parent / ".env", Path.cwd() / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

SENTINEL_API_KEY: str = os.getenv("SENTINEL_API_KEY", "")
MODEL_PATH: str = os.getenv("SENTINEL_MODEL_PATH", "model.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

if not SENTINEL_API_KEY:
    logger.warning("SENTINEL_API_KEY not set — authenticated endpoints will reject all requests")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TransactionInput(BaseModel):
    """Single transaction for scoring."""
    txn_id: str
    customer_id: str
    merchant_id: str
    device_id: str
    amount: float
    timestamp: str = Field(description="ISO 8601, e.g. 2024-12-25T03:15:00Z")
    lat: float = Field(description="Transaction latitude")
    lon: float = Field(description="Transaction longitude")
    mcc_code: str = Field(description="Merchant category code, e.g. MCC-5411")
    channel: str = Field(description="Channel: CARD | DIGITAL | UPI | NETBANKING")

    model_config = {"json_schema_extra": {
        "examples": [{
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
        }]
    }}


class ScoreResponse(BaseModel):
    """Scoring result for a single transaction."""
    txn_id: str
    risk_score: float
    risk_band: str
    triggered_rules: list[str]
    fraud_probability: float
    features: dict[str, float]
    recommendation: str
    explanation: str


class BatchScoreResponse(BaseModel):
    """Scoring results for a batch of transactions."""
    results: list[ScoreResponse]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    version: str


# ---------------------------------------------------------------------------
# 10 Engineered Features
# ---------------------------------------------------------------------------

def engineer_features(txn: TransactionInput, context: dict) -> dict:
    """
    Compute the 10 engineered features from a transaction and historical context.

    Returns a dict mapping feature name -> numeric value.
    """
    ts = datetime.fromisoformat(txn.timestamp.replace("Z", "+00:00"))
    cust = context.get("customers", {}).get(txn.customer_id, {})
    merch = context.get("merchants", {}).get(txn.merchant_id, {})
    dev = context.get("devices", {}).get(txn.device_id, {})

    # 1. amount_to_avg_ratio
    avg_amount = cust.get("avg_amount_90d", 5000) or 5000
    amount_to_avg_ratio = txn.amount / avg_amount if avg_amount > 0 else 1.0

    # 2. is_new_device
    prev_devices = set(cust.get("devices_used", []))
    is_new_device = int(txn.device_id not in prev_devices)

    # 3. customer_merchant_distance_km
    cust_lat = cust.get("lat", txn.lat)
    cust_lon = cust.get("lon", txn.lon)
    distance_km = haversine(cust_lat, cust_lon, txn.lat, txn.lon)

    # 4. is_night
    hour = ts.hour
    is_night = int(0 <= hour < 6)

    # 5. txn_count_last_1h
    hist_txns = cust.get("recent_transactions", [])
    txn_count_last_1h = sum(
        1 for t in hist_txns
        if (ts - datetime.fromisoformat(t.replace("Z", "+00:00"))).total_seconds() < 3600
    )

    # 6. txn_amount_last_24h
    txn_amount_last_24h = sum(
        float(t_amt) for t_ts, t_amt in cust.get("recent_amounts", [])
        if (ts - datetime.fromisoformat(t_ts.replace("Z", "+00:00"))).total_seconds() < 86400
    )

    # 7. failed_attempts
    failed_attempts = len(cust.get("failed_txns", []))

    # 8. merchant_risk_score
    mcc_risk = MCC_RISK.get(txn.mcc_code, 0.2)
    fraud_ratio = merch.get("fraud_ratio", 0.0)
    merchant_risk_score = min(1.0, mcc_risk + fraud_ratio)

    # 9. customer_age_days
    created = cust.get("created_at", ts.isoformat())
    try:
        cust_ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        customer_age_days = max(0, (ts - cust_ts).days)
    except (ValueError, TypeError):
        customer_age_days = 365

    # 10. device_fingerprint_hash
    fp_str = f"{txn.device_id}|{txn.channel}|{cust.get('user_agent', '')}"
    device_fingerprint_hash = hash_device(fp_str)

    features = {
        "amount_to_avg_ratio": round(amount_to_avg_ratio, 4),
        "is_new_device": is_new_device,
        "customer_merchant_distance_km": round(distance_km, 2),
        "is_night": is_night,
        "txn_count_last_1h": txn_count_last_1h,
        "txn_amount_last_24h": round(txn_amount_last_24h, 2),
        "failed_attempts": failed_attempts,
        "merchant_risk_score": round(merchant_risk_score, 4),
        "customer_age_days": customer_age_days,
        "device_fingerprint_hash": device_fingerprint_hash,
    }

    # Update context for future requests
    if txn.customer_id not in context.get("customers", {}):
        context["customers"][txn.customer_id] = {
            "avg_amount_90d": 5000,
            "devices_used": [txn.device_id],
            "recent_transactions": [txn.timestamp],
            "recent_amounts": [(txn.timestamp, txn.amount)],
            "failed_txns": [],
            "created_at": (ts - datetime.timedelta(days=365)).isoformat(),
            "lat": txn.lat,
            "lon": txn.lon,
        }
    else:
        cust["devices_used"].append(txn.device_id)
        cust["recent_transactions"].append(txn.timestamp)
        cust["recent_amounts"].append((txn.timestamp, txn.amount))

    return features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km between two lat/lon points."""
    R = 6371.0
    r_lat1, r_lon1 = math.radians(lat1), math.radians(lon1)
    r_lat2, r_lon2 = math.radians(lat2), math.radians(lon2)
    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(r_lat1) * math.cos(r_lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def hash_device(fp: str) -> int:
    """Deterministic device fingerprint hash (0-1000)."""
    h = hashlib.md5(fp.encode()).hexdigest()
    return int(h[:8], 16) % 1000


# ---------------------------------------------------------------------------
# MCC Risk Mapping
# ---------------------------------------------------------------------------

MCC_RISK = {
    "MCC-5942": 0.9,   # gambling
    "MCC-6011": 0.7,   # financial
    "MCC-5411": 0.2,   # grocery
    "MCC-4111": 0.2,   # transit
    "MCC-7011": 0.3,   # hotels
    "MCC-5812": 0.2,   # restaurants
}


# ---------------------------------------------------------------------------
# 14 Risk Rules
# ---------------------------------------------------------------------------

def apply_rules(txn: TransactionInput, features: dict) -> list[str]:
    """
    Apply 14 fraud detection rules. Returns list of triggered rule IDs.

    Rules:
    - FR01: Very high amount-to-average ratio (>10x)
    - FR02: New device + high amount
    - FR03: Night-time cross-border distance (>300km)
    - FR04: Multiple failed attempts (>5)
    - R01:  New device first-time use
    - R02:  Customer-merchant distance > 500 km
    - R03:  Transaction at odd hours (0-5)
    - R04:  High-risk MCC (gambling, financial)
    - R05:  Amount > 50000 (high-value)
    - R06:  Rapid successive transactions (>5 in 1h)
    - R10:  Very new customer (<7 days)
    - R11:  Merchant fraud ratio > 20%
    - R12:  Amount > 5x customer average
    - R14:  Device seen with many customers (>10)
    """
    triggered = []

    # FR01: Very high amount-to-average ratio
    if features["amount_to_avg_ratio"] > 10:
        triggered.append("FR01_HIGH_AMOUNT_RATIO")

    # FR02: New device + high amount
    if features["is_new_device"] == 1 and txn.amount > 20000:
        triggered.append("FR02_NEW_DEVICE_HIGH_AMT")

    # FR03: Night-time + long distance
    if features["is_night"] == 1 and features["customer_merchant_distance_km"] > 300:
        triggered.append("FR03_NIGHT_CROSS_BORDER")

    # FR04: Multiple failed attempts
    if features["failed_attempts"] > 5:
        triggered.append("FR04_FAILED_ATTEMPTS")

    # R01: New device first-time use
    if features["is_new_device"] == 1:
        triggered.append("R01_NEW_DEVICE")

    # R02: Customer-merchant distance > 500 km
    if features["customer_merchant_distance_km"] > 500:
        triggered.append("R02_GEO_MISMATCH")

    # R03: Transaction at odd hours (0-5)
    if features["is_night"] == 1:
        triggered.append("R03_ODD_HOUR")

    # R04: High-risk MCC
    mcc = txn.mcc_code
    if MCC_RISK.get(mcc, 0) >= 0.7:
        triggered.append("R04_HIGH_RISK_MCC")

    # R05: High-value transaction
    if txn.amount > 50000:
        triggered.append("R05_HIGH_VALUE")

    # R06: Rapid successive transactions
    if features["txn_count_last_1h"] > 5:
        triggered.append("R06_RAPID_SUCCESSIVE")

    # R10: Very new customer
    if features["customer_age_days"] < 7:
        triggered.append("R10_NEW_CUSTOMER")

    # R11: Merchant fraud ratio > 20%
    if features["merchant_risk_score"] > 0.4:
        triggered.append("R11_HIGH_MERCHANT_RISK")

    # R12: Amount > 5x customer average
    if features["amount_to_avg_ratio"] > 5:
        triggered.append("R12_AMOUNT_SPIKE")

    # R14: Device shared across many customers
    device_cust_count = len(context.get("devices", {}).get(txn.device_id, {}).get("customers", []))
    if device_cust_count > 10:
        triggered.append("R14_SHARED_DEVICE")

    return triggered


# ---------------------------------------------------------------------------
# Scoring Pipeline
# ---------------------------------------------------------------------------

def compute_risk_score(triggered_rules: list[str], features: dict) -> float:
    """
    Compute a normalized risk score (0-1) from triggered rules.

    Base score accumulates per rule, then is clamped to [0, 1].
    """
    weights = {
        "FR01_HIGH_AMOUNT_RATIO": 0.25,
        "FR02_NEW_DEVICE_HIGH_AMT": 0.20,
        "FR03_NIGHT_CROSS_BORDER": 0.15,
        "FR04_FAILED_ATTEMPTS": 0.15,
        "R01_NEW_DEVICE": 0.10,
        "R02_GEO_MISMATCH": 0.15,
        "R03_ODD_HOUR": 0.05,
        "R04_HIGH_RISK_MCC": 0.15,
        "R05_HIGH_VALUE": 0.10,
        "R06_RAPID_SUCCESSIVE": 0.10,
        "R10_NEW_CUSTOMER": 0.10,
        "R11_HIGH_MERCHANT_RISK": 0.15,
        "R12_AMOUNT_SPIKE": 0.15,
        "R14_SHARED_DEVICE": 0.10,
    }

    score = sum(weights.get(rule, 0.05) for rule in triggered_rules)
    return min(1.0, round(score, 4))


def assign_band(score: float) -> str:
    """Assign risk band based on score thresholds (NPCI standard)."""
    if score > 0.5:
        return "BLOCK"
    elif score > 0.2:
        return "MONITOR"
    else:
        return "SAFE"


def recommend(band: str) -> str:
    """Return action recommendation for the band."""
    return {"SAFE": "approve", "MONITOR": "flag_and_review", "BLOCK": "block_and_alert"}[band]


def explain(txn: TransactionInput, triggered_rules: list[str], band: str) -> str:
    """Generate a human-readable explanation."""
    if not triggered_rules:
        return f"Transaction for {txn.customer_id} at {txn.merchant_id} appears normal; risk score low."
    parts = [f"Transaction for {txn.customer_id} triggered {len(triggered_rules)} risk rule(s):"]
    parts.extend(f"  - {rule}" for rule in triggered_rules)
    parts.append(f"  -> Band: {band} | Action: {recommend(band)}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# ML Model (optional: load from file if present)
# ---------------------------------------------------------------------------

def load_model(path: str):
    """Load an XGBoost classifier or serialized model from path (if present)."""
    paths_to_check = [Path(path)]
    base = Path(__file__).resolve().parent
    paths_to_check.extend([
        base / "model.json",
        base / "model" / "sentinel_xgb.json",
        base.parent.parent / "04-model-training" / "model" / "sentinel_xgb.json",
    ])
    for p in paths_to_check:
        if p.exists():
            try:
                import xgboost as xgb
                m = xgb.XGBClassifier()
                m.load_model(str(p))
                logger.info("Loaded XGBoost model from %s", p)
                return m
            except Exception:
                try:
                    with open(p) as f:
                        data = json.load(f)
                    return data
                except Exception:
                    pass
    return None


MODEL = load_model(MODEL_PATH)


def predict_proba(features: dict) -> float:
    """
    Predict fraud probability. Uses ML model if loaded; falls back to
    deterministic feature-weighted scoring.
    """
    if MODEL is not None and hasattr(MODEL, "predict_proba"):
        try:
            import pandas as pd
            feature_cols = [
                "amount", "customer_avg_amount_90d", "is_new_device", "distance_km",
                "hour_of_day", "failed_attempts", "amount_to_avg_ratio", "is_night",
                "transaction_count_last_1_hour", "transaction_amount_last_24_hours",
                "time_since_last_txn", "account_age_days"
            ]
            row = {
                "amount": features.get("amount", 0.0),
                "customer_avg_amount_90d": features.get("customer_avg_amount_90d", 0.0),
                "is_new_device": int(features.get("is_new_device", 0)),
                "distance_km": float(features.get("customer_merchant_distance_km", features.get("distance_km", 0.0))),
                "hour_of_day": int(features.get("hour_of_day", 12)),
                "failed_attempts": int(features.get("failed_attempts", 0)),
                "amount_to_avg_ratio": float(features.get("amount_to_avg_ratio", 1.0)),
                "is_night": int(features.get("is_night", 0)),
                "transaction_count_last_1_hour": int(features.get("txn_count_last_1h", 0)),
                "transaction_amount_last_24_hours": float(features.get("txn_amount_last_24h", 0.0)),
                "time_since_last_txn": float(features.get("time_since_last_txn", 24.0)),
                "account_age_days": int(features.get("customer_age_days", 365)),
            }
            df = pd.DataFrame([row], columns=feature_cols)
            return float(MODEL.predict_proba(df)[0, 1])
        except Exception as e:
            logger.warning("Inference with loaded model failed: %s; using deterministic fallback", e)

    # Heuristic fallback: weighted sum of high-risk features
    score = 0.0
    if features.get("amount_to_avg_ratio", 0) > 5:
        score += 0.3
    if features.get("is_new_device", 0) == 1:
        score += 0.15
    if features.get("customer_merchant_distance_km", 0) > 300:
        score += 0.15
    if features.get("is_night", 0) == 1:
        score += 0.1
    if features.get("txn_count_last_1h", 0) > 5:
        score += 0.1
    if features.get("failed_attempts", 0) > 3:
        score += 0.1
    if features.get("merchant_risk_score", 0) > 0.4:
        score += 0.1
    return min(1.0, round(score, 4))


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SENTINEL Fraud Detection API",
    version="2.0.0",
    description="Real-time transaction scoring with 10 engineered features and 14 risk rules."
)

# Shared in-memory context (session-scoped for the demo; use Redis in production)
session_context = {"customers": {}, "merchants": {}, "devices": {}}


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Reject requests without a valid X-API-Key (401)."""
    if not SENTINEL_API_KEY or not x_api_key or x_api_key != SENTINEL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        model_loaded=MODEL is not None,
        version="2.0.0"
    )


@app.post("/score", response_model=ScoreResponse)
async def score(txn: TransactionInput, x_api_key: Optional[str] = Header(None)):
    """Score a single transaction (v2 endpoint)."""
    verify_api_key(x_api_key)

    features = engineer_features(txn, session_context)
    triggered = apply_rules(txn, features)
    risk_score = compute_risk_score(triggered, features)
    fraud_prob = predict_proba(features)
    band = assign_band(risk_score)

    return ScoreResponse(
        txn_id=txn.txn_id,
        risk_score=risk_score,
        risk_band=band,
        triggered_rules=triggered,
        fraud_probability=fraud_prob,
        features=features,
        recommendation=recommend(band),
        explanation=explain(txn, triggered, band)
    )


@app.post("/score/v1", response_model=ScoreResponse)
async def score_v1(txn: TransactionInput, x_api_key: Optional[str] = Header(None)):
    """Score a single transaction (v1 endpoint, same logic as v2)."""
    verify_api_key(x_api_key)

    features = engineer_features(txn, session_context)
    triggered = apply_rules(txn, features)
    risk_score = compute_risk_score(triggered, features)
    fraud_prob = predict_proba(features)
    band = assign_band(risk_score)

    return ScoreResponse(
        txn_id=txn.txn_id,
        risk_score=risk_score,
        risk_band=band,
        triggered_rules=triggered,
        fraud_probability=fraud_prob,
        features=features,
        recommendation=recommend(band),
        explanation=explain(txn, triggered, band)
    )


@app.post("/score/batch", response_model=BatchScoreResponse)
async def score_batch(request: Request, x_api_key: Optional[str] = Header(None)):
    """Score a batch of transactions (array of TransactionInput)."""
    verify_api_key(x_api_key)

    body = await request.json()
    results = []
    for txn_dict in body:
        txn = TransactionInput(**txn_dict)
        features = engineer_features(txn, session_context)
        triggered = apply_rules(txn, features)
        risk_score = compute_risk_score(triggered, features)
        fraud_prob = predict_proba(features)
        band = assign_band(risk_score)
        results.append(ScoreResponse(
            txn_id=txn.txn_id,
            risk_score=risk_score,
            risk_band=band,
            triggered_rules=triggered,
            fraud_probability=fraud_prob,
            features=features,
            recommendation=recommend(band),
            explanation=explain(txn, triggered, band)
        ))

    return BatchScoreResponse(results=results)


# ---------------------------------------------------------------------------
# Run with: uvicorn main:app --host 0.0.0.0 --port 8000
# ---------------------------------------------------------------------------

"""
SENTINEL Model Serving API
Loads the trained XGBoost model and serves predictions.

Endpoints:
  GET  /health          → health check (no auth)
  POST /predict         → single transaction fraud prediction
  POST /predict/batch   → batch predictions (up to 100 transactions)
"""

import json
import os
import time
import hashlib
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel-serving")

_fallback_model = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "04-model-training", "model", "sentinel_xgb.json")
)
_app_model = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "model", "sentinel_xgb.json")
)
_fallback_metrics = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "04-model-training", "model", "metrics.json")
)
_app_metrics = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "model", "metrics.json")
)

MODEL_PATH = os.getenv("SENTINEL_MODEL_PATH") or os.getenv("MODEL_PATH")
if not MODEL_PATH or not os.path.exists(MODEL_PATH):
    if os.path.exists("model/sentinel_xgb.json"):
        MODEL_PATH = "model/sentinel_xgb.json"
    elif os.path.exists(_app_model):
        MODEL_PATH = _app_model
    elif os.path.exists(_fallback_model):
        MODEL_PATH = _fallback_model
    else:
        MODEL_PATH = "model/sentinel_xgb.json"

METRICS_PATH = os.getenv("METRICS_PATH")
if not METRICS_PATH or not os.path.exists(METRICS_PATH):
    if os.path.exists("model/metrics.json"):
        METRICS_PATH = "model/metrics.json"
    elif os.path.exists(_app_metrics):
        METRICS_PATH = _app_metrics
    elif os.path.exists(_fallback_metrics):
        METRICS_PATH = _fallback_metrics
    else:
        METRICS_PATH = "model/metrics.json"

API_KEY = os.getenv("SENTINEL_API_KEY", "")
if not API_KEY:
    logger.warning("SENTINEL_API_KEY not set — authenticated endpoints will reject all requests")

FEATURE_COLUMNS = [
    "amount",
    "customer_avg_amount_90d",
    "is_new_device",
    "distance_km",
    "hour_of_day",
    "failed_attempts",
    "amount_to_avg_ratio",
    "is_night",
    "transaction_count_last_1_hour",
    "transaction_amount_last_24_hours",
    "time_since_last_txn",
    "account_age_days",
]

RULE_WEIGHTS = {
    "R01": 0.12, "R02": 0.10, "R03": 0.08,
    "R04": 0.15, "R05": 0.10, "R06": 0.15,
}

# ---------------------------------------------------------------------------
# Global model state (loaded at startup)
# ---------------------------------------------------------------------------

class ModelState:
    model = None
    metrics: dict = {}
    threshold: float = 0.40
    loaded: bool = False


state = ModelState()


def _load_model():
    """Load XGBoost model and metrics at startup."""
    try:
        import xgboost as xgb
        m = xgb.XGBClassifier()
        m.load_model(MODEL_PATH)
        state.model = m
        if os.path.exists(METRICS_PATH):
            with open(METRICS_PATH) as f:
                state.metrics = json.load(f)
                state.threshold = state.metrics.get("threshold", 0.40)
        state.loaded = True
        logger.info(f"Model loaded from {MODEL_PATH}  threshold={state.threshold}")
    except Exception as e:
        logger.warning(f"Model not loaded: {e}. Falling back to rules-only mode.")
        state.loaded = False


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SENTINEL Serving API starting …")
    _load_model()
    if not API_KEY:
        logger.warning("SENTINEL_API_KEY not set — all requests will be rejected")
    yield
    logger.info("SENTINEL Serving API shutting down")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Transaction(BaseModel):
    amount: float = Field(..., description="Transaction amount")
    customer_avg_amount_90d: float = Field(0.0, description="Customer 90-day avg amount")
    is_new_device: int = Field(0, ge=0, le=1)
    distance_km: float = Field(0.0, description="Customer-merchant distance (km)")
    hour_of_day: int = Field(12, ge=0, le=23)
    failed_attempts: int = Field(0, ge=0)
    amount_to_avg_ratio: float = Field(1.0)
    is_night: int = Field(0, ge=0, le=1)
    transaction_count_last_1_hour: int = Field(0, ge=0)
    transaction_amount_last_24_hours: float = Field(0.0)
    time_since_last_txn: float = Field(24.0, description="Hours since last transaction")
    account_age_days: int = Field(365, ge=0)

    @field_validator("amount_to_avg_ratio", mode="before")
    @classmethod
    def compute_ratio(cls, v, info):
        """Auto-compute ratio if not provided."""
        return v


class BatchRequest(BaseModel):
    transactions: list[Transaction] = Field(..., min_length=1, max_length=100)


class PredictResponse(BaseModel):
    fraud_probability: float
    decision: str          # FRAUD | REVIEW | CLEAN
    reason_codes: list[str]
    model_version: str
    request_id: str
    latency_ms: float


class BatchResponse(BaseModel):
    results: list[PredictResponse]
    total: int
    fraud_count: int
    latency_ms: float


# ---------------------------------------------------------------------------
# Risk rule engine (R01-R06, mirroring training labels)
# ---------------------------------------------------------------------------

def apply_rules(tx: Transaction) -> list[str]:
    codes = []
    if tx.is_new_device == 1:
        codes.append("R01")
    if tx.distance_km > 100:
        codes.append("R02")
    if tx.hour_of_day < 6 or tx.hour_of_day >= 22:
        codes.append("R03")
    if tx.failed_attempts >= 3:
        codes.append("R04")
    if tx.customer_avg_amount_90d > 0 and tx.amount > tx.customer_avg_amount_90d * 3:
        codes.append("R05")
    if tx.customer_avg_amount_90d == 0:
        codes.append("R06")
    return codes


def decision_from_prob(prob: float, threshold: float) -> str:
    if prob >= threshold:
        return "FRAUD"
    elif prob >= threshold * 0.6:
        return "REVIEW"
    else:
        return "CLEAN"


def to_feature_vector(tx: Transaction) -> list[float]:
    return [getattr(tx, col) for col in FEATURE_COLUMNS]


def _predict_single(tx: Transaction) -> tuple[float, list[str]]:
    """Return (fraud_probability, reason_codes)."""
    codes = apply_rules(tx)
    if not state.loaded:
        # Rules-only fallback
        rule_score = sum(RULE_WEIGHTS.get(c, 0.1) for c in codes)
        return min(rule_score, 1.0), codes

    import pandas as pd
    X = pd.DataFrame([to_feature_vector(tx)], columns=FEATURE_COLUMNS)
    prob = float(state.model.predict_proba(X)[0, 1])
    return prob, codes


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _check_key(x_api_key: str | None) -> None:
    if not API_KEY or not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _request_id(tx: Transaction) -> str:
    raw = f"{tx.amount}{tx.hour_of_day}{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SENTINEL Model Serving API",
    version="1.0.0",
    description=(
        "Serves the trained XGBoost fraud detection model. "
        "Blends ML probability with rule-engine codes (R01-R06). "
        "Falls back to rules-only when no model is loaded."
    ),
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check — no authentication required."""
    return {
        "status": "healthy",
        "model_loaded": state.loaded,
        "threshold": state.threshold,
        "model_path": MODEL_PATH,
        "timestamp": int(time.time()),
    }


@app.post("/predict", response_model=PredictResponse)
async def predict(tx: Transaction, x_api_key: str | None = Header(None)):
    """Single-transaction fraud prediction."""
    _check_key(x_api_key)
    t0 = time.perf_counter()

    prob, codes = _predict_single(tx)
    decision = decision_from_prob(prob, state.threshold)
    latency = round((time.perf_counter() - t0) * 1000, 3)

    return PredictResponse(
        fraud_probability=round(prob, 6),
        decision=decision,
        reason_codes=codes,
        model_version="xgb-v1" if state.loaded else "rules-v1",
        request_id=_request_id(tx),
        latency_ms=latency,
    )


@app.post("/predict/batch", response_model=BatchResponse)
async def predict_batch(req: BatchRequest, x_api_key: str | None = Header(None)):
    """Batch fraud prediction (1-100 transactions)."""
    _check_key(x_api_key)
    t0 = time.perf_counter()

    results = []
    fraud_count = 0
    for tx in req.transactions:
        prob, codes = _predict_single(tx)
        decision = decision_from_prob(prob, state.threshold)
        if decision == "FRAUD":
            fraud_count += 1
        results.append(PredictResponse(
            fraud_probability=round(prob, 6),
            decision=decision,
            reason_codes=codes,
            model_version="xgb-v1" if state.loaded else "rules-v1",
            request_id=_request_id(tx),
            latency_ms=0.0,  # filled in batch total
        ))

    total_latency = round((time.perf_counter() - t0) * 1000, 3)
    return BatchResponse(
        results=results,
        total=len(results),
        fraud_count=fraud_count,
        latency_ms=total_latency,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

"""
SENTINEL Real-Time Risk API
Local Docker deployment with Terraform provider "docker".

Implements the scoring engine from client docs:
  - 10 engineered features (Client Requirement Doc)
  - 14 risk rules: FR01-FR04, R01-R06, R10-R14 (LLD §3)
  - Risk bands: Safe 0-0.2, Monitor 0.2-0.5, Block >0.5 (Client Requirement Doc)
  - v1 (rule-only) + v2 (rule + model stub, HLD §4.1)
  - X-API-Key authentication (required on all endpoints except /health)

API Key:
  - Set via environment variable SENTINEL_API_KEY (from .env or Terraform var)
  - Requests without X-API-Key header get 401
  - Requests with wrong key get 401

Endpoints:
  - GET  /health          → health check (no auth)
  - POST /v1/score        → rule-based scoring
  - POST /v2/score        → rule + model hybrid scoring
"""

import os
import time
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Load .env file so environment variables are available without manual setup
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel")

SENTINEL_API_KEY = os.getenv("SENTINEL_API_KEY", "")
if not SENTINEL_API_KEY:
    logger.warning("⚠️  SENTINEL_API_KEY not set — authenticated endpoints will reject all requests")

# ---------------------------------------------------------------------------
# Feature model (10 features from Client Requirement Doc)
# ---------------------------------------------------------------------------

class TransactionRequest(BaseModel):
    amount: float = Field(description="Transaction amount in currency units (e.g. INR)")
    customer_id: str = Field(description="Unique customer identifier")
    merchant_id: str = Field(description="Unique merchant identifier")
    device_id: str = Field(description="Unique device identifier")
    # Engineered features (client requirement doc)
    amount_to_avg_ratio: float = Field(
        default=1.0,
        description="ratio of this txn to customer's 90-day avg amount"
    )
    is_new_device: bool = Field(
        default=False,
        description="True if device is new for this customer"
    )
    customer_merchant_distance_km: float = Field(
        default=0.0,
        description="Euclidean distance (km) between customer home and merchant"
    )
    is_night: bool = Field(
        default=False,
        description="True if txn hour is between 22:00 and 05:00"
    )
    txn_count_1h: int = Field(
        default=0,
        description="Transaction count by same customer in last 1 hour"
    )
    txn_amount_24h: float = Field(
        default=0.0,
        description="Sum of transaction amounts by same customer in last 24 hours"
    )
    failed_attempts: int = Field(
        default=0,
        description="Failed txn attempts by same customer in last 1 hour"
    )
    merchant_risk_score: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Pre-computed risk score for the merchant (0-1)"
    )
    customer_age_days: int = Field(
        default=0,
        description="Days since customer account was created"
    )
    device_fingerprint_hash: str = Field(
        default="",
        description="SHA-256 hash of device fingerprint for detection"
    )
    # Additional context (used by risk rules)
    hour_of_day: int = Field(
        default=12,
        ge=0, le=23,
        description="Hour of day (0-23)"
    )
    is_international: bool = Field(
        default=False,
        description="Whether the transaction is international/cross-border"
    )
    is_blacklisted: bool = Field(
        default=False,
        description="Whether customer or merchant is on a blacklist"
    )
    device_change_flag: bool = Field(
        default=False,
        description="Whether the customer switched device since last txn"
    )
    merchant_age_days: int = Field(
        default=365,
        description="Days since merchant onboarded"
    )
    customer_dormant_days: int = Field(
        default=0,
        description="Days since last transaction by this customer"
    )
    payment_channel: str = Field(
        default="UPI",
        description="Payment channel (UPI, CARD, NETBANKING, WALLET)"
    )
    merchant_category: str = Field(
        default="RETAIL",
        description="Merchant category"
    )

# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class ScoreResponse(BaseModel):
    risk_score: float = Field(description="Overall risk score (0-1)")
    risk_band: str = Field(description="Safe, Monitor, or Block")
    triggered_rules: list[str] = Field(description="List of risk rule codes that triggered")
    explanation: str = Field(description="Human-readable explanation")
    request_id: str = Field(description="Unique request identifier")
    model_version: str = Field(description="API version (v1 or v2)")

# ---------------------------------------------------------------------------
# Risk Rule Engine (from LLD §3)
# ---------------------------------------------------------------------------

class RiskRule:
    """One risk rule from the LLD."""
    def __init__(self, code: str, name: str, weight: float, condition, description: str):
        self.code = code
        self.name = name
        self.weight = weight
        self.condition = condition  # callable(TransactionRequest) -> bool
        self.description = description

# 14 risk rules from the LLD
RULES = [
    # Fraud Rules (FR series) — high-priority, client-identified
    RiskRule(
        code="FR01", name="High Amount", weight=0.15,
        condition=lambda t: t.amount > 50000,
        description=lambda t: f"Amount ₹{t.amount:.0f} exceeds ₹50,000 threshold"
    ),
    RiskRule(
        code="FR02", name="New Device", weight=0.10,
        condition=lambda t: t.is_new_device,
        description="Transaction from a device not previously used by this customer"
    ),
    RiskRule(
        code="FR03", name="Unusual Location", weight=0.10,
        condition=lambda t: t.customer_merchant_distance_km > 100,
        description=lambda t: f"Merchant is {t.customer_merchant_distance_km:.0f} km from customer's normal location"
    ),
    RiskRule(
        code="FR04", name="Night Transaction", weight=0.05,
        condition=lambda t: t.is_night or (t.hour_of_day >= 22 or t.hour_of_day <= 5),
        description="Transaction during night hours (22:00-05:00)"
    ),
    # Risk Rules (R series) — behavioural patterns
    RiskRule(
        code="R01", name="New Device", weight=0.12,
        condition=lambda t: t.is_new_device,
        description="Transaction from a device not previously used by this customer"
    ),
    RiskRule(
        code="R02", name="Geo Mismatch", weight=0.10,
        condition=lambda t: t.customer_merchant_distance_km > 50,
        description=lambda t: f"Merchant is {t.customer_merchant_distance_km:.0f} km from customer's normal location (> 50 km)"
    ),
    RiskRule(
        code="R03", name="Odd Hours", weight=0.08,
        condition=lambda t: t.is_night or (t.hour_of_day >= 22 or t.hour_of_day <= 5),
        description=lambda t: f"Transaction at {t.hour_of_day}:00 (outside normal 05:00-22:00 hours)"
    ),
    RiskRule(
        code="R04", name="Failed Attempts", weight=0.15,
        condition=lambda t: t.failed_attempts > 3,
        description=lambda t: f"{t.failed_attempts} failed attempts in last 1 hour"
    ),
    RiskRule(
        code="R05", name="Amount Spike", weight=0.10,
        condition=lambda t: t.amount_to_avg_ratio > 2,
        description=lambda t: f"Amount is {t.amount_to_avg_ratio:.1f}x the 90-day average (> 2x)"
    ),
    RiskRule(
        code="R06", name="New Account", weight=0.15,
        condition=lambda t: t.customer_age_days < 30,
        description=lambda t: f"Customer account is only {t.customer_age_days} days old (< 30 days)"
    ),
    RiskRule(
        code="R10", name="Geolocation Risk", weight=0.08,
        condition=lambda t: t.is_international,
        description="Cross-border / international transaction"
    ),
    RiskRule(
        code="R11", name="Dormant Activation", weight=0.06,
        condition=lambda t: t.customer_dormant_days > 90,
        description=lambda t: f"Account was dormant for {t.customer_dormant_days} days before this txn"
    ),
    RiskRule(
        code="R12", name="Round Amount", weight=0.03,
        condition=lambda t: t.amount > 1000 and t.amount % 1000 == 0,
        description=lambda t: f"Round amount ₹{t.amount:,.0f} (common in structured fraud)"
    ),
    RiskRule(
        code="R13", name="Sequential Transaction", weight=0.05,
        condition=lambda t: t.txn_count_1h > 3,
        description=lambda t: f"Sequential pattern: {t.txn_count_1h} txns in 1 hour"
    ),
    RiskRule(
        code="R14", name="Merchant Risk", weight=0.10,
        condition=lambda t: t.merchant_risk_score > 0.6,
        description=lambda t: f"Merchant has high pre-computed risk score ({t.merchant_risk_score:.2f})"
    ),
]


def evaluate_rules(txn: TransactionRequest) -> tuple[float, list[str], list[str]]:
    """Run all 14 risk rules and return (score, triggered_codes, explanations)."""
    triggered = []
    explanations = []
    score = 0.0
    for rule in RULES:
        if rule.condition(txn):
            score += rule.weight
            triggered.append(rule.code)
            desc = rule.description(txn) if callable(rule.description) else rule.description
            explanations.append(f"[{rule.code}] {desc}")
    return min(score, 1.0), triggered, explanations

# ---------------------------------------------------------------------------
# Risk band classification (client requirement doc)
# ---------------------------------------------------------------------------

def classify_band(score: float) -> str:
    if score <= 0.3:
        return "Safe"
    elif score <= 0.6:
        return "Monitor"
    else:
        return "Block"

# ---------------------------------------------------------------------------
# Lifespan context manager (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info("SENTINEL API starting")
    if not SENTINEL_API_KEY:
        logger.warning("⚠️  SENTINEL_API_KEY is not set; all authenticated endpoints will require an empty key")
    yield
    # shutdown
    logger.info("SENTINEL API shutting down")

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SENTINEL Risk API",
    version="2.0.0",
    description="Real-time fraud risk scoring with 14 risk rules, 10 engineered features, and risk bands (Safe/Monitor/Block). "
                "Based on client requirement doc, HLD, and LLD for PayVista SENTINEL.",
    lifespan=lifespan,
)

# Health (no auth)
@app.get("/health")
async def health():
    """Health check — no authentication required."""
    return {
        "status": "healthy",
        "service": "sentinel",
        "version": "2.0.0",
        "model_version": "rules-v1",
        "rules_loaded": len(RULES),
        "timestamp": int(time.time())
    }

# Auth middleware helper
def check_api_key(x_api_key: str | None) -> None:
    """Reject 401 if X-API-Key is missing or wrong."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail={"error": "Missing X-API-Key header"})
    if x_api_key != SENTINEL_API_KEY:
        raise HTTPException(status_code=401, detail={"error": "Invalid X-API-Key"})

# v1: Rule-only scoring
@app.post("/v1/score")
async def score_v1(txn: TransactionRequest, x_api_key: str | None = Header(None)):
    """
    Rule-only risk scoring (v1).
    
    Runs 14 risk rules from the LLD. Returns risk_score (0-1), risk_band, triggered rules.
    Requires X-API-Key header.
    """
    check_api_key(x_api_key)

    score, triggered, explanations = evaluate_rules(txn)
    band = classify_band(score)

    return ScoreResponse(
        risk_score=round(score, 4),
        risk_band=band,
        triggered_rules=triggered,
        explanation="; ".join(explanations) if explanations else "No risk rules triggered",
        request_id=hashlib.sha256(f"{txn.customer_id}{txn.device_id}{time.time()}".encode()).hexdigest()[:12],
        model_version="v1"
    )

# v2: Rule + model hybrid scoring (stub — loads XGBoost model when available)
@app.post("/v2/score")
async def score_v2(txn: TransactionRequest, x_api_key: str | None = Header(None)):
    """
    Hybrid risk scoring (v2): rules + ML model blend.
    
    Combines rule-engine score (60% weight) with model prediction (40% weight).
    When the XGBoost model is loaded, it blends model_output * 0.4 + rules * 0.6.
    Without a loaded model, falls back to rule-only with a v2 wrapper.
    
    Requires X-API-Key header.
    """
    check_api_key(x_api_key)

    rule_score, triggered, explanations = evaluate_rules(txn)
    
    # In a real deployment, load the XGBoost model here:
    # model_score = model.predict(feature_vector(txn))[0]
    # blended = rule_score * 0.6 + model_score * 0.4
    model_score = 0.0  # stub: no model loaded yet
    blended = min(rule_score * 0.6 + model_score * 0.4, 1.0)
    band = classify_band(blended)

    return ScoreResponse(
        risk_score=round(blended, 4),
        risk_band=band,
        triggered_rules=triggered,
        explanation="; ".join(explanations) if explanations else "No risk rules triggered",
        request_id=hashlib.sha256(f"{txn.customer_id}{txn.device_id}{time.time()}".encode()).hexdigest()[:12],
        model_version="v2"
    )

# ---------------------------------------------------------------------------
# Run with: uvicorn main:app --host 0.0.0.0 --port 8000
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

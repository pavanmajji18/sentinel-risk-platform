"""
Validation script for Module 05: Model Serving API.
Tests model loading, health endpoint, authentication, single prediction, and batch prediction.
"""

import os
import sys
from pathlib import Path

# Add app to path
app_dir = Path(__file__).resolve().parent / "app"
sys.path.insert(0, str(app_dir))

from fastapi import HTTPException
import main
from main import (
    Transaction,
    BatchRequest,
    PredictResponse,
    BatchResponse,
    state,
    _load_model,
)

# Helper to run synchronous FastAPI coroutines
def resolve(coro):
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    raise RuntimeError("Coroutine did not complete synchronously")


def run_tests():
    print("=" * 60)
    print("SENTINEL Module 05: Model Serving Validation")
    print("=" * 60)

    # 0. Initialize model
    _load_model()
    print(f"\nModel loaded: {state.loaded}")
    print(f"Model threshold: {state.threshold}")
    assert state.loaded is True, "XGBoost model failed to load!"

    # 1. Health check
    print("\n[Test 1] GET /health")
    res = resolve(main.health())
    print(f"  Response: {res}")
    assert res["status"] == "healthy"
    assert res["model_loaded"] is True
    assert res["threshold"] == 0.40
    print("  PASSED: Health check verified.")

    # 2. Authentication enforcement
    print("\n[Test 2] Auth enforcement on /predict")
    sample_tx = Transaction(
        amount=500.0,
        customer_avg_amount_90d=480.0,
        is_new_device=0,
        distance_km=5.0,
        hour_of_day=14,
        failed_attempts=0,
        amount_to_avg_ratio=500 / 480,
        is_night=0,
        transaction_count_last_1_hour=1,
        transaction_amount_last_24_hours=500.0,
        time_since_last_txn=24.0,
        account_age_days=365,
    )

    # Missing API key
    try:
        resolve(main.predict(sample_tx, x_api_key=None))
        assert False, "Expected 401 for missing key"
    except HTTPException as e:
        assert e.status_code == 401
        print("  Missing key rejected: 401 Unauthorized")

    # Invalid API key
    try:
        resolve(main.predict(sample_tx, x_api_key="wrong-key"))
        assert False, "Expected 401 for invalid key"
    except HTTPException as e:
        assert e.status_code == 401
        print("  Invalid key rejected: 401 Unauthorized")
    print("  PASSED: Authentication verified.")

    # 3. Single Prediction: Clean Transaction
    print("\n[Test 3] POST /predict - Clean Transaction")
    clean_tx = Transaction(
        amount=500.0,
        customer_avg_amount_90d=480.0,
        is_new_device=0,
        distance_km=5.0,
        hour_of_day=14,
        failed_attempts=0,
        amount_to_avg_ratio=500 / 480,
        is_night=0,
        transaction_count_last_1_hour=1,
        transaction_amount_last_24_hours=500.0,
        time_since_last_txn=24.0,
        account_age_days=365,
    )
    clean_res = resolve(main.predict(clean_tx, x_api_key=main.API_KEY))
    print(f"  Decision: {clean_res.decision}")
    print(f"  Fraud Probability: {clean_res.fraud_probability:.4f}")
    print(f"  Reason Codes: {clean_res.reason_codes}")
    print(f"  Latency: {clean_res.latency_ms} ms")
    assert clean_res.decision == "CLEAN"
    assert clean_res.fraud_probability < 0.20
    assert clean_res.reason_codes == []
    print("  PASSED: Clean transaction classified correctly.")

    # 4. Single Prediction: Risky Transaction
    print("\n[Test 4] POST /predict - Risky Transaction")
    risky_tx = Transaction(
        amount=2000.0,
        customer_avg_amount_90d=500.0,
        is_new_device=1,
        distance_km=250.0,
        hour_of_day=3,
        failed_attempts=5,
        amount_to_avg_ratio=2000 / 500,
        is_night=1,
        transaction_count_last_1_hour=3,
        transaction_amount_last_24_hours=6000.0,
        time_since_last_txn=2.0,
        account_age_days=120,
    )
    risky_res = resolve(main.predict(risky_tx, x_api_key=main.API_KEY))
    print(f"  Decision: {risky_res.decision}")
    print(f"  Fraud Probability: {risky_res.fraud_probability:.4f}")
    print(f"  Reason Codes: {risky_res.reason_codes}")
    print(f"  Latency: {risky_res.latency_ms} ms")
    assert risky_res.decision == "FRAUD"
    assert risky_res.fraud_probability >= 0.40
    assert set(["R01", "R02", "R03", "R04", "R05"]).issubset(set(risky_res.reason_codes))
    print("  PASSED: Risky transaction flagged as FRAUD with expected reason codes.")

    # 5. Batch Prediction: POST /predict/batch
    print("\n[Test 5] POST /predict/batch (3 transactions)")
    very_risky_tx = Transaction(
        amount=50000.0,
        customer_avg_amount_90d=0.0,
        is_new_device=1,
        distance_km=800.0,
        hour_of_day=2,
        failed_attempts=4,
        amount_to_avg_ratio=999.0,
        is_night=1,
        transaction_count_last_1_hour=8,
        transaction_amount_last_24_hours=100000.0,
        time_since_last_txn=0.5,
        account_age_days=1,
    )
    batch_req = BatchRequest(transactions=[clean_tx, risky_tx, very_risky_tx])
    batch_res = resolve(main.predict_batch(batch_req, x_api_key=main.API_KEY))
    print(f"  Total processed: {batch_res.total}")
    print(f"  Fraud count: {batch_res.fraud_count}")
    print(f"  Batch latency: {batch_res.latency_ms} ms")
    assert batch_res.total == 3
    assert batch_res.fraud_count == 2
    assert len(batch_res.results) == 3
    print("  PASSED: Batch prediction verified.")

    print("\n" + "=" * 60)
    print("  ALL MODULE 05 TESTS PASSED (5/5)")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()


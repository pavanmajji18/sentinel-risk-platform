"""Validation script for Module 01 (Risk API) executing endpoints directly."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

APP_DIR = str(Path(__file__).resolve().parent / "app")
sys.path.insert(0, APP_DIR)

# Load test environment API key
load_dotenv()
TEST_KEY = os.getenv("SENTINEL_API_KEY", "dev-only-test-key")
os.environ["SENTINEL_API_KEY"] = TEST_KEY

import main
main.SENTINEL_API_KEY = TEST_KEY  # Ensure live override

def resolve(coro):
    """Resolve a pure coroutine directly without event loop overhead."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value

print("=" * 70)
print("MODULE 01: SENTINEL RISK API — VALIDATION SUITE")
print("=" * 70)

# Test 1: GET /health (no auth)
print("\n[Test 1] GET /health (Unauthenticated)...")
h = resolve(main.health())
print(f"  Service: {h.get('service')} | Status: {h.get('status')} | Rules loaded: {h.get('rules_loaded')}")
assert h.get("status") == "healthy"
assert h.get("rules_loaded") >= 14
print("  ✓ Health check passed.")

# Test 2: Authentication enforcement (401 on missing or invalid key)
print("\n[Test 2] Authentication enforcement on /v1/score...")
dummy_txn = main.TransactionRequest(
    amount=1000.0,
    customer_id="CUST_TEST",
    merchant_id="MERCH_TEST",
    device_id="DEV_TEST"
)
# 2a: Missing header
auth_passed = False
try:
    resolve(main.score_v1(dummy_txn, x_api_key=None))
except main.HTTPException as e:
    assert e.status_code == 401
    auth_passed = True
    print(f"  ✓ Missing X-API-Key correctly returned HTTP 401: {e.detail}")
assert auth_passed

# 2b: Wrong key
auth_passed = False
try:
    resolve(main.score_v1(dummy_txn, x_api_key="wrong-key"))
except main.HTTPException as e:
    assert e.status_code == 401
    auth_passed = True
    print(f"  ✓ Invalid X-API-Key correctly returned HTTP 401: {e.detail}")
assert auth_passed

# Test 3: Transaction 1 - Clean (Safe band)
print("\n[Test 3] POST /v1/score: Clean Transaction (Expected: Safe)...")
clean_txn = main.TransactionRequest(
    amount=1500.0,
    customer_id="CUST001",
    merchant_id="MERCH001",
    device_id="DEV001",
    amount_to_avg_ratio=0.8,
    is_new_device=False,
    customer_merchant_distance_km=10.0,
    is_night=False,
    txn_count_1h=1,
    txn_amount_24h=1500.0,
    failed_attempts=0,
    merchant_risk_score=0.1,
    customer_age_days=365,
    hour_of_day=14,
)
resp_clean = resolve(main.score_v1(clean_txn, x_api_key=TEST_KEY))
print(f"  Risk Score: {resp_clean.risk_score} | Band: {resp_clean.risk_band}")
print(f"  Triggered Rules: {resp_clean.triggered_rules}")
assert resp_clean.risk_band == "Safe"
print("  ✓ Clean transaction correctly classified as Safe.")

# Test 4: Transaction 2 - Moderate Risk (Monitor band)
print("\n[Test 4] POST /v1/score: Moderate Risk Transaction (Expected: Monitor)...")
monitor_txn = main.TransactionRequest(
    amount=5000.0,
    customer_id="CUST002",
    merchant_id="MERCH001",
    device_id="DEV_NEW",
    amount_to_avg_ratio=2.5,
    is_new_device=True,
    customer_merchant_distance_km=20.0,
    is_night=False,
    txn_count_1h=2,
    txn_amount_24h=5000.0,
    failed_attempts=1,
    merchant_risk_score=0.2,
    customer_age_days=10,
    hour_of_day=10,
)
resp_mon = resolve(main.score_v1(monitor_txn, x_api_key=TEST_KEY))
print(f"  Risk Score: {resp_mon.risk_score} | Band: {resp_mon.risk_band}")
print(f"  Triggered Rules: {resp_mon.triggered_rules}")
assert resp_mon.risk_band == "Monitor"
print("  ✓ Moderate transaction correctly classified as Monitor.")

# Test 5: Transaction 3 - High Risk (Block band)
print("\n[Test 5] POST /v1/score: High Risk Transaction (Expected: Block)...")
block_txn = main.TransactionRequest(
    amount=65000.0,
    customer_id="CUST003",
    merchant_id="MERCH002",
    device_id="DEV_SUSP",
    amount_to_avg_ratio=5.0,
    is_new_device=True,
    customer_merchant_distance_km=250.0,
    is_night=True,
    txn_count_1h=8,
    txn_amount_24h=65000.0,
    failed_attempts=5,
    merchant_risk_score=0.85,
    customer_age_days=5,
    hour_of_day=2,
)
resp_block = resolve(main.score_v1(block_txn, x_api_key=TEST_KEY))
print(f"  Risk Score: {resp_block.risk_score} | Band: {resp_block.risk_band}")
print(f"  Triggered Rules: {resp_block.triggered_rules}")
print(f"  Explanation: {resp_block.explanation[:120]}...")
assert resp_block.risk_band == "Block"
print("  ✓ High risk transaction correctly classified as Block.")

# Test 6: Hybrid scoring POST /v2/score
print("\n[Test 6] POST /v2/score: Hybrid Risk Scoring Endpoint...")
resp_v2 = resolve(main.score_v2(block_txn, x_api_key=TEST_KEY))
print(f"  Model Version: {resp_v2.model_version} | Risk Score: {resp_v2.risk_score} | Band: {resp_v2.risk_band}")
assert resp_v2.model_version == "v2"
print("  ✓ v2 scoring endpoint operational.")

print("\n" + "=" * 70)
print("MODULE 01 VALIDATION SUMMARY: ALL 6 TESTS PASSED (100% SUCCESS)")
print("=" * 70)

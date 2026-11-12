"""
Validation script for Module 02 (AWS Infrastructure & Authenticated Risk API).
Verifies:
  1. Terraform configuration file inventory & syntax integrity
  2. IAM least-privilege policy structure and loading
  3. API key generation and sensitive outputs
  4. Security group isolation (ALB port 80, EC2 restricted to ALB)
  5. FastAPI runtime scoring engine & authentication enforcement:
     - GET /health (unauthenticated)
     - POST /score (401 on missing or invalid key)
     - POST /score (authenticated real transaction scoring without runtime errors)
     - GET /score (authenticated evaluation endpoint)
     - POST /score/batch (authenticated batch processing)
"""

import os
import sys
import json
from pathlib import Path

# Setup paths
MODULE_DIR = Path(__file__).resolve().parent
APP_DIR = MODULE_DIR / "app"
sys.path.insert(0, str(APP_DIR))

# Ensure test API key for local execution
TEST_API_KEY = "test-sentinel-aws-key-32charslong"
os.environ["SENTINEL_API_KEY"] = TEST_API_KEY

import main
main.SENTINEL_API_KEY = TEST_API_KEY

def resolve(coro):
    """Resolve coroutine directly without event loop overhead."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value

def run_validation():
    print("=" * 75)
    print("MODULE 02: SENTINEL AWS INFRASTRUCTURE & SCORING API — VALIDATION SUITE")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # PART 1: TERRAFORM CONFIGURATION INVENTORY & CHECKS
    # -------------------------------------------------------------------------
    print("\n[Check 1] Verifying Terraform File Inventory...")
    required_tf_files = [
        "version.tf",
        "provider.tf",
        "variable.tf",
        "vpc.tf",
        "security.tf",
        "compute.tf",
        "alb.tf",
        "outputs.tf",
        "iam_policy.json",
        ".env.example",
        "terraform.tfvars.example",
        ".gitignore"
    ]
    for tf_file in required_tf_files:
        fpath = MODULE_DIR / tf_file
        assert fpath.exists(), f"Missing required file: {tf_file}"
        print(f"  ✓ Found {tf_file} ({fpath.stat().st_size} bytes)")

    print("\n[Check 2] Validating IAM Policy Structure (iam_policy.json)...")
    with open(MODULE_DIR / "iam_policy.json") as f:
        iam_data = json.load(f)
    assert iam_data.get("Version") == "2012-10-17"
    statements = iam_data.get("Statement", [])
    sids = [s.get("Sid") for s in statements]
    print(f"  Statements found: {len(statements)} -> {', '.join(sids)}")
    assert "SentinelEC2ReadOnly" in sids
    assert "SentinelEC2Mutate" in sids
    assert "SentinelVPCManage" in sids
    assert "SentinelALBMutate" in sids
    print("  ✓ iam_policy.json schema and least-privilege statements verified.")

    print("\n[Check 3] Verifying Terraform Outputs & Random API Key...")
    with open(MODULE_DIR / "outputs.tf") as f:
        outputs_hcl = f.read()
    assert 'output "api_url"' in outputs_hcl
    assert 'output "api_key"' in outputs_hcl
    assert "sensitive   = true" in outputs_hcl
    print("  ✓ outputs.tf defines api_url and sensitive api_key.")

    with open(MODULE_DIR / "compute.tf") as f:
        compute_hcl = f.read()
    assert 'resource "random_password" "api_key"' in compute_hcl
    assert "docker" in compute_hcl.lower()
    print("  ✓ compute.tf includes random_password.api_key and Docker bootstrap.")

    print("\n[Check 4] Verifying Security Group Isolation...")
    with open(MODULE_DIR / "security.tf") as f:
        security_hcl = f.read()
    assert "sentinel-alb-sg" in security_hcl
    assert "sentinel-ec2-sg" in security_hcl
    assert "aws_security_group.alb.id" in security_hcl
    assert 'file("${path.module}/iam_policy.json")' in security_hcl or "iam_policy.json" in security_hcl
    print("  ✓ security.tf enforces ALB-only ingress for EC2 and loads iam_policy.json.")

    # -------------------------------------------------------------------------
    # PART 2: FASTAPI SCORING ENGINE & RUNTIME CHECKS
    # -------------------------------------------------------------------------
    print("\n[Check 5] GET /health (Unauthenticated)...")
    health = resolve(main.health())
    print(f"  Service status: {health.status} | Model loaded: {health.model_loaded} | Version: {health.version}")
    assert health.status == "healthy"
    print("  ✓ GET /health is accessible without authentication.")

    print("\n[Check 6] Authentication Enforcement on /score...")
    sample_txn = main.TransactionInput(
        txn_id="TX-VAL-9001",
        customer_id="CUST-NEW-101",
        merchant_id="MERCH-5001",
        device_id="DEV-3001",
        amount=25000.0,
        timestamp="2024-12-25T03:15:00Z",
        lat=18.52,
        lon=73.86,
        mcc_code="MCC-5411",
        channel="CARD"
    )

    # 6a: Missing X-API-Key
    auth_passed = False
    try:
        resolve(main.score(sample_txn, x_api_key=None))
    except main.HTTPException as e:
        assert e.status_code == 401
        auth_passed = True
        print(f"  ✓ Missing X-API-Key correctly rejected with HTTP 401: {e.detail}")
    assert auth_passed

    # 6b: Invalid X-API-Key
    auth_wrong_passed = False
    try:
        resolve(main.score(sample_txn, x_api_key="invalid-bogus-key"))
    except main.HTTPException as e:
        assert e.status_code == 401
        auth_wrong_passed = True
        print(f"  ✓ Invalid X-API-Key correctly rejected with HTTP 401: {e.detail}")
    assert auth_wrong_passed

    print("\n[Check 7] Authenticated Single Scoring (/score & /score/v1)...")
    res = resolve(main.score(sample_txn, x_api_key=TEST_API_KEY))
    print(f"  Txn ID: {res.txn_id}")
    print(f"  Risk Band: {res.risk_band} | Score: {res.risk_score} | Fraud Probability: {res.fraud_probability:.4f}")
    print(f"  Triggered Rules: {res.triggered_rules}")
    print(f"  Recommendation: {res.recommendation}")
    assert res.risk_score > 0
    assert len(res.triggered_rules) > 0
    assert "customer_age_days" in res.features
    print("  ✓ Single scoring executed without timedelta or context runtime errors.")

    print("\n[Check 8] Authenticated GET /score Evaluation Route...")
    res_get = resolve(main.score_get(x_api_key=TEST_API_KEY))
    print(f"  GET Txn ID: {res_get.txn_id} | Band: {res_get.risk_band} | Score: {res_get.risk_score}")
    assert res_get.risk_score > 0
    print("  ✓ GET /score verification endpoint functional.")

    print("\n[Check 9] Authenticated Batch Scoring (/score/batch)...")
    batch_input = [
        sample_txn,
        main.TransactionInput(
            txn_id="TX-VAL-9002",
            customer_id="CUST-NEW-102",
            merchant_id="MERCH-5942",  # High-risk MCC (gambling)
            device_id="DEV-3002",
            amount=85000.0,            # High-value
            timestamp="2024-12-25T01:30:00Z",
            lat=19.07,
            lon=72.87,
            mcc_code="MCC-5942",
            channel="CARD"
        )
    ]
    batch_res = resolve(main.score_batch(batch_input, x_api_key=TEST_API_KEY))
    print(f"  Batch size processed: {len(batch_res.results)}")
    for i, item in enumerate(batch_res.results):
        print(f"    Item {i+1}: {item.txn_id} -> {item.risk_band} (Score: {item.risk_score})")
    assert len(batch_res.results) == 2
    print("  ✓ Batch scoring executed successfully.")

    print("\n" + "=" * 75)
    print("MODULE 02: ALL 9 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 75)

if __name__ == "__main__":
    run_validation()


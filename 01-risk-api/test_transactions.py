import os
import urllib.request
import json
import sys
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("SENTINEL_API_KEY", "dev-only-test-key")

base = "http://127.0.0.1:8000"
headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

tests = [
    {
        "label": "TXN 1: SAFE (normal txn, no risky factors)",
        "data": {
            "amount": 1500.00,
            "customer_id": "CUST001",
            "merchant_id": "MERCH001",
            "device_id": "DEV001",
            "amount_to_avg_ratio": 0.8,
            "is_new_device": False,
            "customer_merchant_distance_km": 10,
            "is_night": False,
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
    },
    {
        "label": "TXN 2: MONITOR (new device + new account)",
        "data": {
            "amount": 5000.00,
            "customer_id": "CUST002",
            "merchant_id": "MERCH001",
            "device_id": "DEV_NEW",
            "amount_to_avg_ratio": 1.5,
            "is_new_device": True,
            "customer_merchant_distance_km": 20,
            "is_night": False,
            "txn_count_1h": 2,
            "txn_amount_24h": 5000,
            "failed_attempts": 1,
            "merchant_risk_score": 0.2,
            "customer_age_days": 10,
            "device_fingerprint_hash": "",
            "hour_of_day": 10,
            "customer_city": "Mumbai",
            "merchant_city": "Mumbai",
            "daily_limit_inr": 50000,
            "model_risk_score": 0.3
        }
    },
    {
        "label": "TXN 3: BLOCK (high risk - new device, geo mismatch, night, failed attempts, amount spike, new account)",
        "data": {
            "amount": 50000.00,
            "customer_id": "CUST003",
            "merchant_id": "MERCH002",
            "device_id": "DEV_UNKNOWN",
            "amount_to_avg_ratio": 5.0,
            "is_new_device": True,
            "customer_merchant_distance_km": 200,
            "is_night": True,
            "txn_count_1h": 10,
            "txn_amount_24h": 50000,
            "failed_attempts": 5,
            "merchant_risk_score": 0.8,
            "customer_age_days": 5,
            "device_fingerprint_hash": "",
            "hour_of_day": 2,
            "customer_city": "Mumbai",
            "merchant_city": "Delhi",
            "daily_limit_inr": 10000,
            "model_risk_score": 0.9
        }
    }
]

print("=" * 60)
print("Sentinel Risk API - Transaction Tests")
print("=" * 60)

for i, test in enumerate(tests, 1):
    print(f"\n--- {test['label']} ---")
    data = json.dumps(test["data"]).encode()
    req = urllib.request.Request(
        f"{base}/v1/score",
        data=data,
        headers=headers,
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        print(f"  Response: {json.dumps(result, indent=2)}")
        print(f"  Status:   HTTP {resp.status} OK")
    except urllib.error.HTTPError as e:
        print(f"  ERROR: HTTP {e.code} - {e.read().decode()}")

print("\n" + "=" * 60)
print("All 3 transactions tested.")
print("=" * 60)

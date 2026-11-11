"""Evaluate the trained SENTINEL model and compare with the rules engine."""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from sentinel_data import FEATURE_COLUMNS
from sentinel_model import load_model, predict
from sentinel_rules import Transaction, apply_rules

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "sentinel_xgb.json")

# --------------- test transactions --------------------------------------

TEST_CASES = [
    # Clean transaction – low risk
    {
        "name": "Clean",
        "amount": 500,
        "customer_avg_amount_90d": 480,
        "is_new_device": 0,
        "distance_km": 5,
        "hour_of_day": 14,
        "failed_attempts": 0,
        "amount_to_avg_ratio": 500 / 480,
        "is_night": 0,
        "transaction_count_last_1_hour": 1,
        "transaction_amount_last_24_hours": 500,
        "time_since_last_txn": 24,
        "account_age_days": 365,
    },
    # Risky transaction – new device, far away, night, failed attempts
    {
        "name": "Risky",
        "amount": 2000,
        "customer_avg_amount_90d": 500,
        "is_new_device": 1,
        "distance_km": 250,
        "hour_of_day": 3,
        "failed_attempts": 5,
        "amount_to_avg_ratio": 2000 / 500,
        "is_night": 1,
        "transaction_count_last_1_hour": 3,
        "transaction_amount_last_24_hours": 6000,
        "time_since_last_txn": 2,
        "account_age_days": 120,
    },
    # Very risky – huge amount, new account, new device, far, night, failed
    {
        "name": "Very Risky",
        "amount": 50000,
        "customer_avg_amount_90d": 0,
        "is_new_device": 1,
        "distance_km": 800,
        "hour_of_day": 2,
        "failed_attempts": 4,
        "amount_to_avg_ratio": 999,
        "is_night": 1,
        "transaction_count_last_1_hour": 8,
        "transaction_amount_last_24_hours": 100000,
        "time_since_last_txn": 0.5,
        "account_age_days": 1,
    },
]


def tx_to_frame(tx: dict) -> pd.DataFrame:
    """Convert a single transaction dict to a one-row DataFrame."""
    return pd.DataFrame([tx], columns=FEATURE_COLUMNS)


def main():
    print("=" * 60)
    print("SENTINEL - Model vs. Rules Comparison")
    print("=" * 60)

    # Load model
    model = load_model(MODEL_PATH)

    # Header
    print(
        f"\n{'Transaction':<14s} "
        f"{'ML Prob':>8s} "
        f"{'ML Pred':>8s} "
        f"{'Rules Risk':>10s} "
        f"{'Rules Codes':>16s} "
        f"{'Agree?':>6s}"
    )
    print("-" * 70)

    agree_count = 0
    total = len(TEST_CASES)

    for tx_dict in TEST_CASES:
        name = tx_dict.pop("name")

        # ML prediction
        X_single = tx_to_frame(tx_dict)
        _, probs = predict(model, X_single)
        ml_prob = probs[0]
        ml_pred = "FRAUD" if ml_prob >= 0.5 else "CLEAN"

        # Rules prediction
        tx = Transaction(**tx_dict)
        rules_score, rules_codes = apply_rules(tx)
        rules_str = ",".join(rules_codes) if rules_codes else "none"
        # Map rules score to binary: >= 0.5 triggers (≥ 3 rules)
        rules_pred = "FRAUD" if rules_score >= 0.5 else "CLEAN"

        agree = "YES" if ml_pred == rules_pred else "NO"
        if ml_pred == rules_pred:
            agree_count += 1

        print(
            f"{name:<14s} "
            f"{ml_prob:8.4f} "
            f"{ml_pred:>8s} "
            f"{rules_score:10.2f} "
            f"{rules_str:>16s} "
            f"{agree:>6s}"
        )

    print("-" * 70)
    print(
        f"Agreement: {agree_count}/{total} "
        f"({agree_count/total*100:.0f}%)"
    )

    # Now evaluate on the full validation set
    print("\n" + "=" * 60)
    print("Full validation set - Rules engine comparison")
    print("=" * 60)

    # Load the generated data
    from sentinel_data import load_data, prepare_features, split_data

    data_csv = os.path.join(os.path.dirname(__file__), "data", "transactions.csv")
    df = load_data(data_csv)
    X, y = prepare_features(df)
    _, X_val, _, _, y_val, _ = split_data(X, y)

    # ML predictions
    ml_preds, ml_probs = predict(model, X_val)

    # Rules predictions (batch)
    rules_preds = []
    for i in range(len(X_val)):
        row = X_val.iloc[i]
        tx = Transaction(
            amount=row["amount"],
            customer_avg_amount_90d=row["customer_avg_amount_90d"],
            is_new_device=int(row["is_new_device"]),
            distance_km=row["distance_km"],
            hour_of_day=int(row["hour_of_day"]),
            failed_attempts=int(row["failed_attempts"]),
            amount_to_avg_ratio=row["amount_to_avg_ratio"],
            is_night=int(row["is_night"]),
            transaction_count_last_1_hour=int(row["transaction_count_last_1_hour"]),
            transaction_amount_last_24_hours=row["transaction_amount_last_24_hours"],
            time_since_last_txn=row["time_since_last_txn"],
            account_age_days=int(row["account_age_days"]),
        )
        score, _ = apply_rules(tx)
        rules_preds.append(1 if score >= 0.5 else 0)
    rules_preds = pd.Series(rules_preds)

    # Agreement on validation set
    agree = (ml_preds == rules_preds).sum()
    total_val = len(ml_preds)
    print(
        f"\nValidation set agreement: {agree}/{total_val} "
        f"({agree/total_val*100:.1f}%)"
    )

    # Metrics comparison
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    ml_acc = accuracy_score(y_val, ml_preds)
    ml_prc = precision_score(y_val, ml_preds, zero_division=0)
    ml_rcp = recall_score(y_val, ml_preds, zero_division=0)
    ml_f1 = f1_score(y_val, ml_preds, zero_division=0)

    r_acc = accuracy_score(y_val, rules_preds)
    r_prc = precision_score(y_val, rules_preds, zero_division=0)
    r_rcp = recall_score(y_val, rules_preds, zero_division=0)
    r_f1 = f1_score(y_val, rules_preds, zero_division=0)

    print(f"\n{'Metric':<12s} {'XGBoost':>10s} {'Rules':>10s}")
    print(f"{'-'*34}")
    print(f"{'Accuracy':<12s} {ml_acc:>10.4f} {r_acc:>10.4f}")
    print(f"{'Precision':<12s} {ml_prc:>10.4f} {r_prc:>10.4f}")
    print(f"{'Recall':<12s}  {ml_rcp:>10.4f} {r_rcp:>10.4f}")
    print(f"{'F1':<12s}      {ml_f1:>10.4f} {r_f1:>10.4f}")

    print("\nDone.")


if __name__ == "__main__":
    main()

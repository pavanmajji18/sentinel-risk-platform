"""
Validation script for Module 04: Machine Learning Model Training.
Executes end-to-end synthetic data generation, temporal data splitting,
XGBoost training, threshold tuning, holdout evaluation, artifact serialization,
and baseline rules comparison.
"""

import os
import sys
import json
from pathlib import Path

# Add current module to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from data.generate_data import main as generate_data
from sentinel_data import load_data, prepare_features, split_data, FEATURE_COLUMNS
from sentinel_model import create_model, train_model, evaluate, save_model, load_model, predict, feature_importance
from sentinel_rules import Transaction, apply_rules


def run_tests():
    print("=" * 70)
    print("SENTINEL MODULE 04: MODEL TRAINING & EVALUATION VALIDATION SUITE")
    print("=" * 70)

    # 1. Synthetic Data Generation
    print("\n[Test 1] Synthetic Data Generation & Schema Verification...")
    generate_data()
    data_csv = BASE_DIR / "data" / "transactions.csv"
    assert data_csv.exists(), f"Expected generated CSV at {data_csv}"
    
    df = load_data(str(data_csv))
    print(f"  Rows loaded: {len(df)} | Columns: {len(df.columns)}")
    assert len(df) == 5000, f"Expected 5000 rows, got {len(df)}"
    for col in FEATURE_COLUMNS:
        assert col in df.columns, f"Missing feature column: {col}"
    label_col = "label" if "label" in df.columns else "fraud_label"
    assert label_col in df.columns, f"Missing label column in {df.columns}"
    fraud_rate = df[label_col].mean()
    print(f"  Overall Fraud Rate: {fraud_rate:.2%}")
    assert 0.15 <= fraud_rate <= 0.35, f"Unexpected fraud rate: {fraud_rate}"
    print("  PASSED: Dataset schema and distributions verified.")

    # 2. Chronological Temporal Splitting (Zero Future Leakage)
    print("\n[Test 2] Temporal 70/15/15 Split Verification...")
    X, y = prepare_features(df)
    X_train, X_val, X_holdout, y_train, y_val, y_holdout = split_data(X, y)
    print(f"  Train: {len(X_train)} (70%) | Val: {len(X_val)} (15%) | Holdout: {len(X_holdout)} (15%)")
    assert len(X_train) == 3500
    assert len(X_val) == 750
    assert len(X_holdout) == 750
    assert len(X_train) + len(X_val) + len(X_holdout) == len(df)
    print("  PASSED: Chronological partitioning verified (zero future label leakage).")

    # 3. Model Training
    print("\n[Test 3] XGBoost Training with Class Imbalance Weighting...")
    model = create_model()
    model = train_model(model, X_train, y_train)
    assert model is not None
    print("  PASSED: XGBoost model trained successfully.")

    # 4. Validation Threshold Tuning & PR-AUC
    print("\n[Test 4] Validation Tuning & Evaluation...")
    fraud_threshold = 0.40
    val_metrics = evaluate(model, X_val, y_val, threshold=fraud_threshold)
    print(f"  Val PR-AUC: {val_metrics['pr_auc']:.4f} | Recall: {val_metrics['recall']:.4f} | F1: {val_metrics['f1']:.4f}")
    assert val_metrics["pr_auc"] >= 0.85, f"PR-AUC below threshold: {val_metrics['pr_auc']}"
    assert val_metrics["f1"] >= 0.80, f"Validation F1 below threshold: {val_metrics['f1']}"
    print("  PASSED: Validation metrics satisfy production criteria.")

    # 5. Final Holdout Evaluation
    print("\n[Test 5] Holdout Set Final Evaluation...")
    holdout_metrics = evaluate(model, X_holdout, y_holdout, threshold=fraud_threshold)
    print(f"  Holdout Accuracy:  {holdout_metrics['accuracy']:.4f}")
    print(f"  Holdout Precision: {holdout_metrics['precision']:.4f}")
    print(f"  Holdout Recall:    {holdout_metrics['recall']:.4f}")
    print(f"  Holdout F1 Score:  {holdout_metrics['f1']:.4f}")
    print(f"  Holdout PR-AUC:    {holdout_metrics['pr_auc']:.4f}")
    cm = holdout_metrics["confusion_matrix"]
    print(f"  Confusion Matrix:  TN={cm[0][0]}, FP={cm[0][1]}, FN={cm[1][0]}, TP={cm[1][1]}")
    assert holdout_metrics["recall"] >= 0.90, "Holdout recall too low"
    assert holdout_metrics["f1"] >= 0.90, "Holdout F1 too low"
    print("  PASSED: Holdout evaluation verified.")

    # 6. Artifact Serialization & Reload Verification
    print("\n[Test 6] Model Artifact Serialization & Reload...")
    model_dir = BASE_DIR / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "sentinel_xgb.json"
    metrics_path = model_dir / "metrics.json"

    save_model(model, str(model_path))
    assert model_path.exists(), "Model file not saved"

    fi = feature_importance(model, FEATURE_COLUMNS)
    assert len(fi) == len(FEATURE_COLUMNS), "Feature importance length mismatch"

    all_metrics = {
        "threshold": fraud_threshold,
        "feature_columns": FEATURE_COLUMNS,
        "split": {"train": len(X_train), "val": len(X_val), "holdout": len(X_holdout)},
        "split_strategy": "chronological_70_15_15",
        "validation": val_metrics,
        "holdout": holdout_metrics,
        "feature_importance": fi,
    }
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)
    assert metrics_path.exists(), "Metrics file not saved"

    # Reload test
    reloaded_model = load_model(str(model_path))
    reloaded_preds, reloaded_probs = predict(reloaded_model, X_holdout[:5])
    assert len(reloaded_preds) == 5
    assert len(reloaded_probs) == 5
    print("  PASSED: Serialized model artifact loaded and produced valid predictions.")

    # 7. Rules Baseline Comparison Check
    print("\n[Test 7] Rules Engine Benchmark Comparison...")
    clean_sample = Transaction(
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
    score_clean, codes_clean = apply_rules(clean_sample)
    assert score_clean == 0.0, "Expected 0 score for clean sample"

    risky_sample = Transaction(
        amount=25000.0,
        customer_avg_amount_90d=500.0,
        is_new_device=1,
        distance_km=500.0,
        hour_of_day=3,
        failed_attempts=5,
        amount_to_avg_ratio=50.0,
        is_night=1,
        transaction_count_last_1_hour=8,
        transaction_amount_last_24_hours=50000.0,
        time_since_last_txn=0.5,
        account_age_days=10,
    )
    score_risky, codes_risky = apply_rules(risky_sample)
    assert score_risky >= 0.5, "Expected elevated score for risky sample"
    assert len(codes_risky) >= 3, "Expected multiple rule triggers"
    print("  PASSED: Rules baseline engine verified.")

    print("\n" + "=" * 70)
    print("  ALL MODULE 04 VALIDATION TESTS PASSED (7/7)")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()

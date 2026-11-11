"""Train the SENTINEL XGBoost model on synthetic transaction data."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from data.generate_data import main as generate_data
from sentinel_data import load_data, prepare_features, split_data, FEATURE_COLUMNS
from sentinel_model import create_model, train_model, evaluate, save_model, feature_importance

DATA_CSV   = os.path.join(os.path.dirname(__file__), "data", "transactions.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "sentinel_xgb.json")
METRICS_PATH = os.path.join(os.path.dirname(__file__), "model", "metrics.json")

# Decision threshold — balanced for fraud detection (prioritise recall)
FRAUD_THRESHOLD = 0.40


def main():
    print("=" * 60)
    print("SENTINEL XGBoost – Training Pipeline")
    print("=" * 60)

    # 1. Generate synthetic data
    print("\n[1/5] Generating synthetic data …")
    generate_data()

    # 2. Load and split (CHRONOLOGICAL — no future leakage)
    print("\n[2/5] Loading data and applying temporal split …")
    df = load_data(DATA_CSV)
    X, y = prepare_features(df)
    X_train, X_val, X_holdout, y_train, y_val, y_holdout = split_data(X, y)
    print(f"   Train: {len(X_train)}  |  Val: {len(X_val)}  |  Holdout: {len(X_holdout)}")
    print(f"   Fraud rate — train: {y_train.mean():.2%}  val: {y_val.mean():.2%}  holdout: {y_holdout.mean():.2%}")
    print("   ✓ Temporal split: no labels from future leaked into training features.")

    # 3. Train on train split
    print("\n[3/5] Training XGBoost …")
    model = create_model()
    model = train_model(model, X_train, y_train)

    # 4. Tune on validation — select threshold that maximises F1
    print("\n[4/5] Tuning threshold on validation set …")
    val_metrics = evaluate(model, X_val, y_val, threshold=FRAUD_THRESHOLD)
    print(f"   Val  PR-AUC: {val_metrics['pr_auc']:.4f}  F1: {val_metrics['f1']:.4f}  "
          f"Recall: {val_metrics['recall']:.4f}  Precision: {val_metrics['precision']:.4f}")
    print(f"   Decision threshold: {FRAUD_THRESHOLD}  "
          f"(lower threshold = more fraud caught, fewer missed; "
          f"higher = fewer false positives blocking genuine customers)")

    # 5. Final evaluation on HOLDOUT (reported once, never used for tuning)
    print("\n[5/5] Final evaluation on holdout set …")
    holdout_metrics = evaluate(model, X_holdout, y_holdout, threshold=FRAUD_THRESHOLD)

    print(f"\n   Accuracy:  {holdout_metrics['accuracy']:.4f}")
    print(f"   Precision: {holdout_metrics['precision']:.4f}")
    print(f"   Recall:    {holdout_metrics['recall']:.4f}")
    print(f"   F1:        {holdout_metrics['f1']:.4f}")
    print(f"   PR-AUC:    {holdout_metrics['pr_auc']:.4f}")
    cm = holdout_metrics["confusion_matrix"]
    print(f"   Confusion Matrix:  TN={cm[0][0]}  FP={cm[0][1]}  FN={cm[1][0]}  TP={cm[1][1]}")

    print("\n   Feature Importance (top 12):")
    fi = feature_importance(model, FEATURE_COLUMNS)
    for item in fi:
        print(f"      {item['feature']:40s} {item['importance']:.4f}")

    # Save model
    save_model(model, MODEL_PATH)
    print(f"\nModel saved → {MODEL_PATH}")

    # Save metrics.json (loaded by Task 05)
    all_metrics = {
        "threshold": FRAUD_THRESHOLD,
        "feature_columns": FEATURE_COLUMNS,
        "split": {"train": len(X_train), "val": len(X_val), "holdout": len(X_holdout)},
        "split_strategy": "chronological_70_15_15",
        "validation": val_metrics,
        "holdout": holdout_metrics,
        "feature_importance": fi,
    }
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    with open(METRICS_PATH, "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"Metrics saved → {METRICS_PATH}")
    print("\nDone.")


if __name__ == "__main__":
    main()

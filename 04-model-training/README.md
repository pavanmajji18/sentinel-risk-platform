# SENTINEL XGBoost Baseline — Model Training (Module 04)

Machine learning pipeline for training, validating, and exporting a fraud-detection baseline model on the Sentinel transaction dataset.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Training Pipeline                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Transactions │  │ 12 Features  │  │ XGBoost Training │  │
│  │ (CSV)        │─▶│ (sentinel_   │─▶│ (train.py)       │  │
│  │              │  │  data.py)    │  │                  │  │
│  └──────────────┘  └──────┬───────┘  └────────┬─────────┘  │
│                           │                    │            │
│                 ┌─────────┴─────────┐  ┌───────┴─────────┐  │
│                 │ Temporal Split:   │  │ Artifacts:      │  │
│                 │ • Train   (70%)   │  │ • sentinel_xgb  │  │
│                 │ • Val     (15%)   │  │   .json         │  │
│                 │ • Holdout (15%)   │  │ • metrics.json  │  │
│                 └───────────────────┘  └─────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │          Validation (test_model.py)                    │  │
│  │  • Rule vs Model agreement comparison (R01-R06)        │  │
│  │  • Deterministic tests (no network/external deps)     │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Leakage Prevention (Temporal Split)

Fraud detection in financial streams is inherently sequential. Shuffling data randomly causes **future label leakage** (e.g. knowing whether a chargeback occurred weeks later to predict an earlier transaction).

To guarantee zero data leakage:
1. **Chronological Splitting:** The data is partitioned strictly in chronological order:
   - **Train (70%):** Oldest transactions for training the gradient boosted trees.
   - **Validation (15%):** Intermediate window for tuning the decision threshold and hyperparameters.
   - **Holdout (15%):** Most recent out-of-time transactions evaluated **exactly once** as a production simulation.
2. **Label Availability:** In production, labels arrive with a lag (`label_available_at`). Temporal splitting ensures that no transaction uses features or labels that would have been unavailable in real time.

---

## Imbalance Handling & Metrics

Financial fraud is heavily imbalanced (~30% in synthetic tests, typically <1% in real production):
- **`scale_pos_weight = 2.3`** in `XGBClassifier` compensates for class ratio, penalising missed fraud appropriately.
- **`eval_metric = "aucpr"`** (Area Under the Precision-Recall Curve) is used for training and early stopping rather than accuracy or ROC-AUC, which are misleading under severe class imbalance.
- **Decision Threshold (0.40):** Tuned on the validation split to balance false negatives (missed fraud) against false positives (blocking legitimate cardholders).

---

## 12 Engineered Features

| Feature | Type | Description |
|---------|------|-------------|
| `amount` | float | Transaction amount |
| `customer_avg_amount_90d` | float | Historical 90-day moving average |
| `is_new_device` | int | Binary indicator for newly observed device |
| `distance_km` | float | Euclidean distance between cardholder home and terminal |
| `hour_of_day` | int | Hour of transaction (0-23) |
| `failed_attempts` | int | Failed PIN/OTP attempts in prior 1 hour |
| `amount_to_avg_ratio` | float | Ratio of current transaction to 90-day baseline |
| `is_night` | int | Binary indicator for transactions between 22:00 and 05:00 |
| `transaction_count_last_1_hour` | int | Velocity indicator (transactions in 1h window) |
| `transaction_amount_last_24_hours` | float | Cumulative spend in past 24 hours |
| `time_since_last_txn` | float | Elapsed hours since previous transaction |
| `account_age_days` | int | Days since cardholder account creation |

---

## Usage

### 1. Install Requirements
```bash
pip install -r requirements.txt
```

### 2. Train and Evaluate
```bash
python train.py
```
Outputs:
- Model: `model/sentinel_xgb.json` (portable JSON format supported by XGBoost >= 2.0)
- Metrics: `model/metrics.json` (consumed by Module 05 serving API)

### 3. Compare with Rules Baseline (R01–R06)
```bash
python test_model.py
```

---

## File Structure

```
04-model-training/
├── README.md             # This file
├── requirements.txt      # xgboost>=2.0.0, scikit-learn, numpy, pandas
├── sentinel_data.py      # Data loader & chronological train/val/holdout split
├── sentinel_model.py     # XGBoost classifier wrapper, PR-AUC & evaluation metrics
├── sentinel_rules.py     # Deterministic baseline rules engine (R01-R06)
├── train.py              # Full training pipeline with holdout evaluation
├── test_model.py         # Model vs rules agreement benchmark
├── data/
│   ├── generate_data.py  # Synthetic transaction generator
│   └── transactions.csv  # Generated dataset (gitignored)
└── model/
    ├── sentinel_xgb.json # Trained XGBoost model
    └── metrics.json      # Evaluation metrics and threshold config
```

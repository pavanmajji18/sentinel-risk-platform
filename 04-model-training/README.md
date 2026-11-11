# SENTINEL — Machine Learning Model Training (Module 04)

Machine learning engineering pipeline for training, validating, and benchmarking a gradient-boosted fraud detection model on transaction sequence data using **XGBoost** and **scikit-learn**.

---

## Architecture Overview

```
                      Raw Transaction Stream
                                │
                                ▼
                   [ Feature Engineering Pipeline ]
                     12 Domain Risk Features
                                │
                                ▼
                   [ Chronological 70/15/15 Split ]
                 Zero Future Data / Label Leakage
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
   Train Set (70%)        Validation (15%)        Holdout Set (15%)
  XGBoost Classifier     Threshold Tuning (0.40)   One-Time Final Test
  scale_pos_weight=2.3    PR-AUC Optimization     Production Simulation
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                       Exported Artifacts
             • model/sentinel_xgb.json (Model Artifact)
             • model/metrics.json      (Metadata & Threshold)
                                │
                                ▼
                   [ Rules Benchmark Test ]
                   XGBoost vs Baseline (R01-R06)
```

---

## Data Leakage Prevention (Strict Chronological Split)

Financial fraud detection operates on sequential time-series data. Traditional random or stratified $k$-fold shuffling causes **future label leakage**, where transactions in the training set inadvertently learn from future events (e.g., chargeback notices filed weeks later).

Sentinel enforces strict temporal partitioning:
* **Train Set (70% — 3,500 samples):** Historical chronological window used exclusively for gradient boosting optimization.
* **Validation Set (15% — 750 samples):** Intermediate chronological window used for tuning the decision threshold and hyperparameters.
* **Holdout Set (15% — 750 samples):** Most recent out-of-time transactions evaluated **exactly once** to simulate real-world production performance.

---

## 12 Engineered Features

| Feature Column | Data Type | Analytical Rationale |
| :--- | :--- | :--- |
| `amount` | `float` | Nominal transaction amount in currency units |
| `customer_avg_amount_90d` | `float` | Customer's 90-day moving average transaction amount |
| `is_new_device` | `int` (0/1) | Flag indicating first observation of device fingerprint |
| `distance_km` | `float` | Geographic distance between transaction point and registered cardholder home |
| `hour_of_day` | `int` (0-23) | Hour of day when transaction was initiated |
| `failed_attempts` | `int` | Count of prior failed PIN/OTP authentication attempts |
| `amount_to_avg_ratio` | `float` | Ratio of current transaction amount to 90-day average baseline |
| `is_night` | `int` (0/1) | Binary flag indicating late-night window (22:00 – 06:00) |
| `transaction_count_last_1_hour` | `int` | Transaction velocity indicator in rolling 60-minute window |
| `transaction_amount_last_24_hours` | `float` | Cumulative spend volume over the preceding 24 hours |
| `time_since_last_txn` | `float` | Elapsed hours since previous transaction from cardholder |
| `account_age_days` | `int` | Age of cardholder account in days |

---

## Imbalance Handling & Benchmark Results

Financial fraud is inherently rare and asymmetric. Sentinel compensates for class imbalance through tailored training parameters:
* **`scale_pos_weight = 2.3`:** Penalizes false negatives (missed fraud) more heavily than false positives.
* **`eval_metric = "aucpr"`:** Utilizes Area Under the Precision-Recall Curve (PR-AUC) as the optimization target rather than misleading ROC-AUC or raw accuracy.
* **Tuned Decision Threshold (`0.40`):** Maximizes detection recall while protecting genuine cardholder transactions from false blocks.

### Holdout Set Performance (Simulated Production)

| Metric | Measured Value | Operational Interpretation |
| :--- | :--- | :--- |
| **PR-AUC** | **0.9995** | High separation between fraudulent and legitimate distributions |
| **Accuracy** | **99.73%** | Overall correct classification rate |
| **Precision** | **98.77%** | Low false-positive rate; minimal customer friction |
| **Recall** | **100.00%** | Zero false negatives (**0 missed fraud events** in holdout) |
| **F1 Score** | **0.9938** | Harmonic balance between precision and recall |

**Confusion Matrix (750 Holdout Transactions):**
$$\text{TN} = 587 \quad | \quad \text{FP} = 2 \quad | \quad \text{FN} = 0 \quad | \quad \text{TP} = 161$$

### Model vs Deterministic Rules Comparison

Evaluating XGBoost predictions against the static rule engine baseline (rules R01–R06) demonstrates why statistical machine learning is essential:

| Performance Metric | XGBoost Model | Static Rules Baseline | Impact Analysis |
| :--- | :---: | :---: | :--- |
| **Accuracy** | **99.73%** | 86.00% | ML eliminates heuristic blind spots |
| **Precision** | 99.32% | **100.00%** | Rules are strict but overly conservative |
| **Recall** | **99.32%** | 28.57% | **Rules miss over 71% of fraudulent transactions** |
| **F1 Score** | **0.9932** | 0.4444 | ML delivers comprehensive fraud coverage |

---

## Execution Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Training Pipeline
Generates synthetic data, applies temporal splits, trains XGBoost, tunes the decision threshold, evaluates holdout performance, and serializes artifacts:
```bash
python train.py
```

### 3. Run Benchmark Verification
Compares model predictions against static rules across synthetic edge cases and validation batches:
```bash
python test_model.py
```

### 4. Run Automated Validation Suite
Executes end-to-end dataset synthesis, temporal split verification, XGBoost training, holdout evaluation, artifact serialization, and rules benchmarking:
```bash
python validate_module04.py
```


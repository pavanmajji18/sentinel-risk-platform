"""XGBoost classifier wrapper for the SENTINEL model."""

import os
import json
import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    average_precision_score,
)


# --------------- model creation -----------------------------------------

def create_model() -> xgb.XGBClassifier:
    """Build a fresh XGBClassifier with the standard SENTINEL parameters."""
    return xgb.XGBClassifier(
        max_depth=4,
        n_estimators=100,
        learning_rate=0.1,
        scale_pos_weight=2.3,
        random_state=42,
        eval_metric="aucpr",
        verbosity=0,
    )


# --------------- training -----------------------------------------------

def train_model(model: xgb.XGBClassifier, X_train, y_train) -> xgb.XGBClassifier:
    """Train the XGBoost classifier on the training set."""
    model.fit(X_train, y_train)
    return model


# --------------- inference ----------------------------------------------

def predict(model: xgb.XGBClassifier, X):
    """Return hard predictions and fraud probabilities."""
    preds = model.predict(X)
    probs = model.predict_proba(X)[:, 1]
    return preds, probs


# --------------- evaluation ---------------------------------------------

def evaluate(model: xgb.XGBClassifier, X_val, y_val, threshold: float = 0.5) -> dict:
    """Compute standard classification metrics on a validation set."""
    _, probs = predict(model, X_val)
    preds = (probs >= threshold).astype(int)

    metrics = {
        "accuracy":         float(accuracy_score(y_val, preds)),
        "precision":        float(precision_score(y_val, preds, zero_division=0)),
        "recall":           float(recall_score(y_val, preds, zero_division=0)),
        "f1":               float(f1_score(y_val, preds, zero_division=0)),
        "pr_auc":           float(average_precision_score(y_val, probs)),
        "confusion_matrix": confusion_matrix(y_val, preds).tolist(),
    }
    return metrics


# --------------- persistence --------------------------------------------

def save_model(model: xgb.XGBClassifier, path: str) -> None:
    """Save the trained model as JSON (requires tree_method='hist')."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Use the JSON format supported by xgboost >= 2.0
    model.save_model(path)


def load_model(path: str) -> xgb.XGBClassifier:
    """Load a previously saved XGBoost model."""
    model = xgb.XGBClassifier()
    model.load_model(path)
    return model


# --------------- feature importance --------------------------------------

def feature_importance(model: xgb.XGBClassifier, feature_names: list[str]) -> list[dict]:
    """Return a sorted list of {feature, importance} dicts."""
    importances = model.feature_importances_
    combined = sorted(
        zip(feature_names, importances), key=lambda x: x[1], reverse=True
    )
    return [{"feature": name, "importance": round(float(imp), 4)} for name, imp in combined]

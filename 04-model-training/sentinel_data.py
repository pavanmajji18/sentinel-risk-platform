"""Data loading and feature preparation for the SENTINEL XGBoost model."""

import pandas as pd

FEATURE_COLUMNS = [
    "amount",
    "customer_avg_amount_90d",
    "is_new_device",
    "distance_km",
    "hour_of_day",
    "failed_attempts",
    "amount_to_avg_ratio",
    "is_night",
    "transaction_count_last_1_hour",
    "transaction_amount_last_24_hours",
    "time_since_last_txn",
    "account_age_days",
]


def load_data(path: str) -> pd.DataFrame:
    """Load a transactions CSV and return it as a pandas DataFrame."""
    df = pd.read_csv(path)
    return df


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Extract the feature matrix X and the label series y."""
    X = df[FEATURE_COLUMNS]
    y = df["label"]
    return X, y


def split_data(
    X: pd.DataFrame, y: pd.Series, train_frac: float = 0.70, val_frac: float = 0.15
) -> tuple:
    """Chronological 70/15/15 train / validation / holdout split.

    Rows are assumed to be ordered oldest-first (as generated).  No shuffling
    is performed so that labels from future transactions cannot leak into
    training features — the same guarantee required when using label_available_at
    in a production system.

    Returns:
        X_train, X_val, X_holdout, y_train, y_val, y_holdout
    """
    n = len(X)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    X_train   = X.iloc[:train_end]
    X_val     = X.iloc[train_end:val_end]
    X_holdout = X.iloc[val_end:]

    y_train   = y.iloc[:train_end]
    y_val     = y.iloc[train_end:val_end]
    y_holdout = y.iloc[val_end:]

    return X_train, X_val, X_holdout, y_train, y_val, y_holdout

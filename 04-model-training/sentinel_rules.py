"""Rules-based fraud engine mirroring Risk API (R01–R06)."""

from dataclasses import dataclass

# --------------- data class for a single transaction --------------------

@dataclass
class Transaction:
    amount: float
    customer_avg_amount_90d: float
    is_new_device: int
    distance_km: float
    hour_of_day: int
    failed_attempts: int
    amount_to_avg_ratio: float = 0.0
    is_night: int = 0
    transaction_count_last_1_hour: int = 0
    transaction_amount_last_24_hours: float = 0.0
    time_since_last_txn: float = 0.0
    account_age_days: int = 0


# --------------- rules --------------------------------------------------

def _rule_r01(tx: Transaction) -> bool:
    """R01 – new device."""
    return tx.is_new_device == 1


def _rule_r02(tx: Transaction) -> bool:
    """R02 – geo mismatch (distance > 100 km)."""
    return tx.distance_km > 100


def _rule_r03(tx: Transaction) -> bool:
    """R03 – odd hours (before 6 am)."""
    return tx.hour_of_day < 6


def _rule_r04(tx: Transaction) -> bool:
    """R04 – failed attempts >= 3."""
    return tx.failed_attempts >= 3


def _rule_r05(tx: Transaction) -> bool:
    """R05 – amount spike (amount > 3× average, avg > 0)."""
    if tx.customer_avg_amount_90d > 0:
        return tx.amount > tx.customer_avg_amount_90d * 3
    return False


def _rule_r06(tx: Transaction) -> bool:
    """R06 – new account (avg == 0)."""
    return tx.customer_avg_amount_90d == 0


ALL_RULES = [
    ("R01", _rule_r01),
    ("R02", _rule_r02),
    ("R03", _rule_r03),
    ("R04", _rule_r04),
    ("R05", _rule_r05),
    ("R06", _rule_r06),
]


# --------------- public API ---------------------------------------------

def apply_rules(tx: Transaction) -> tuple[float, list[str]]:
    """Run all 6 rules; return (risk_score, list_of_triggered_codes).

    risk_score = triggered_rules / 6  (capped at 1.0).
    """
    triggered: list[str] = []
    for code, fn in ALL_RULES:
        if fn(tx):
            triggered.append(code)
    score = len(triggered) / len(ALL_RULES)
    return min(score, 1.0), triggered

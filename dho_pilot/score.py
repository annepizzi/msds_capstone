"""Scores that can be computed before and after outcomes resolve.

Bias deltas and the Counterfactual Sensitivity Index do not need a close.
Brier score and log loss wait for a resolved 0/1 event.
"""

from __future__ import annotations

import math
from collections import defaultdict


def brier(probability: float, outcome: int) -> float:
    if outcome not in (0, 1):
        raise ValueError("outcome must be 0 or 1")
    return (probability - outcome) ** 2


def log_loss(probability: float, outcome: int, eps: float = 1e-6) -> float:
    p = min(max(probability, eps), 1 - eps)
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def bias_delta(baseline: list[float], variant: list[float]) -> dict:
    if not baseline or not variant:
        raise ValueError("both series need at least one probability")
    base = sum(baseline) / len(baseline)
    alt = sum(variant) / len(variant)
    return {
        "baseline_mean": base,
        "variant_mean": alt,
        "delta": alt - base,
        "baseline_sd": _sd(baseline),
        "variant_sd": _sd(variant),
    }


def counterfactual_sensitivity(observations: list[dict]) -> dict:
    """observations: {variable, delta_p_close, expected_sign}.

    expected_sign is +1, -1, or 0. A zero expectation scores as sensitive
    only when the absolute move stays under a small band.
    """
    scored = []
    for row in observations:
        delta = row["delta_p_close"]
        expected = row["expected_sign"]
        if expected == 0:
            agree = abs(delta) < 0.05
        else:
            agree = (delta > 0 and expected > 0) or (delta < 0 and expected < 0)
        scored.append({**row, "agree": agree})
    hits = sum(1 for row in scored if row["agree"])
    return {
        "csi": hits / len(scored) if scored else None,
        "n": len(scored),
        "rows": scored,
    }


def platform_disagreement(rows: list[dict]) -> list[dict]:
    """rows: {deal_id, platform, p_close}. Returns mean and sd by deal."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["deal_id"]].append(row["p_close"])
    summary = []
    for deal_id, values in grouped.items():
        summary.append(
            {
                "deal_id": deal_id,
                "mean_p_close": sum(values) / len(values),
                "sd_p_close": _sd(values),
                "n_platforms": len(values),
            }
        )
    return summary


def _sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))

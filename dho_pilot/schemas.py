"""Frozen shapes for dossier fields, forecasts, and ledger entries.

Prompt v2 asks every model for every field. Branching ("ROI only if
success is higher") makes deals incomparable, so the schema does not branch.
"""

from __future__ import annotations

import json
from typing import Literal

try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:  # pragma: no cover - stdlib fallback when pydantic is absent
    BaseModel = None


FORECAST_KEYS = (
    "p_close",
    "p_terminate",
    "p_higher_bid",
    "p_value_creating_36m",
    "confidence",
)


def validate_forecast(payload: dict) -> list[str]:
    """Return a list of schema errors. Empty list means the JSON is usable."""
    errors = []
    if not isinstance(payload, dict):
        return ["response is not a JSON object"]
    for key in FORECAST_KEYS:
        if key not in payload:
            errors.append(f"missing {key}")
            continue
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{key} is not a number")
            continue
        if not 0 <= float(value) <= 1 and key != "confidence":
            errors.append(f"{key}={value} is outside 0 to 1")
        if key == "confidence" and not 0 <= float(value) <= 100:
            errors.append(f"confidence={value} is outside 0 to 100")
    for key, n in (("drivers", 5), ("risks", 3), ("citations", 1)):
        if key not in payload or not isinstance(payload[key], list) or len(payload[key]) < n:
            errors.append(f"{key} needs at least {n} items")
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, dict):
        errors.append("assumptions must be an object with roi, wacc, roa ranges")
    else:
        for metric in ("roi_5y", "wacc", "roa"):
            block = assumptions.get(metric)
            if not isinstance(block, dict) or "low" not in block or "high" not in block:
                errors.append(f"assumptions.{metric} needs low and high")
    if payload.get("missing_information") is None:
        errors.append("missing_information must be present (use an empty list if none)")
    return errors


if BaseModel is not None:

    class AssumptionRange(BaseModel):
        low: float
        high: float
        point: float | None = None

    class ForecastResponse(BaseModel):
        p_close: float = Field(ge=0, le=1)
        p_terminate: float = Field(ge=0, le=1)
        p_higher_bid: float = Field(ge=0, le=1)
        p_value_creating_36m: float = Field(ge=0, le=1)
        confidence: float = Field(ge=0, le=100)
        drivers: list[str] = Field(min_length=5)
        risks: list[str] = Field(min_length=3)
        assumptions: dict[str, AssumptionRange]
        citations: list[str] = Field(min_length=1)
        missing_information: list[str]

        @field_validator("assumptions")
        @classmethod
        def _metrics(cls, value: dict) -> dict:
            needed = {"roi_5y", "wacc", "roa"}
            missing = needed - set(value)
            if missing:
                raise ValueError(f"assumptions missing {sorted(missing)}")
            return value


PROMPT_V2 = """You are an independent merger analyst. Use only the dossier provided. Do not use outside knowledge of later events.

Answer all four questions for every deal:
1. Probability the deal closes on the announced terms.
2. Probability the deal is terminated.
3. Probability a higher competing bid appears.
4. Probability the combination creates value for the acquirer 36 months after close.

These four probabilities are separate judgments. Do not force them to sum to 1.

Return JSON only with this shape:
{
  "p_close": 0.0,
  "p_terminate": 0.0,
  "p_higher_bid": 0.0,
  "p_value_creating_36m": 0.0,
  "confidence": 0,
  "drivers": ["", "", "", "", ""],
  "risks": ["", "", ""],
  "assumptions": {
    "roi_5y": {"low": 0.0, "high": 0.0},
    "wacc": {"low": 0.0, "high": 0.0},
    "roa": {"low": 0.0, "high": 0.0}
  },
  "citations": ["section name"],
  "missing_information": []
}
If a fact is missing from the dossier, list it in missing_information. Do not invent it.
"""

BIAS_PROBES: list[dict[str, str]] = [
    {"probe_id": "orientation_flip", "instruction": "Lead with the probability of failure, then success."},
    {"probe_id": "name_mask", "instruction": "Company names in the dossier are replaced with Target A and Acquirer B."},
    {"probe_id": "acquirer_swap", "instruction": "The acquirer identity is swapped with a paired deal. Hold all numbers fixed."},
    {"probe_id": "premium_up", "instruction": "The stated premium is increased by 10 percentage points. All other facts stay fixed."},
    {"probe_id": "premium_down", "instruction": "The stated premium is decreased by 10 percentage points. All other facts stay fixed."},
    {"probe_id": "persona_bull", "instruction": "Reason as the bull analyst, then still return the same JSON schema."},
    {"probe_id": "persona_bear", "instruction": "Reason as the bear analyst, then still return the same JSON schema."},
    {"probe_id": "persona_regulator", "instruction": "Reason as the regulator, then still return the same JSON schema."},
    {"probe_id": "trim_fairness", "instruction": "The fairness-opinion section has been removed."},
    {"probe_id": "trim_regulatory", "instruction": "The regulatory-approvals section has been removed."},
]

# Full-study probes in the architecture doc are six. The pilot uses the six
# that map cleanly onto a signed delta versus baseline.
PILOT_PROBES = [
    "orientation_flip",
    "name_mask",
    "acquirer_swap",
    "premium_up",
    "persona_bear",
    "trim_regulatory",
]


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


Consideration = Literal["cash", "stock", "mixed", "unknown"]

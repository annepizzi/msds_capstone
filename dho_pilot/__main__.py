"""Pilot commands for the Deal Horizon Observatory test plan.

Examples
--------
python -m dho_pilot budget
python -m dho_pilot odds
python -m dho_pilot leakage-demo
python -m dho_pilot ledger-demo
python -m dho_pilot fetch
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from dho_pilot.deals import DEALS, HYPOTHESES
from dho_pilot.ledger import append, verify
from dho_pilot.leakage import scan
from dho_pilot.market_odds import annualized_spread, implied_completion, unaffected_from_premium
from dho_pilot.schemas import BIAS_PROBES, PILOT_PROBES, PROMPT_V2, validate_forecast
from dho_pilot.score import brier, counterfactual_sensitivity, log_loss


def call_budget() -> dict:
    n_deals_full = 20
    n_platforms = 4
    n_structured = 3
    n_probes_full = 6
    n_reps = 3
    full = n_deals_full * n_platforms * (n_structured + n_probes_full) * n_reps
    baseline = 5 * n_platforms * n_reps
    # Two stratified deals (one cash, one high-regulation), six probes, two reps.
    probes = 2 * n_platforms * len(PILOT_PROBES) * 2
    return {
        "full_study_calls": full,
        "pilot_baseline_calls": baseline,
        "pilot_probe_calls": probes,
        "pilot_total_calls": baseline + probes,
        "formula_full": "20 deals x 4 platforms x (3 prompt variants + 6 probes) x 3 reps",
        "formula_pilot": "5x4x3 baseline, then 2 deals x 4 platforms x 6 probes x 2 reps",
        "pilot_probe_ids": PILOT_PROBES,
    }


def cmd_budget() -> None:
    print(json.dumps(call_budget(), indent=2))


def cmd_registry() -> None:
    rows = [
        {
            "deal_id": d["deal_id"],
            "pair": f"{d['target']} / {d['acquirer']}",
            "consideration": d["consideration"],
            "status": d["profile_status"],
            "why": d["role_in_pilot"],
            "filings": len(d["filings"]),
        }
        for d in DEALS
    ]
    print(json.dumps(rows, indent=2))


def cmd_odds() -> None:
    # Caesars profile: $31 cash, 49% premium => unaffected about $20.81.
    # Illustrative market price only, so the arithmetic can be checked.
    offer = 31.0
    break_price = unaffected_from_premium(offer, 0.49)
    illustrative_price = 28.50
    result = implied_completion(illustrative_price, offer, break_price)
    result["deal_id"] = "CZR-FERTITTA"
    result["offer"] = offer
    result["break_price_proxy"] = round(break_price, 4)
    result["illustrative_price"] = illustrative_price
    result["annualized_if_180_days"] = annualized_spread(result["gross_spread"], 180)
    result["note"] = "Replace illustrative_price with the close on the forecast date before any model call."
    print(json.dumps(result, indent=2))


def cmd_leakage_demo() -> None:
    dirty = (
        "Norfolk Southern stockholders voted to adopt the merger agreement. "
        "The outside date was extended after a schedule review."
    )
    clean = (
        "The merger agreement requires STB approval and a shareholder vote. "
        "The outside date is January 28, 2028. The regulatory termination fee is $2.5 billion."
    )
    print(json.dumps({"dirty_hits": scan(dirty), "clean_hits": scan(clean)}, indent=2))


def cmd_schema_demo() -> None:
    bad = {"p_close": 0.8, "confidence": 70}
    good = {
        "p_close": 0.72,
        "p_terminate": 0.18,
        "p_higher_bid": 0.11,
        "p_value_creating_36m": 0.41,
        "confidence": 64,
        "drivers": ["cash consideration", "premium", "ticking fee", "financing", "vote threshold"],
        "risks": ["regulatory delay", "financing market", "outside date"],
        "assumptions": {
            "roi_5y": {"low": 0.04, "high": 0.09},
            "wacc": {"low": 0.07, "high": 0.10},
            "roa": {"low": 0.03, "high": 0.06},
        },
        "citations": ["Merger Agreement summary"],
        "missing_information": [],
    }
    print(json.dumps({"incomplete_errors": validate_forecast(bad), "complete_errors": validate_forecast(good)}, indent=2))


def cmd_ledger_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ledger.jsonl"
        first = append(path, {"deal_id": "CZR-FERTITTA", "platform": "demo", "p_close": 0.72})
        second = append(path, {"deal_id": "NSC-UNP", "platform": "demo", "p_close": 0.55})
        ok, message = verify(path)
        # Tamper with the first payload and show the chain fails.
        lines = path.read_text().splitlines()
        forged = json.loads(lines[0])
        forged["payload"]["p_close"] = 0.99
        lines[0] = json.dumps(forged)
        path.write_text("\n".join(lines) + "\n")
        tamper_ok, tamper_message = verify(path)
        print(
            json.dumps(
                {
                    "head": second["entry_hash"][:16],
                    "links_to": second["prev_hash"][:16],
                    "matches_first": second["prev_hash"] == first["entry_hash"],
                    "verify": message,
                    "verify_ok": ok,
                    "after_tamper": tamper_message,
                    "tamper_ok": tamper_ok,
                },
                indent=2,
            )
        )


def cmd_scores() -> None:
    observations = [
        {"variable": "premium", "delta_p_close": 0.06, "expected_sign": 1},
        {"variable": "regulatory_gravity", "delta_p_close": -0.08, "expected_sign": -1},
        {"variable": "closing_horizon", "delta_p_close": 0.03, "expected_sign": -1},
    ]
    print(
        json.dumps(
            {
                "hypotheses": HYPOTHESES,
                "example_csi": counterfactual_sensitivity(observations),
                "brier_when_closed": brier(0.72, 1),
                "log_loss_when_closed": log_loss(0.72, 1),
                "probes": [p["probe_id"] for p in BIAS_PROBES],
            },
            indent=2,
        )
    )


def cmd_prompt() -> None:
    sys.stdout.write(PROMPT_V2)


def cmd_fetch(args: argparse.Namespace) -> None:
    from dho_pilot.fetch_filings import fetch_pilot

    root = Path(args.out)
    records = fetch_pilot(root, limit=args.limit)
    blocked = [
        r["deal_id"]
        for r in records
        if r.get("coverage", {}).get("prompt_blocked")
    ]
    print(json.dumps({"downloaded": len(records), "prompt_blocked": blocked, "manifest": str(root / "raw" / "manifest.json")}, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Deal Horizon Observatory pilot tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("budget")
    sub.add_parser("registry")
    sub.add_parser("odds")
    sub.add_parser("leakage-demo")
    sub.add_parser("schema-demo")
    sub.add_parser("ledger-demo")
    sub.add_parser("scores")
    sub.add_parser("prompt")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--out", default="dho_data")
    fetch.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    {
        "budget": cmd_budget,
        "registry": cmd_registry,
        "odds": cmd_odds,
        "leakage-demo": cmd_leakage_demo,
        "schema-demo": cmd_schema_demo,
        "ledger-demo": cmd_ledger_demo,
        "scores": cmd_scores,
        "prompt": cmd_prompt,
    }.get(args.cmd, lambda: cmd_fetch(args))()


if __name__ == "__main__":
    main()

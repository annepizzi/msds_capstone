"""Five-deal pilot register from the Week 4 dataset report.

CIKs and URLs are copied from the report appendix. The report says CIKs
taken from EDGAR paths still need a check against the company page.
"""

from __future__ import annotations

DEALS = [
    {
        "deal_id": "CZR-FERTITTA",
        "target": "Caesars Entertainment",
        "acquirer": "Fertitta Gaming Holdco",
        "target_ticker": "CZR",
        "acquirer_ticker": None,
        "target_cik": "0001590895",
        "consideration": "cash",
        "offer_cash": 31.00,
        "exchange_ratio": 0.0,
        "premium_to_unaffected": 0.49,
        "role_in_pilot": "cash take-private; ticking fee",
        "profile_status": "drafted",
        "filings": [
            {
                "form": "DEFM14A",
                "url": "https://www.sec.gov/Archives/edgar/data/1590895/000119312526365696/d143368ddefm14a.htm",
            }
        ],
    },
    {
        "deal_id": "PAYO-NUVEI",
        "target": "Payoneer Global",
        "acquirer": "Neon Maple Parent (Nuvei)",
        "target_ticker": "PAYO",
        "acquirer_ticker": None,
        "target_cik": "0001845815",
        "consideration": "cash",
        "offer_cash": 7.40,
        "exchange_ratio": 0.0,
        "premium_to_unaffected": None,
        "role_in_pilot": "sponsor-backed cash take-private",
        "profile_status": "drafted",
        "filings": [
            {
                "form": "DEFM14A",
                "url": "https://www.sec.gov/Archives/edgar/data/1845815/000110465926094105/tm2619600-2_defm14a.htm",
            }
        ],
    },
    {
        "deal_id": "KVUE-KMB",
        "target": "Kenvue",
        "acquirer": "Kimberly-Clark",
        "target_ticker": "KVUE",
        "acquirer_ticker": "KMB",
        "target_cik": "0001944048",
        "consideration": "unknown",
        "offer_cash": None,
        "exchange_ratio": None,
        "premium_to_unaffected": None,
        "role_in_pilot": "strategic consumer; terms still to extract",
        "profile_status": "pending",
        "filings": [
            {
                "form": "DEFM14A",
                "url": "https://www.sec.gov/Archives/edgar/data/1944048/000114036125045607/ny20060344x1_defm14a.htm",
            }
        ],
    },
    {
        "deal_id": "NSC-UNP",
        "target": "Norfolk Southern",
        "acquirer": "Union Pacific",
        "target_ticker": "NSC",
        "acquirer_ticker": "UNP",
        "target_cik": "0000702165",
        "acquirer_cik": "0000100885",
        "consideration": "mixed",
        "offer_cash": 88.82,
        "exchange_ratio": 1.0,
        "premium_to_unaffected": None,
        "role_in_pilot": "high regulatory gravity; stock-and-cash",
        "profile_status": "partial",
        "filings": [
            {
                "form": "DEFM14A",
                "url": "https://www.sec.gov/Archives/edgar/data/702165/000119312525226601/d64358ddefm14a.htm",
            },
            {
                "form": "8-K",
                "url": "https://www.sec.gov/Archives/edgar/data/100885/000119312525168150/d51641d8k.htm",
            },
            {
                "form": "8-K",
                "url": "https://www.sec.gov/Archives/edgar/data/100885/000119312525270046/d84472d8k.htm",
            },
            {
                "form": "8-K",
                "url": "https://www.sec.gov/Archives/edgar/data/100885/000010088525000332/unp-20251114.htm",
            },
        ],
    },
    {
        "deal_id": "UNF-CTAS",
        "target": "UniFirst",
        "acquirer": "Cintas",
        "target_ticker": "UNF",
        "acquirer_ticker": "CTAS",
        "target_cik": "0000717954",
        "acquirer_cik": "0000723254",
        "consideration": "unknown",
        "offer_cash": None,
        "exchange_ratio": None,
        "premium_to_unaffected": None,
        "role_in_pilot": "strategic; terms still to extract",
        "profile_status": "pending",
        "filings": [
            {
                "form": "DEFM14A",
                "url": "https://www.sec.gov/Archives/edgar/data/717954/000114036126020380/ny20072400x1_defm14a.htm",
            },
            {
                "form": "8-K",
                "url": "https://www.sec.gov/Archives/edgar/data/723254/000095010326008890/dp248355_8k.htm",
            },
        ],
    },
]

# Sections that must be present before a dossier is prompt-safe.
REQUIRED_SECTIONS = [
    "summary",
    "background of the merger",
    "reasons",
    "opinion of",
    "financing",
    "regulatory",
    "merger agreement",
]

# Directional hypotheses from the Insights report, used by the
# Counterfactual Sensitivity Index. sign is the expected change in P(close).
HYPOTHESES = [
    {"variable": "premium", "expected_sign_p_close": +1, "basis": "Shareholder approval; Roll 1986 on overpayment for value creation"},
    {"variable": "regulatory_gravity", "expected_sign_p_close": -1, "basis": "Deal-spread and remedy risk"},
    {"variable": "reverse_termination_fee", "expected_sign_p_close": +1, "basis": "Buyer commitment"},
    {"variable": "cash_share", "expected_sign_p_close": +1, "basis": "Less mark-to-market vote risk than stock"},
    {"variable": "closing_horizon", "expected_sign_p_close": -1, "basis": "Time at risk"},
    {"variable": "synergy_to_ebitda", "expected_sign_p_close": 0, "basis": "Completion-neutral; tests value-creation separately"},
]

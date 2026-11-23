"""Market-implied completion probability from the deal spread.

For a cash or stock-and-cash offer, if the target price is a blend of the
offer and a break price:

    price = p * offer_value + (1 - p) * break_price
    p = (price - break_price) / (offer_value - break_price)

offer_value for a mixed deal is cash plus exchange_ratio times the acquirer
price on the same date. The break price is not observed. Using the
unaffected price is a labeled proxy, and it is wrong if standalone value
has moved since announcement. Do not put this probability into the prompt.
"""

from __future__ import annotations


def offer_value(offer_cash: float, exchange_ratio: float, acquirer_price: float) -> float:
    return float(offer_cash) + float(exchange_ratio) * float(acquirer_price)


def implied_completion(price: float, offer: float, break_price: float) -> dict:
    if offer == break_price:
        raise ValueError("offer and break price are equal; probability is undefined")
    if not (min(offer, break_price) <= price <= max(offer, break_price)):
        # Price outside the two anchors. Still report the raw ratio and flag it.
        bounded = False
    else:
        bounded = True
    probability = (price - break_price) / (offer - break_price)
    gross_spread = (offer - price) / price if price else None
    return {
        "p_market": probability,
        "gross_spread": gross_spread,
        "price_inside_anchors": bounded,
        "method": "two_state_blend",
        "assumptions": [
            "One close-on-terms state and one break state.",
            "Break price is an input, often the unaffected price as a proxy.",
            "Ignores ticking fees, collars, proration, and financing outs.",
            "Stock leg must use the acquirer price on the forecast date.",
        ],
    }


def unaffected_from_premium(offer: float, premium: float) -> float:
    """premium is offer/unaffected - 1, so unaffected = offer / (1 + premium)."""
    if premium <= -1:
        raise ValueError("premium must be greater than -100%")
    return offer / (1 + premium)


def annualized_spread(gross_spread: float, days_to_close: int) -> float:
    if days_to_close <= 0:
        raise ValueError("days_to_close must be positive")
    return gross_spread * (365 / days_to_close)

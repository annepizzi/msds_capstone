"""Flag dossier text that would teach the model an outcome.

This is a scanner, not a proof. A human still audits every dossier before
the first forecast batch. Anything it flags is prompt-unsafe until removed.
"""

from __future__ import annotations

import re

# Patterns observed or expected in the Week 4 leakage notes:
# vote results and schedule slips were already inside a draft profile.
PATTERNS = [
    ("vote_result", r"\b(votes?\s+(for|against|cast|represented)|stockholders?\s+voted|item\s+5\.07)\b"),
    ("closing", r"\b(merger\s+(was\s+)?(completed|consummated)|transaction\s+closed|closing\s+occurred)\b"),
    ("termination", r"\b(terminated\s+the\s+merger\s+agreement|agreement\s+was\s+terminated|deal\s+was\s+abandoned)\b"),
    ("schedule_slip", r"\b(outside\s+date\s+(was\s+)?extended|closing\s+(was\s+)?delayed|timeline\s+slipped)\b"),
    ("remedy", r"\b(consent\s+decree|divestiture\s+order|second\s+request\s+(issued|complied))\b"),
    ("post_price", r"\b(shares?\s+(closed|traded)\s+at\s+\$?\d|after\s+the\s+announcement,?\s+the\s+stock)\b"),
]


def scan(text: str) -> list[dict]:
    hits = []
    for label, pattern in PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            hits.append(
                {
                    "label": label,
                    "span": match.group(0),
                    "context": " ".join(text[start:end].split()),
                }
            )
    return hits


def prompt_allowed(text: str) -> bool:
    return not scan(text)

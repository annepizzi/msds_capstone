"""Append-only SHA-256 forecast ledger.

Each entry binds the previous hash, so a later edit of any forecast changes
every hash after it. Publish the head hash (git commit is enough at capstone
scale) before the next deal event.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dho_pilot.schemas import canonical_json

GENESIS = "0" * 64


def entry_hash(payload: dict, prev_hash: str) -> str:
    body = canonical_json({"payload": payload, "prev_hash": prev_hash})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def append(path: Path, payload: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    prev = GENESIS
    if lines:
        prev = json.loads(lines[-1])["entry_hash"]
    record = {
        "prev_hash": prev,
        "payload": payload,
        "entry_hash": entry_hash(payload, prev),
    }
    with path.open("a") as handle:
        handle.write(canonical_json(record) + "\n")
    return record


def verify(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "ledger file is missing"
    prev = GENESIS
    count = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["prev_hash"] != prev:
            return False, f"chain break at entry {count}"
        expected = entry_hash(record["payload"], record["prev_hash"])
        if record["entry_hash"] != expected:
            return False, f"hash mismatch at entry {count}"
        prev = record["entry_hash"]
        count += 1
    return True, f"{count} entries verified; head {prev[:12]}"

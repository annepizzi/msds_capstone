"""Download public EDGAR filings into a hashed raw store.

SEC fair-access rules require a User-Agent that identifies the requester
and a request rate at or below the published limit (10 requests per second
as of the Week 4 architecture note; confirm the current policy).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from dho_pilot.deals import DEALS, REQUIRED_SECTIONS

DEFAULT_SLEEP_S = 0.2


def user_agent() -> str:
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not agent:
        raise SystemExit(
            "Set SEC_USER_AGENT to a string with your name and email, "
            "for example: SEC_USER_AGENT='Anne Pizzini MSDS498 anne@example.com'"
        )
    return agent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str, dest: Path, agent: str, sleep_s: float = DEFAULT_SLEEP_S) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": agent, "Accept-Encoding": "gzip, deflate"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            encoding = response.headers.get("Content-Encoding", "")
    except urllib.error.HTTPError as exc:
        return {"url": url, "ok": False, "status": exc.code, "error": str(exc)}
    if encoding == "gzip":
        import gzip

        raw = gzip.decompress(raw)
    digest = sha256_bytes(raw)
    stamped = dest.with_name(f"{dest.stem}.{digest[:12]}{dest.suffix}")
    stamped.write_bytes(raw)
    time.sleep(sleep_s)
    return {
        "url": url,
        "ok": True,
        "path": str(stamped),
        "sha256": digest,
        "bytes": len(raw),
    }


def section_coverage(html: str) -> dict:
    lowered = html.lower()
    found = [name for name in REQUIRED_SECTIONS if name in lowered]
    missing = [name for name in REQUIRED_SECTIONS if name not in lowered]
    return {
        "found": found,
        "missing": missing,
        "coverage": len(found) / len(REQUIRED_SECTIONS),
        "prompt_blocked": bool(missing),
    }


def fetch_pilot(root: Path, limit: int | None = None) -> list[dict]:
    agent = user_agent()
    records = []
    deals = DEALS if limit is None else DEALS[:limit]
    for deal in deals:
        for filing in deal["filings"]:
            name = f"{deal['deal_id']}_{filing['form']}.html"
            result = download(filing["url"], root / "raw" / name, agent)
            result["deal_id"] = deal["deal_id"]
            result["form"] = filing["form"]
            if result.get("ok"):
                text = Path(result["path"]).read_text(errors="replace")
                result["coverage"] = section_coverage(text)
            records.append(result)
    manifest = root / "raw" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(records, indent=2))
    return records

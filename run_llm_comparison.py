"""Ask each configured LLM to profile a deal from its SEC filings, then forecast it.

Keys are read from secrets.env in this folder, then from the environment.
A model with a blank key is skipped. Keys are never printed.

Example
-------
cp secrets.env.example secrets.env
# paste keys into secrets.env
python3 run_llm_comparison.py --deal CZR-FERTITTA
python3 run_llm_comparison.py --deal NSC-UNP --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

def _project_root() -> Path:
    """Script folder when run as a file. Notebook cells have no __file__."""
    try:
        return Path(__file__).resolve().parent
    except NameError:
        here = Path.cwd()
        if (here / "dho_pilot").is_dir():
            return here
        fallback = Path("/Users/apizzini/Desktop/Capstone")
        if (fallback / "dho_pilot").is_dir():
            return fallback
        return here


ROOT = _project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dho_pilot.deals import DEALS, REQUIRED_SECTIONS
from dho_pilot.fetch_filings import download
from dho_pilot.leakage import scan

FORECAST_PROMPT = (
    "Based on the situation and company profiles given, determine if this "
    "merger and acquisition will be a success or a failure. Give a percentage "
    "of probability for either failed or successful. If the prediction of "
    "success is higher, what is the ROI, WACC and ROA 5 years from acquisition? "
    "If the prediction of failure is higher, give cause, analysis, and "
    "predictive financial outcomes."
)

PE_FIRMS_URL = "https://umbrex.com/resources/top-1000-global-private-equity-firms/"

PROFILE_INSTRUCTIONS = """You are reading SEC filings for one proposed merger. The filing text below is the Form 8-K and Form DEFM14A for this deal. Alongside those filings, use the Umbrex Top 1000 Global Private Equity Firms directory at https://umbrex.com/resources/top-1000-global-private-equity-firms/. The directory is attached after the filings. Use it to say whether a named acquirer, parent, or financial sponsor appears on that list, and cite the page when you rely on it. A listing is not a financial figure.

Write two sections with those headings:
1. Company profile
Cover the acquirer and the target: legal names, business, scale, and the capital-structure figures that appear in the filings.
2. Situational analysis
Cover deal structure, per-share consideration, premium, synergies, conditions to closing, termination fees, outside date, required approvals, and the process in the background of the merger.

Cite the form type for every material number from the filings. If a number is not in the filing text, write "missing from the filings provided." Do not invent figures.
"""

# Standard list price in USD per 1,000,000 tokens, checked 2026-10-19.
# long_* applies to the whole call once input tokens exceed long_after.
# Edit a row if you change models or a vendor changes its rate card.
PRICE_PER_MILLION = {
    "gpt-4.1": {"input": 2.00, "output": 8.00, "cached_input": 0.50, "source": "https://developers.openai.com/api/docs/pricing"},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "cached_input": 0.10, "source": "https://developers.openai.com/api/docs/pricing"},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40, "cached_input": 0.025, "source": "https://developers.openai.com/api/docs/pricing"},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached_input": 1.25, "source": "https://developers.openai.com/api/docs/pricing"},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached_input": 0.075, "source": "https://developers.openai.com/api/docs/pricing"},
    "gpt-5": {"input": 1.25, "output": 10.00, "cached_input": 0.125, "source": "https://developers.openai.com/api/docs/pricing"},
    "gpt-5-mini": {"input": 0.25, "output": 2.00, "cached_input": 0.025, "source": "https://developers.openai.com/api/docs/pricing"},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cached_input": 0.10, "cache_write": 2.50, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00, "cached_input": 0.30, "cache_write": 3.75, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00, "cached_input": 0.30, "cache_write": 3.75, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cached_input": 0.30, "cache_write": 3.75, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cached_input": 0.20, "cache_write": 2.50, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cached_input": 0.10, "cache_write": 1.25, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "claude-opus-4-5": {"input": 5.00, "output": 25.00, "cached_input": 0.50, "cache_write": 6.25, "source": "https://platform.claude.com/docs/en/about-claude/pricing"},
    "grok-3": {"input": 3.00, "output": 15.00, "source": "https://docs.x.ai/developers/pricing"},
    "grok-3-mini": {"input": 0.30, "output": 0.50, "source": "https://docs.x.ai/developers/pricing"},
    "grok-4.7": {"input": 2.00, "output": 6.00, "cached_input": 0.50, "long_after": 200_000, "long_input": 4.00, "long_output": 12.00, "long_cached_input": 1.00, "source": "https://docs.x.ai/developers/pricing"},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00, "cached_input": 0.20, "long_after": 200_000, "long_input": 4.00, "long_output": 18.00, "long_cached_input": 0.40, "source": "https://ai.google.dev/gemini-api/docs/pricing"},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached_input": 0.125, "long_after": 200_000, "long_input": 2.50, "long_output": 15.00, "long_cached_input": 0.25, "source": "https://ai.google.dev/gemini-api/docs/pricing"},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50, "cached_input": 0.03, "source": "https://ai.google.dev/gemini-api/docs/pricing"},
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        if tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def load_secrets(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def providers() -> list[dict]:
    catalog = [
        {
            "name": "openai",
            "key_env": "OPENAI_API_KEY",
            "model_env": "OPENAI_MODEL",
            "default_model": "gpt-4.1",
            "kind": "openai",
            "url": "https://api.openai.com/v1/chat/completions",
        },
        {
            "name": "anthropic",
            "key_env": "ANTHROPIC_API_KEY",
            "model_env": "ANTHROPIC_MODEL",
            "default_model": "claude-sonnet-5-5",
            "kind": "anthropic",
            "url": "https://api.anthropic.com/v1/messages",
        },
        {
            "name": "xai",
            "key_env": "XAI_API_KEY",
            "model_env": "XAI_MODEL",
            "default_model": "grok-3",
            "kind": "openai",
            "url": "https://api.x.ai/v1/chat/completions",
        },
        {
            "name": "gemini",
            "key_env": "GEMINI_API_KEY",
            "model_env": "GEMINI_MODEL",
            "default_model": "gemini-3.1-pro-preview",
            "kind": "gemini",
            "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        },
    ]
    ready = []
    for item in catalog:
        key = os.environ.get(item["key_env"], "").strip()
        if not key:
            continue
        ready.append({**item, "key": key, "model": os.environ.get(item["model_env"], item["default_model"]).strip() or item["default_model"]})
    return ready


def deal_by_id(deal_id: str) -> dict:
    for deal in DEALS:
        if deal["deal_id"] == deal_id:
            return deal
    known = ", ".join(deal["deal_id"] for deal in DEALS)
    raise SystemExit(f"Unknown deal {deal_id}. Choose one of: {known}")


def local_filings(data_root: Path, deal_id: str) -> list[Path]:
    raw = data_root / "raw"
    if not raw.is_dir():
        return []
    return sorted(path for path in raw.glob(f"{deal_id}_*.html") if path.is_file())


def ensure_filings(deal: dict, data_root: Path) -> list[Path]:
    found = local_filings(data_root, deal["deal_id"])
    if found:
        return found
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not agent:
        raise SystemExit(
            f"No local filings for {deal['deal_id']} in {data_root / 'raw'}. "
            "Set SEC_USER_AGENT in secrets.env, or download them first with "
            "python3 -m dho_pilot fetch."
        )
    saved = []
    for filing in deal["filings"]:
        dest = data_root / "raw" / f"{deal['deal_id']}_{filing['form']}.html"
        result = download(filing["url"], dest, agent)
        if not result.get("ok"):
            raise SystemExit(f"Download failed for {filing['url']}: {result.get('error')}")
        saved.append(Path(result["path"]))
    return saved


def excerpt(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    head = text[: max_chars // 5]
    windows = [head]
    used = max_chars // 5
    lowered = text.lower()
    span = max(4000, (max_chars - used) // max(len(REQUIRED_SECTIONS), 1))
    for label in REQUIRED_SECTIONS:
        at = lowered.find(label)
        if at < 0:
            continue
        start = max(0, at - 500)
        piece = text[start : start + span]
        windows.append(f"\n\n[excerpt around '{label}']\n{piece}")
        used += len(piece)
        if used >= max_chars:
            break
    return "".join(windows)[:max_chars], True


def _fetch_pe_page() -> str:
    """Download the Umbrex directory page. The site blocks a plain Python client."""
    request = urllib.request.Request(
        PE_FIRMS_URL,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        completed = subprocess.run(
            ["curl", "-fsSL", "-A", "Mozilla/5.0", PE_FIRMS_URL],
            check=True,
            capture_output=True,
        )
        return completed.stdout.decode("utf-8", "replace")


def pe_directory_text() -> str:
    """Firm names from the Umbrex Top 1000 page. Cached so each run sees the same list."""
    cache = ROOT / "dho_data" / "umbrex_top_1000_pe_firms.txt"
    if cache.is_file():
        names = cache.read_text().strip()
    else:
        html = _fetch_pe_page()
        match = re.search(r"FIRMS=`(.*?)`", html, re.S)
        if not match:
            raise RuntimeError(f"Could not read the firm list from {PE_FIRMS_URL}")
        names = "\n".join(
            line.split("\t", 1)[0].strip()
            for line in match.group(1).splitlines()
            if line.strip()
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(names + "\n")
    return (
        "Umbrex Top 1000 Global Private Equity Firms\n"
        f"Source: {PE_FIRMS_URL}\n"
        "One firm name per line:\n"
        + names
    )


def profile_prompt_for(packet: str) -> str:
    return (
        PROFILE_INSTRUCTIONS
        + "\n\nFiling text:\n\n"
        + packet
        + "\n\nReference directory:\n\n"
        + pe_directory_text()
    )


def filing_packet(paths: list[Path], max_chars: int) -> tuple[str, list[dict], list[dict]]:
    blocks = []
    meta = []
    for path in paths:
        raw = path.read_text(errors="replace")
        text = html_to_text(raw)
        clipped, truncated = excerpt(text, max_chars)
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
        blocks.append(f"===== {path.name} sha256={digest} =====\n{clipped}")
        meta.append(
            {
                "path": str(path),
                "sha256": digest,
                "chars_extracted": len(text),
                "chars_sent": len(clipped),
                "truncated": truncated,
            }
        )
    packet = "\n\n".join(blocks)
    return packet, meta, scan(packet)


def estimate_tokens(text: str) -> int:
    """Rough input size before a call. Vendors bill the tokenizer, not characters."""
    return max(1, len(text) // 4)


def lookup_rate(model: str) -> dict | None:
    key = model.lower().strip()
    if key in PRICE_PER_MILLION:
        return PRICE_PER_MILLION[key]
    # Drop a trailing snapshot date such as -20250929, then prefer the longest match.
    trimmed = key.rsplit("-", 1)[0] if key[-8:].isdigit() and key[-9:-8] == "-" else key
    candidates = [name for name in PRICE_PER_MILLION if trimmed == name or trimmed.startswith(name + "-") or key.startswith(name + "-")]
    if not candidates:
        return None
    return PRICE_PER_MILLION[max(candidates, key=len)]


def price_usage(model: str, usage: dict) -> dict:
    """Price one call from token counts. Amounts are USD."""
    rate = lookup_rate(model)
    input_tokens = int(usage.get("input_tokens") or 0)
    cached = int(usage.get("cached_input_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    prompt_tokens = input_tokens + cached + cache_write
    if rate is None:
        return {
            "model": model,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "cache_write_tokens": cache_write,
            "output_tokens": output_tokens,
            "usd": None,
            "priced": False,
            "note": f"No list price stored for {model}. Add it to PRICE_PER_MILLION.",
        }
    input_rate = rate["input"]
    output_rate = rate["output"]
    cached_rate = rate.get("cached_input", input_rate)
    write_rate = rate.get("cache_write", input_rate)
    long_after = rate.get("long_after")
    if long_after and prompt_tokens > long_after:
        input_rate = rate.get("long_input", input_rate)
        output_rate = rate.get("long_output", output_rate)
        cached_rate = rate.get("long_cached_input", cached_rate)
    usd = (
        input_tokens * input_rate
        + cached * cached_rate
        + cache_write * write_rate
        + output_tokens * output_rate
    ) / 1_000_000
    return {
        "model": model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "cache_write_tokens": cache_write,
        "output_tokens": output_tokens,
        "input_usd_per_million": input_rate,
        "output_usd_per_million": output_rate,
        "usd": round(usd, 6),
        "priced": True,
        "token_source": usage.get("source", "api"),
        "rate_source": rate.get("source"),
    }


def usage_from_response(kind: str, body: dict) -> dict:
    if kind == "openai":
        usage = body.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0)
        return {
            "input_tokens": max(prompt - cached, 0),
            "cached_input_tokens": cached,
            "cache_write_tokens": 0,
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "source": "api" if usage else "missing",
        }
    if kind == "anthropic":
        usage = body.get("usage") or {}
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "cached_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "cache_write_tokens": int(usage.get("cache_creation_input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "source": "api" if usage else "missing",
        }
    if kind == "gemini":
        usage = body.get("usageMetadata") or {}
        thoughts = int(usage.get("thoughtsTokenCount") or 0)
        return {
            "input_tokens": int(usage.get("promptTokenCount") or 0),
            "cached_input_tokens": int(usage.get("cachedContentTokenCount") or 0),
            "cache_write_tokens": 0,
            "output_tokens": int(usage.get("candidatesTokenCount") or 0) + thoughts,
            "source": "api" if usage else "missing",
        }
    return {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0, "source": "missing"}


def money(usd: float | None) -> str:
    if usd is None:
        return "n/a"
    return f"${usd:,.4f}"


def post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def complete(provider: dict, prompt: str, max_tokens: int, timeout: int) -> tuple[str, dict]:
    if provider["kind"] == "openai":
        body = post_json(
            provider["url"],
            {
                "model": provider["model"],
                "temperature": 0,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            {"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"},
            timeout,
        )
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = content
        return text, usage_from_response("openai", body)
    if provider["kind"] == "anthropic":
        body = post_json(
            provider["url"],
            {
                "model": provider["model"],
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            {
                "x-api-key": provider["key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout,
        )
        text = "\n".join(block.get("text", "") for block in body.get("content", []))
        return text, usage_from_response("anthropic", body)
    if provider["kind"] == "gemini":
        url = provider["url"].format(model=provider["model"])
        body = post_json(
            url,
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
            },
            {"x-goog-api-key": provider["key"], "Content-Type": "application/json"},
            timeout,
        )
        parts = body["candidates"][0]["content"]["parts"]
        text = "\n".join(part.get("text", "") for part in parts)
        return text, usage_from_response("gemini", body)
    raise RuntimeError(f"unknown provider kind {provider['kind']}")


def call_record(provider: dict, name: str, usage: dict) -> dict:
    priced = price_usage(provider["model"], usage)
    return {"prompt": name, **priced}


def run_provider(provider: dict, packet: str, max_tokens: int, timeout: int) -> dict:
    result: dict = {"calls": []}
    profile_prompt = profile_prompt_for(packet)
    try:
        profile, profile_usage = complete(provider, profile_prompt, max_tokens, timeout)
    except Exception as exc:
        result["error"] = str(exc)
        return result
    result["profile"] = profile
    result["calls"].append(call_record(provider, "profile", profile_usage))
    forecast_prompt = (
        "Company profile and situational analysis:\n\n"
        + profile
        + "\n\n"
        + FORECAST_PROMPT
    )
    try:
        forecast, forecast_usage = complete(provider, forecast_prompt, max_tokens, timeout)
    except Exception as exc:
        result["error"] = str(exc)
        result["cost"] = sum_calls(result["calls"])
        return result
    result["forecast"] = forecast
    result["calls"].append(call_record(provider, "forecast", forecast_usage))
    result["cost"] = sum_calls(result["calls"])
    return result


def sum_calls(calls: list[dict]) -> dict:
    priced = [call for call in calls if call.get("priced") and call.get("usd") is not None]
    return {
        "usd": round(sum(call["usd"] for call in priced), 6) if priced else None,
        "input_tokens": sum(call.get("input_tokens", 0) for call in calls),
        "output_tokens": sum(call.get("output_tokens", 0) for call in calls),
        "prompts": len(calls),
    }


def estimate_run(model: str, profile_prompt: str, max_tokens: int) -> dict:
    """Upper bound before the call. Output is assumed to hit max_tokens on both prompts."""
    profile_in = estimate_tokens(profile_prompt)
    profile_out = max_tokens
    forecast_in = estimate_tokens("Company profile and situational analysis:\n\n" + FORECAST_PROMPT) + profile_out
    forecast_out = max_tokens
    profile = price_usage(model, {"input_tokens": profile_in, "output_tokens": profile_out, "source": "estimate"})
    forecast = price_usage(model, {"input_tokens": forecast_in, "output_tokens": forecast_out, "source": "estimate"})
    profile["prompt"] = "profile"
    forecast["prompt"] = "forecast"
    return {"calls": [profile, forecast], "cost": sum_calls([profile, forecast]), "bound": "upper"}


def cost_lines(results: list[dict]) -> list[str]:
    lines = [
        "### Cost of this run",
        "",
        "Dollars use the list price in PRICE_PER_MILLION and the token counts returned by each API. "
        "A profile call sends the filings. A forecast call sends only that model's profile plus the success-or-failure question.",
        "",
        "| Model | Prompt | Input tokens | Output tokens | USD |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    total = 0.0
    any_price = False
    for result in results:
        for call in result.get("calls") or []:
            usd = call.get("usd")
            if usd is not None:
                total += usd
                any_price = True
            lines.append(
                f"| {result['provider']} {result['model']} | {call['prompt']} | "
                f"{call.get('input_tokens', 0):,} | {call.get('output_tokens', 0):,} | {money(usd)} |"
            )
        if result.get("error") and not result.get("calls"):
            lines.append(f"| {result['provider']} {result['model']} | — | — | — | failed before a billed call |")
        subtotal = (result.get("cost") or {}).get("usd")
        if subtotal is not None:
            lines.append(f"| {result['provider']} {result['model']} | both prompts | | | {money(subtotal)} |")
    if any_price:
        lines.append(f"| All models | both prompts | | | {money(total)} |")
    lines.append("")
    lines.append("Prices were checked on 2026-10-19. Cached-token discounts apply only when the API reports cached tokens.")
    lines.append("")
    return lines


def write_report(out_dir: Path, deal: dict, results: list[dict]) -> None:
    lines = [
        f"# {deal['target']} / {deal['acquirer']}",
        "",
        f"Deal id: {deal['deal_id']}",
        "",
        *cost_lines(results),
    ]
    for result in results:
        lines.append(f"## {result['provider']} ({result['model']})")
        lines.append("")
        if result.get("profile"):
            lines.append("### Company profile and situational analysis")
            lines.append("")
            lines.append(result["profile"])
            lines.append("")
        if result.get("forecast"):
            lines.append("### Success or failure forecast")
            lines.append("")
            lines.append(result["forecast"])
            lines.append("")
        if result.get("error"):
            lines.append(f"Error: {result['error']}")
            lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare LLM merger profiles and forecasts")
    parser.add_argument("--deal", default="CZR-FERTITTA", help="Deal id from the Week 4 register")
    parser.add_argument("--secrets", default=str(ROOT / "secrets.env"))
    parser.add_argument("--data", default=str(ROOT / "dho_data"))
    parser.add_argument("--max-chars", type=int, default=80000, help="Characters sent per filing")
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--models", default="", help="Comma-separated subset: openai,anthropic,xai,gemini")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sent, without calling models")
    if argv is None:
        # Jupyter launches the kernel as: ipykernel_launcher.py -f kernel.json
        # argparse would treat that file as an unknown flag.
        try:
            from IPython import get_ipython
            in_notebook = get_ipython() is not None
        except Exception:
            in_notebook = False
        if in_notebook:
            argv = []
    args = parser.parse_args(argv)

    load_secrets(Path(args.secrets))
    deal = deal_by_id(args.deal)
    selected = providers()
    if args.models:
        wanted = {name.strip() for name in args.models.split(",") if name.strip()}
        selected = [item for item in selected if item["name"] in wanted]
        missing = wanted - {item["name"] for item in selected}
        if missing:
            print("No key loaded for:", ", ".join(sorted(missing)))

    print(f"Deal: {deal['target']} / {deal['acquirer']} ({deal['deal_id']})")
    if not selected and not args.dry_run:
        raise SystemExit(
            f"No model keys found. Copy {ROOT / 'secrets.env.example'} to secrets.env and add at least one key."
        )
    for item in selected:
        print(f"  {item['name']}: {item['model']}")
    if args.dry_run and not selected:
        print("  (dry run) no keys loaded; filings will still be prepared")

    data_root = Path(args.data)
    if args.dry_run:
        paths = local_filings(data_root, deal["deal_id"])
        if not paths:
            print(f"No local filings. A real run would download {len(deal['filings'])} file(s) from EDGAR.")
            return
    else:
        paths = ensure_filings(deal, data_root)

    packet, meta, hits = filing_packet(paths, args.max_chars)
    print(f"Filings: {len(meta)}")
    for row in meta:
        flag = " truncated" if row["truncated"] else ""
        print(f"  {Path(row['path']).name}: {row['chars_extracted']} chars extracted, {row['chars_sent']} sent{flag}")
    if hits:
        labels = sorted({hit["label"] for hit in hits})
        print(f"Leakage scanner hits in the text sent to models: {', '.join(labels)} ({len(hits)})")

    profile_prompt = profile_prompt_for(packet)
    catalog = selected or [
        {"name": name, "model": os.environ.get(env, default)}
        for name, env, default in (
            ("openai", "OPENAI_MODEL", "gpt-4.1"),
            ("anthropic", "ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            ("xai", "XAI_MODEL", "grok-3"),
            ("gemini", "GEMINI_MODEL", "gemini-3.1-pro-preview"),
        )
    ]
    print("Estimated cost if each reply uses the full output cap (characters/4 for input tokens):")
    estimate_total = 0.0
    for item in catalog:
        estimate = estimate_run(item["model"], profile_prompt, args.max_tokens)
        for call in estimate["calls"]:
            print(
                f"  {item['name']} {item['model']} {call['prompt']}: "
                f"in {call['input_tokens']:,} out {call['output_tokens']:,} {money(call['usd'])}"
            )
        subtotal = estimate["cost"]["usd"]
        if subtotal is not None:
            estimate_total += subtotal
            print(f"  {item['name']} upper bound: {money(subtotal)}")
    if estimate_total:
        print(f"  all models upper bound: {money(estimate_total)}")
    if args.dry_run:
        print("Dry run only. No model was called.")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = data_root / "llm_runs" / deal["deal_id"] / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for item in selected:
        print(f"Calling {item['name']}...")
        record = {
            "provider": item["name"],
            "model": item["model"],
            "deal_id": deal["deal_id"],
            "filings": meta,
            "leakage_labels": sorted({hit["label"] for hit in hits}),
            "forecast_prompt": FORECAST_PROMPT,
        }
        record.update(run_provider(item, packet, args.max_tokens, args.timeout))
        if record.get("error"):
            print(f"  {item['name']} failed: {record['error']}")
        for call in record.get("calls") or []:
            print(
                f"  {call['prompt']}: in {call.get('input_tokens', 0):,} "
                f"out {call.get('output_tokens', 0):,} {money(call.get('usd'))}"
            )
        subtotal = (record.get("cost") or {}).get("usd")
        if subtotal is not None:
            print(f"  {item['name']} total: {money(subtotal)}")
        results.append(record)
        (out_dir / f"{item['name']}.json").write_text(json.dumps(record, indent=2))
    write_report(out_dir, deal, results)
    print(f"Wrote {out_dir / 'report.md'}")


if __name__ == "__main__":
    main()

# MSDS 498 Capstone — Deal Horizon Observatory

This repository is the working code for an MSDS 498 capstone on merger outcomes. The project, **Deal Horizon Observatory**, reads SEC filings for announced deals and asks several large language models the same two questions: what the companies and the deal look like, and whether the merger is more likely to succeed or fail.

Each model sees the same filing text. The forecast prompt sees the model’s own profile, not the raw filing. Outputs are saved so runs can be compared on success probability, cost, and token use.

## What the code does

1. Looks up a deal in `M&A Datasets.csv` or in the five-deal pilot register in `dho_pilot/deals.py`.
2. Downloads the Form 8-K and Form DEFM14A from EDGAR when they are not already on disk.
3. Turns the HTML into text, caps how much is sent, and scans that text for leakage (language that already states the outcome).
4. Sends a **company profile and situational analysis** prompt, then a **success-or-failure forecast** prompt, to each provider that has an API key.
5. Writes one JSON file per provider plus a `report.md` under `dho_data/llm_runs/<deal-id>/<timestamp>/`.

Providers are OpenAI, Anthropic, xAI, and Google Gemini. A blank key skips that provider. Keys are read from `secrets.env` and are never printed.

`dho_pilot` holds the earlier pilot tools: the deal register, market-implied close odds, the leakage scanner, a hash-chained forecast ledger, and scoring helpers (Brier score, log loss, and a counterfactual sensitivity index).

## Repository layout

| Path | Role |
| --- | --- |
| `capstone.ipynb` | Main notebook. Set one `DEAL_ID`, then profile and forecast that deal. |
| `view_outputs.ipynb` | Reads every JSON payload under `dho_data/llm_runs` and charts success, cost, tokens, and study checks. |
| `dho_pilot_walkthrough.ipynb` | Walks through the pilot tools without calling a model, until the optional EDGAR download. |
| `run_llm_comparison.py` | Same comparison as the main notebook, from the command line. |
| `M&A Datasets.csv` | Deal names, ids, and links to the 8-K and DEFM14A filings. |
| `dho_pilot/` | Pilot package: deals, filing download, leakage scan, odds, ledger, and scores. |
| `secrets.env.example` | Template for API keys and model names. Copy this to `secrets.env`. |
| `dho_data/` | Local filings and model outputs. Git ignores this folder. |

## Setup

Python 3.10 or newer. From this folder:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r dho_pilot/requirements.txt
pip install matplotlib pandas
```

`dho_pilot/requirements.txt` covers the pilot package (`pydantic`, `beautifulsoup4`, `lxml`, `duckdb`). The notebooks also use `matplotlib` and `pandas`.

Copy the secrets template and add the keys you have. A blank key skips that model.

```bash
cp secrets.env.example secrets.env
```

`secrets.env` is listed in `.gitignore`. Do not commit it.

EDGAR asks for a user agent that identifies you. Set this only if a run needs to download filings that are not already in `dho_data/raw`:

```bash
SEC_USER_AGENT="Your Name MSDS498 you@email.com"
```

## Run a comparison

Notebook: open `capstone.ipynb` from this folder and run the cells from top to bottom. `DRY_RUN = True` lists the filings and does not call a model. Set it to `False` when you want to spend API credits. `DEAL_ID` must be an id from `M&A Datasets.csv` (for example `HZO-SAFEHARBOR` or `VAL-RIG`).

Command line, using a deal from the pilot register in `dho_pilot/deals.py`:

```bash
python3 run_llm_comparison.py --deal CZR-FERTITTA --dry-run
python3 run_llm_comparison.py --deal CZR-FERTITTA
python3 run_llm_comparison.py --deal NSC-UNP --models anthropic,gemini
```

Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--deal` | `CZR-FERTITTA` | Deal id from the pilot register. |
| `--models` | all with keys | Comma-separated subset: `openai,anthropic,xai,gemini`. |
| `--dry-run` | off | Prepare filings and print a cost bound. No model is called. |
| `--max-chars` | `80000` | Characters of each filing sent to the model. |
| `--max-tokens` | `16000` | Output token cap per call. |
| `--timeout` | `180` | Seconds to wait for each API call. |

Pilot checks that stay on your machine:

```bash
python -m dho_pilot budget
python -m dho_pilot registry
python -m dho_pilot odds
python -m dho_pilot leakage-demo
python -m dho_pilot ledger-demo
```

After a real run, open `view_outputs.ipynb` and run it from top to bottom. It charts the JSON files already saved under `dho_data/llm_runs`.

## Prompts

**Profile.** The model writes a company profile and a situational analysis from the 8-K and DEFM14A text, and from the [Umbrex Top 1000 Global Private Equity Firms](https://umbrex.com/resources/top-1000-global-private-equity-firms/) directory. It is told to cite the form for every material number and to write “missing from the filings provided” when a figure is not in the text.

**Forecast.** Given that profile, the model says whether the deal is more likely to succeed or fail, gives a probability for each, and then either a five-year ROI, WACC, and ROA (if success is higher) or a cause, analysis, and financial outcome (if failure is higher).

## What is not in git

`.gitignore` excludes `secrets.env` and `dho_data/`. Filings downloaded from EDGAR and the JSON forecasts stay on the machine that ran them. The hash-chained ledger in `dho_pilot` is meant to record a forecast after it is made so later edits are detectable.

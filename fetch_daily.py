#!/usr/bin/env python3
"""
fetch_daily.py — builds the end-of-day JSON that the Credit & Rates Monitor reads.

Deterministic. Standard library only. No model calls, no scraping heuristics.
Run it on a schedule; it appends one row per business day and rewrites data.json.

    python3 fetch_daily.py --out data.json

Two feeds:

  Treasury par yields   official keyless XML from home.treasury.gov. Works today.
  CDS spreads           no free public API exists. Pick an adapter below.

Exit codes: 0 ok, 1 treasury failed, 2 cds failed (treasury still written).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

ISSUERS = ["ORCL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]

# Treasury XML field name -> the tenor key the dashboard expects.
TENORS = {
    "BC_6MONTH": "6M",
    "BC_1YEAR": "1Y",
    "BC_2YEAR": "2Y",
    "BC_10YEAR": "10Y",
    "BC_30YEAR": "30Y",
}

TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"
    "/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)

UA = {"User-Agent": "credit-rates-monitor/1.0 (personal dashboard)"}
KEEP_DAYS = 10000  # ~38 years of sessions; treasury.gov data starts in 1990


def get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ----------------------------------------------------------------------
# Treasury par yield curve — official, free, no key
# ----------------------------------------------------------------------

def fetch_treasury(year: int) -> dict[str, dict[str, float]]:
    """Return {'YYYY-MM-DD': {'6M': 3.71, ...}} for the requested year."""
    root = ET.fromstring(get(TREASURY_URL.format(year=year)))
    out: dict[str, dict[str, float]] = {}

    for entry in root.iter():
        if local(entry.tag) != "properties":
            continue
        row, day = {}, None
        for field in entry:
            name, text = local(field.tag), (field.text or "").strip()
            if name == "NEW_DATE" and text:
                day = text[:10]
            elif name in TENORS and text:
                try:
                    row[TENORS[name]] = round(float(text), 3)
                except ValueError:
                    pass
        if day and row:
            out[day] = row

    if not out:
        raise RuntimeError("Treasury feed parsed but contained no rows")
    return out


# ----------------------------------------------------------------------
# CDS adapters — choose one with --cds
# ----------------------------------------------------------------------
#
# There is no free public API for single-name CDS. These are the real options,
# in descending order of how little work they are.
#
#   csv     you drop a two-column file next to the script each morning.
#           Simplest honest path if you have no licence.
#   ice     ICE Clear Credit publishes free end-of-day 5Y single-name
#           settlement prices. Set CDS_ICE_URL to the daily file URL you pull
#           from theice.com/cds and adjust the column names to match it.
#   vendor  ICE Data Derivatives / S&P Global Market Intelligence / LSEG.
#           Licensed. Set CDS_API_URL and CDS_API_KEY.
#
# Every adapter returns {'ORCL': 198.4, ...} in basis points, or raises.


def cds_from_csv(path: str) -> dict[str, float]:
    """Two columns, no header needed: ticker,spread_bp"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{p} not found — write today's marks there first")
    out: dict[str, float] = {}
    with p.open(newline="") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            tic = row[0].strip().upper()
            if tic in ISSUERS:
                try:
                    out[tic] = round(float(row[1].strip()), 2)
                except ValueError:
                    continue
    if not out:
        raise RuntimeError(f"No recognised tickers in {p}")
    return out


def cds_from_ice(url: str) -> dict[str, float]:
    """
    ICE Clear Credit free end-of-day 5Y single-name settlement prices.

    ICE publishes these as a dated CSV. Column headings have changed over the
    years, so this maps on substrings and falls back gracefully. Point
    CDS_ICE_URL at the current file and check the first run's output.
    """
    text = get(url).decode("utf-8", "replace")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise RuntimeError("ICE file has no header row")

    def col(*needles: str) -> str | None:
        for name in reader.fieldnames:
            low = name.lower()
            if all(n in low for n in needles):
                return name
        return None

    name_col = col("name") or col("entity") or col("instrument")
    # ICE quotes conventional spread in bp; some files carry price instead.
    spread_col = col("spread") or col("par", "coupon") or col("conventional")
    if not name_col or not spread_col:
        raise RuntimeError(f"Could not locate name/spread columns in {reader.fieldnames}")

    # Substring match against the ICE reference-entity legal names.
    aliases = {
        "ORCL": ["oracle"],
        "MSFT": ["microsoft"],
        "GOOGL": ["alphabet", "google"],
        "AMZN": ["amazon"],
        "META": ["meta platforms"],
        "NVDA": ["nvidia"],
    }

    out: dict[str, float] = {}
    for row in reader:
        entity = (row.get(name_col) or "").lower()
        for tic, keys in aliases.items():
            if tic in out:
                continue
            if any(k in entity for k in keys):
                try:
                    out[tic] = round(float((row.get(spread_col) or "").replace(",", "")), 2)
                except ValueError:
                    pass
    if not out:
        raise RuntimeError("ICE file fetched but no target entities matched")
    return out


def cds_from_vendor(url: str, key: str) -> dict[str, float]:
    """
    Licensed vendor endpoint. Shape varies, so adjust the response mapping.
    Expected here: {"data": [{"ticker": "ORCL", "spread5y": 198.4}, ...]}
    """
    req = urllib.request.Request(url, headers={**UA, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=45) as r:
        payload = json.loads(r.read())
    rows = payload.get("data", payload if isinstance(payload, list) else [])
    out = {
        str(x["ticker"]).upper(): round(float(x["spread5y"]), 2)
        for x in rows
        if str(x.get("ticker", "")).upper() in ISSUERS and x.get("spread5y") is not None
    }
    if not out:
        raise RuntimeError("Vendor responded but no target tickers were present")
    return out


def fetch_cds(mode: str) -> dict[str, float]:
    if mode == "csv":
        return cds_from_csv(os.environ.get("CDS_CSV", "cds_today.csv"))
    if mode == "ice":
        url = os.environ.get("CDS_ICE_URL")
        if not url:
            raise RuntimeError("Set CDS_ICE_URL to the ICE end-of-day file")
        return cds_from_ice(url)
    if mode == "vendor":
        url, key = os.environ.get("CDS_API_URL"), os.environ.get("CDS_API_KEY")
        if not (url and key):
            raise RuntimeError("Set CDS_API_URL and CDS_API_KEY")
        return cds_from_vendor(url, key)
    if mode == "none":
        return {}
    raise RuntimeError(f"Unknown cds adapter: {mode}")


# ----------------------------------------------------------------------
# Merge and write
# ----------------------------------------------------------------------

def load(out_path: Path) -> list[dict]:
    if not out_path.exists():
        return []
    try:
        doc = json.loads(out_path.read_text())
    except json.JSONDecodeError:
        print(f"warn: {out_path} was unreadable, starting fresh", file=sys.stderr)
        return []
    return doc.get("series", []) if isinstance(doc, dict) else doc


def merge(series: list[dict], ust_by_day: dict, cds_today: dict, backfill: bool) -> list[dict]:
    rows = {r["date"]: r for r in series}

    days = sorted(ust_by_day) if backfill else sorted(ust_by_day)[-1:]
    for day in days:
        row = rows.setdefault(day, {"date": day, "cds": {}, "ust": {}})
        row["ust"] = ust_by_day[day]

    # CDS marks are for the latest session only.
    if cds_today:
        latest = max(ust_by_day) if ust_by_day else date.today().isoformat()
        rows.setdefault(latest, {"date": latest, "cds": {}, "ust": {}})["cds"].update(cds_today)

    merged = sorted(rows.values(), key=lambda r: r["date"])
    return merged[-KEEP_DAYS:]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build end-of-day credit & rates JSON.")
    ap.add_argument("--out", default="data.json")
    ap.add_argument("--cds", default=os.environ.get("CDS_SOURCE", "none"),
                    choices=["none", "csv", "ice", "vendor"])
    ap.add_argument("--backfill", action="store_true",
                    help="Write every session this year, not just the latest.")
    args = ap.parse_args()

    out_path = Path(args.out)
    series = load(out_path)
    rc = 0

    try:
        ust = fetch_treasury(date.today().year)
        # Early January: pull last year too so the MoM window has history.
        if args.backfill or len(ust) < 30:
            try:
                ust = {**fetch_treasury(date.today().year - 1), **ust}
            except Exception as e:
                print(f"warn: prior-year backfill skipped — {e}", file=sys.stderr)
        print(f"treasury: {len(ust)} sessions, latest {max(ust)}")
    except Exception as e:
        print(f"error: treasury fetch failed — {e}", file=sys.stderr)
        return 1

    cds: dict[str, float] = {}
    if args.cds != "none":
        try:
            cds = fetch_cds(args.cds)
            missing = [t for t in ISSUERS if t not in cds]
            print(f"cds: {len(cds)} marks via {args.cds}" + (f", missing {missing}" if missing else ""))
        except Exception as e:
            print(f"error: cds fetch failed — {e}", file=sys.stderr)
            rc = 2

    merged = merge(series, ust, cds, args.backfill)
    out_path.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "series": merged},
        indent=1,
    ))
    print(f"wrote {out_path} — {len(merged)} sessions through {merged[-1]['date']}")
    return rc


if __name__ == "__main__":
    sys.exit(main())

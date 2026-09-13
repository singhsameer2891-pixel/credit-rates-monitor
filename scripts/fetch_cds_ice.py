#!/usr/bin/env python3
"""
Pull ICE Clear Credit's free end-of-day single-name settlement prices and
write today's 5Y senior CDS par spreads as cds_today.csv (ticker,spread_bp),
the exact shape fetch_daily.py's `csv` adapter reads.

ICE publishes *prices* (per 100 notional), not spreads. For a contract with
fixed coupon c, price P means the protection buyer pays an upfront of
(100 - P)/100 per unit notional. We back out the flat hazard rate h that
reproduces that upfront under the standard flat-hazard/flat-rate model, then
quote the par spread s = (1 - R) * h.

Deterministic stdlib code end to end — no external packages, no services
beyond the one ICE endpoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.request
from datetime import date

ICE_URL = os.environ.get(
    "CDS_ICE_URL",
    "https://www.ice.com/api/cds-settlement-prices/icc-single-names",
)

# ICE entity ticker (instrumentName prefix) -> dashboard ticker
ENTITIES = {
    "ORCLE": "ORCL",
    "MSFT": "MSFT",
    "ALPHINC": "GOOGL",
    "AMZN": "AMZN",
    "METAPL": "META",
    "NVIDIA": "NVDA",
}

COUPON_BP = 100          # the liquid 5Y senior USD contract ICE lists
RECOVERY = 0.40          # standard senior unsecured assumption
FLAT_RATE = 0.045        # flat discount rate; spread is insensitive to it

UA = {"User-Agent": "Mozilla/5.0 (credit-rates-monitor; github actions)"}


def year_fraction(start: str, end: str) -> float:
    y0, m0, d0 = (int(x) for x in start.split("-"))
    y1, m1, d1 = (int(x) for x in end.split("-"))
    return (date(y1, m1, d1) - date(y0, m0, d0)).days / 365.25


def par_spread_bp(price: float, coupon_bp: float, t_years: float) -> float:
    """Invert price -> flat hazard -> par spread, all closed form + bisection."""
    upfront = (100.0 - price) / 100.0
    c = coupon_bp / 10_000.0
    r, lgd = FLAT_RATE, 1.0 - RECOVERY

    def model_upfront(h: float) -> float:
        g = r + h
        annuity = (1.0 - math.exp(-g * t_years)) / g
        return (lgd * h - c) * annuity

    lo, hi = 1e-9, 10.0
    if not (model_upfront(lo) <= upfront <= model_upfront(hi)):
        raise ValueError(f"price {price} out of solvable range")
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if model_upfront(mid) < upfront:
            lo = mid
        else:
            hi = mid
    return lgd * ((lo + hi) / 2.0) * 10_000.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="cds_today.csv")
    args = ap.parse_args()

    try:
        req = urllib.request.Request(ICE_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=45) as resp:
            rows = json.loads(resp.read())
    except Exception as e:
        print(f"error: ICE download failed — {e}", file=sys.stderr)
        return 1

    marks: dict[str, float] = {}
    for row in rows:
        parts = str(row.get("instrumentName", "")).split(".")
        if len(parts) < 6:
            continue
        entity, tier, ccy, _doc, coupon, maturity = parts[:6]
        tic = ENTITIES.get(entity)
        if not tic or tic in marks:
            continue
        if tier != "SNRFOR" or ccy != "USD" or coupon != str(COUPON_BP):
            continue
        try:
            price = float(row["eodPrice"])
            t = year_fraction(row["clearingDate"], maturity)
            marks[tic] = round(par_spread_bp(price, COUPON_BP, t), 1)
        except (KeyError, ValueError) as e:
            print(f"warn: skipped {row.get('instrumentName')} — {e}", file=sys.stderr)

    if not marks:
        print("error: ICE feed fetched but no target entities matched", file=sys.stderr)
        return 1

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        for tic in sorted(marks):
            w.writerow([tic, marks[tic]])

    missing = sorted(set(ENTITIES.values()) - set(marks))
    print(f"cds: wrote {len(marks)} marks to {args.out}"
          + (f", missing {missing}" if missing else ""))
    for tic in sorted(marks):
        print(f"  {tic}: {marks[tic]} bp")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
One-off backfill: write bond-spread PROXY credit history into data.json.

Real single-name CDS history is licensed-only (see tasks.md GROUP 2), so this
uses the closest free stand-in: FRED's daily ICE BofA corporate OAS indices by
rating bucket (no API key needed). Each issuer is mapped to its senior
unsecured rating bucket, and the bucket's OAS history is level-anchored so it
equals the issuer's first *real* CDS mark on the anchor date:

    proxy(date) = real_cds(anchor) * oas_bucket(date) / oas_bucket(anchor)

The shape is the rating cohort's credit cycle; the level is the issuer's own.
Values go into a separate `cds_proxy` field per row — `cds` stays strictly
real ICE-derived marks, and the dashboard's "Proxy history" toggle decides
whether `cds_proxy` is shown. Deterministic stdlib code, no AI, idempotent
(recomputes and overwrites `cds_proxy` on each run).
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path

# cosd pins the start; the ICE BofA OAS series begin 1996-12-31, and without
# cosd the fredgraph endpoint returns only the trailing few years.
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1996-12-01"

# FRED series: ICE BofA US Corporate OAS by rating bucket (percent, daily)
SERIES = {
    "AAA": "BAMLC0A1CAAA",
    "AA":  "BAMLC0A2CAA",
    "A":   "BAMLC0A3CA",
    "BBB": "BAMLC0A4CBBB",
}

# Approximate senior unsecured rating bucket per issuer (documented, coarse).
BUCKETS = {
    "MSFT": "AAA",
    "GOOGL": "AA",
    "AMZN": "AA",
    "META": "AA",
    "NVDA": "A",
    "ORCL": "BBB",
}

UA = {"User-Agent": "Mozilla/5.0 (credit-rates-monitor backfill)"}


def fetch_series(sid: str, csv_dir: Path | None) -> dict[str, float]:
    """FRED CSV -> {date: oas_bp}. Holidays come through as '.' and are skipped.

    With --csv-dir, reads <dir>/<sid>.csv instead of hitting FRED (some
    networks reject FRED's TLS handshake from non-browser clients).
    """
    if csv_dir is not None:
        text = (csv_dir / f"{sid}.csv").read_text()
    else:
        # FRED's CDN drops TLS 1.3 handshakes from non-browser clients; cap at 1.2.
        ctx = ssl.create_default_context()
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        req = urllib.request.Request(FRED.format(sid=sid), headers=UA)
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            text = r.read().decode()
    out: dict[str, float] = {}
    for line in text.splitlines()[1:]:
        day, _, val = line.partition(",")
        try:
            out[day] = float(val) * 100.0  # percent -> bp
        except ValueError:
            continue
    if not out:
        raise RuntimeError(f"FRED series {sid} returned no data")
    return out


def last_on_or_before(series: dict[str, float], day: str) -> float | None:
    if day in series:
        return series[day]
    prior = [d for d in series if d <= day]
    return series[max(prior)] if prior else None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", nargs="?", default="data.json")
    ap.add_argument("--csv-dir", type=Path, default=None,
                    help="read <dir>/<FRED id>.csv instead of downloading")
    args = ap.parse_args()

    path = Path(args.data)
    doc = json.loads(path.read_text())
    rows = doc["series"]

    oas = {b: fetch_series(sid, args.csv_dir) for b, sid in SERIES.items()}
    for b in oas:
        print(f"fred {b}: {len(oas[b])} obs, {min(oas[b])} .. {max(oas[b])}")

    # Anchor: first session carrying a real mark, per issuer.
    anchor: dict[str, tuple[str, float]] = {}
    for r in rows:
        for tic, v in (r.get("cds") or {}).items():
            if tic in BUCKETS and tic not in anchor:
                anchor[tic] = (r["date"], v)
    if not anchor:
        print("error: no real cds marks to anchor to", file=sys.stderr)
        return 1

    factor: dict[str, float] = {}
    for tic, (day, real) in anchor.items():
        base = last_on_or_before(oas[BUCKETS[tic]], day)
        if base is None or base <= 0:
            print(f"warn: no OAS at anchor for {tic}", file=sys.stderr)
            continue
        factor[tic] = real / base
        print(f"anchor {tic}: {real} bp real / {base:.1f} bp {BUCKETS[tic]} OAS "
              f"on {day} -> factor {factor[tic]:.3f}")

    filled = 0
    for r in rows:
        proxy: dict[str, float] = {}
        for tic, f in factor.items():
            if r["date"] >= anchor[tic][0] or (r.get("cds") or {}).get(tic) is not None:
                continue  # real data era — never proxy over it
            v = oas[BUCKETS[tic]].get(r["date"])
            if v is not None:
                proxy[tic] = round(v * f, 1)
        if proxy:
            r["cds_proxy"] = proxy
            filled += 1
        else:
            r.pop("cds_proxy", None)

    path.write_text(json.dumps(doc, indent=1))
    print(f"wrote {path}: proxy marks on {filled} of {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

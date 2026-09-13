#!/usr/bin/env python3
"""
One-off backfill: pull the full Treasury par-yield history (treasury.gov has
daily data back to 1990) and merge it into data.json.

Reuses fetch_daily.py's parser — one request per year, saved to disk after
every year so progress is never lost. Existing rows keep their cds/cds_proxy
fields; ust values are (re)written from the official feed. Idempotent.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_daily import fetch_treasury  # noqa: E402

FIRST_YEAR = 1990


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data.json")
    doc = json.loads(path.read_text())
    rows = {r["date"]: r for r in doc["series"]}

    for year in range(FIRST_YEAR, date.today().year + 1):
        try:
            ust = fetch_treasury(year)
        except Exception as e:
            print(f"warn: {year} failed — {e}", file=sys.stderr)
            continue
        for day, curve in ust.items():
            row = rows.setdefault(day, {"date": day, "cds": {}, "ust": {}})
            row["ust"] = curve
        print(f"{year}: {len(ust)} sessions")

        doc["series"] = sorted(rows.values(), key=lambda r: r["date"])
        doc["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path.write_text(json.dumps(doc, indent=1))
        time.sleep(1)  # be polite to treasury.gov

    print(f"wrote {path}: {len(doc['series'])} sessions "
          f"{doc['series'][0]['date']} .. {doc['series'][-1]['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# tasks.md — credit-rates-monitor
> Generated: 2026-09-13 | PRD ref: README.md (no PRD.md in repo)
> Status legend: ⏳ PENDING | 🔄 IN PROGRESS | ✅ DONE | ❌ BLOCKED

---

## GROUP 1: Automatic CDS data via ICE public settlement prices ✅ DONE
**Depends on:** None
**Summary:** Auto-download ICE Clear Credit EOD single-name settlement prices daily, convert price → par spread (bp), and feed them into data.json so the CDS tiles and chart populate.

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 1.1 | Add `scripts/fetch_cds_ice.py`: download `https://www.ice.com/api/cds-settlement-prices/icc-single-names` (JSON, no auth), select USD SNRFOR 100bp-coupon 5Y instruments for ORCLE/MSFT/ALPHINC/AMZN/METAPL/NVIDIA, convert EOD price → par spread bp (flat-hazard model, 40% recovery), write `cds_today.csv` (`ticker,spread_bp`) | ✅ | stdlib only, no new deps; no changes to fetch_daily.py |
| 1.2 | Update `.github/workflows/daily-refresh.yml`: add "Fetch CDS marks" step (`continue-on-error`) before the data step; set `CDS_SOURCE` to `csv` only if that step succeeded, else `none` | ✅ | Treasury refresh unaffected if ICE is down |
| 1.3 | Add `.gitignore` for `cds_today.csv`; update README data-source section | ✅ | same commit as 1.1/1.2 per doc policy |
| 1.4 | Commit + push, trigger workflow, verify `cds` fields populated in committed data.json and tiles render on the live Pages site | ✅ | |

---

## GROUP 2: Backfill CDS history from ICE ❌ BLOCKED
**Depends on:** GROUP 1
**Summary:** Backfill historical CDS spreads from today back to the earliest date ICE has data for.

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 2.1 | Find historical access to ICE settlement prices | ❌ | Endpoint serves ONLY the latest clearing date; all date params (`date`, `clearingDate`, `asOfDate`, `businessDate`, `tradeDate`, path style) ignored or 404. No history API exists publicly. |
| 2.2 | Alternate sources: Wayback Machine, public scrape repos | ❌ | Wayback: 2 API captures, both 2024 (outside data window); in-window page snapshots are empty JS shells. GitHub: 2 repos use the endpoint, neither publishes accumulated data. |
| 2.3 | Backfill data.json | ❌ | Not possible without a licensed vendor (S&P Global / ICE Data Derivatives). History accrues organically: the daily 06:00 IST job adds one session per weekday from 2026-09-11 onward. |

---

## GROUP 3: Proxy CDS backfill + dashboard toggle ✅ DONE
**Depends on:** GROUP 1 (GROUP 2 blocked → proxy route approved by user)
**Summary:** Backfill pre-live credit history from FRED rating-bucket OAS (level-anchored bond-spread proxy) with a dashboard toggle: ON plots proxy+real, OFF plots only real daily marks.

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 3.1 | `scripts/backfill_cds_proxy.py`: FRED ICE BofA OAS (AAA/AA/A/BBB) → per-issuer proxy via level-anchor to first real mark; writes `cds_proxy` per row | ✅ | deterministic stdlib; TLS1.2 + `--csv-dir` fallback (FRED tarpits non-browser clients) |
| 3.2 | Backfill data.json: 399 rows 2025-02-06..2026-09-10; real `cds` untouched | ✅ | anchors: ORCL 1.91×BBB, MSFT 1.05×AAA, GOOGL 1.04×AA, AMZN 1.07×AA, META 1.42×AA, NVDA 1.14×A |
| 3.3 | index.html: `Proxy history` toggle (default ON, persisted), `cdsAt()` resolution real>proxy, disclosure note in CDS panel | ✅ | verified ON/OFF locally in browser |
| 3.4 | Docs + push + live verification | ✅ | |

---

## GROUP 4: Full history to the data floor ✅ DONE
**Depends on:** GROUP 3
**Summary:** Extend Treasury history to 1990 and proxy credit history to Dec 1996; Max chart window; cohort tags next to company names.

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 4.1 | fetch_daily.py: KEEP_DAYS 400 → 10000 | ✅ | user-approved edit; without it the daily job would re-trim history |
| 4.2 | scripts/backfill_ust_history.py: treasury.gov per-year loop from 1990, saves after each year | ✅ | idempotent |
| 4.3 | backfill_cds_proxy.py: FRED cosd=1996-12-01 (series floor); run via manual Actions workflow backfill-history.yml | ✅ | current-cohort mapping per user decision |
| 4.4 | index.html: Max window (1e9 span, 252-session lookback), year-aware axis/tooltip, cohort tags on tiles+chips, sparkline downsampling | ✅ | |
| 4.5 | Push, dispatch backfill workflow, verify live | ✅ | |

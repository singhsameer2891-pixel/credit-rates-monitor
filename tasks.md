# tasks.md — credit-rates-monitor
> Generated: 2026-09-13 | PRD ref: README.md (no PRD.md in repo)
> Status legend: ⏳ PENDING | 🔄 IN PROGRESS | ✅ DONE | ❌ BLOCKED

---

## GROUP 1: Automatic CDS data via ICE public settlement prices
**Depends on:** None
**Summary:** Auto-download ICE Clear Credit EOD single-name settlement prices daily, convert price → par spread (bp), and feed them into data.json so the CDS tiles and chart populate.

| ID | Task | Status | Notes |
|----|------|--------|-------|
| 1.1 | Add `scripts/fetch_cds_ice.py`: download `https://www.ice.com/api/cds-settlement-prices/icc-single-names` (JSON, no auth), select USD SNRFOR 100bp-coupon 5Y instruments for ORCLE/MSFT/ALPHINC/AMZN/METAPL/NVIDIA, convert EOD price → par spread bp (flat-hazard model, 40% recovery), write `cds_today.csv` (`ticker,spread_bp`) | ✅ | stdlib only, no new deps; no changes to fetch_daily.py |
| 1.2 | Update `.github/workflows/daily-refresh.yml`: add "Fetch CDS marks" step (`continue-on-error`) before the data step; set `CDS_SOURCE` to `csv` only if that step succeeded, else `none` | ✅ | Treasury refresh unaffected if ICE is down |
| 1.3 | Add `.gitignore` for `cds_today.csv`; update README data-source section | ✅ | same commit as 1.1/1.2 per doc policy |
| 1.4 | Commit + push, trigger workflow, verify `cds` fields populated in committed data.json and tiles render on the live Pages site | ⏳ | |

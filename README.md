# Credit &amp; rates monitor

An end-of-day dashboard: 5-year CDS spreads for the big AI-capex names, plus the
Treasury par yield curve at 6M / 1Y / 2Y / 10Y / 30Y. Day, week and month
comparisons toggle in place.

GitHub refreshes the numbers every weekday morning and the page reads them.
Nothing here calls a language model — it is a Python script and a `fetch()`.

## What each file does

| File | Job |
|---|---|
| `index.html` | The dashboard. This is the page you bookmark. |
| `fetch_daily.py` | Pulls the numbers. Standard library only, no installs. |
| `.github/workflows/daily-refresh.yml` | The alarm clock. Runs the script each weekday. |
| `data.json` | Where the numbers land. The script writes it, the page reads it. |

## Setup

About fifteen minutes, once. You never need git or a terminal.

### 1. Make the repo

On github.com, click **+** (top right) → **New repository**.

- Name it `credit-rates-monitor`
- Set it to **Public** — Pages hosting is free for public repos
- Leave everything else alone, click **Create repository**

### 2. Upload the three main files

On the empty repo page, click **uploading an existing file**.

Drag in `index.html`, `fetch_daily.py` and `data.json`. Click **Commit changes**.

### 3. Add the workflow file

The workflow lives in a hidden folder, so create it by hand rather than dragging.

Click **Add file** → **Create new file**. In the filename box, type exactly:

```
.github/workflows/daily-refresh.yml
```

GitHub turns the slashes into folders as you type. Paste the contents of
`daily-refresh.yml` into the editor below, then **Commit changes**.

### 4. Let the robot write

**Settings** → **Actions** → **General** → scroll to **Workflow permissions** →
choose **Read and write permissions** → **Save**.

Skip this and the daily job will run but fail to save anything.

### 5. Turn on the web page

**Settings** → **Pages** → under **Build and deployment**, set Source to
**Deploy from a branch**, branch **main**, folder **/ (root)** → **Save**.

Wait a minute or two. Your dashboard will be at:

```
https://YOUR-USERNAME.github.io/credit-rates-monitor/
```

Bookmark it. It works on your phone too.

### 6. Fill it with data

**Actions** tab → **Daily credit and rates refresh** → **Run workflow** →
switch **backfill** to true → **Run workflow**.

That pulls a full year of Treasury history in one go. Refresh your dashboard
and the demo banner disappears.

### 7. Set your own time

The schedule is set to 10:00 UTC, which is 06:00 in New York during summer.
Open `daily-refresh.yml`, click the pencil icon, and change the `cron:` line —
the conversions for other cities are in the comments at the top.

## About the CDS numbers

Treasury yields work immediately. CDS is the awkward half: there is no free
public API for single-name credit default swaps, so out of the box the
dashboard shows Treasury data with the demo spreads still in place.

Pick one of three routes and set `CDS_SOURCE` in `daily-refresh.yml`:

**`csv`** — free, manual. Each morning you commit a `cds_today.csv` with two
columns: ticker and spread in basis points. Six lines. Works with no licence.

**`ice`** — free, a little fiddly. ICE Clear Credit publishes end-of-day
settlement prices for 5-year single names. Get the current file URL from
theice.com/cds, then add it under **Settings** → **Secrets and variables** →
**Actions** → **Variables** as `CDS_ICE_URL`. Run the job once and read the log
to check which entities it matched — ICE has changed its column headings
before, and the matching is deliberately loose.

**`vendor`** — paid. ICE Data Derivatives, S&amp;P Global Market Intelligence or
LSEG. Set `CDS_API_URL` as a variable and `CDS_API_KEY` as a *secret*, then
adjust the response mapping in `cds_from_vendor()` to match your provider's
JSON shape.

## Adding or removing companies

Both files carry the same list. Edit `ISSUERS` near the top of
`fetch_daily.py`, and the matching `ISSUERS` array near the top of the
`<script>` block in `index.html`. Keep the tickers identical in both.

## If something breaks

**Page shows the demo banner forever** — the job hasn't written real data yet.
Check the Actions tab for a red run.

**Job runs but nothing changes** — almost always step 4, workflow permissions.

**Numbers stop updating after a while** — GitHub pauses scheduled workflows in
repos with no activity for 60 days. Push any commit to wake it up.

**Dates look a day behind** — that's correct. Treasury publishes after the
close, so a morning run reports the previous session.

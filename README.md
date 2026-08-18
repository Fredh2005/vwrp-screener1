# VWRP Screener

Screens the largest constituents of **VWRP** (Vanguard FTSE All-World UCITS ETF)
on valuation, balance-sheet health, revenue growth and risk.

## Your web address

**<http://localhost:8765>** — always on, no command needed.

A launch agent (`com.vwrp.server`) starts the server at login and restarts it if
it ever dies, so the address works whenever your Mac is awake. The page shows
live prices refreshed every 60s, and the underlying screen is regenerated
**daily at 21:35** by a second agent (`com.vwrp.screener`).

```bash
launchctl list | grep vwrp        # both agents registered?
tail -20 output/refresh.log       # last few nightly runs
tail -20 output/server.log        # server issues
```

To stop either one:

```bash
launchctl unload ~/Library/LaunchAgents/com.vwrp.server.plist
launchctl unload ~/Library/LaunchAgents/com.vwrp.screener.plist
```

This address is local to your Mac — it is not reachable from other devices or
the internet. For your phone on the same wifi, see `--lan` below.

## Run it as an app

```bash
cd ~/vwrp-screener && source venv/bin/activate && python serve.py
```

Opens <http://localhost:8765> with **live-updating prices** (refreshed every
60s) and a **Refresh data** button that re-runs the whole screen.

To use it on your phone, put both devices on the same wifi and run:

```bash
cd ~/vwrp-screener && source venv/bin/activate && python serve.py --lan
```

It prints a `http://192.168.x.x:8765` address — open that on your phone, then
Share → **Add to Home Screen** for an app icon and full-screen chrome. `--lan`
exposes the app to your local network only, never the internet, and it only
works while your laptop is awake and running the command.

## Scheduled auto-refresh

A macOS launch agent re-runs the screen **daily at 21:35 local** (after the
US close), bypassing the 24h cache so fundamentals are genuinely re-pulled.
Nothing to start — it is already loaded.

```bash
launchctl list | grep vwrp          # is it registered?
tail -20 output/refresh.log         # what happened on the last runs
launchctl start com.vwrp.screener   # run it right now
```

To change the time, edit `~/Library/LaunchAgents/com.vwrp.screener.plist`, then:

```bash
launchctl unload ~/Library/LaunchAgents/com.vwrp.screener.plist && launchctl load ~/Library/LaunchAgents/com.vwrp.screener.plist
```

To stop it permanently:

```bash
launchctl unload ~/Library/LaunchAgents/com.vwrp.screener.plist && rm ~/Library/LaunchAgents/com.vwrp.screener.plist
```

It only fires while the Mac is awake. If it is asleep at 21:35, macOS runs it
shortly after wake. Runs are skipped cleanly when there is no network.

**This updates the local files only.** The hosted artifact link is a separate
thing and does not auto-update — see below.

## How fresh is the data?

| Layer | Freshness |
|---|---|
| Prices + day change | Live while `serve.py` runs, polled every 60s. Yahoo is a **delayed** feed — typically up to 15 min, varying by exchange. Not a licensed real-time feed. |
| Fundamentals (P/E, debt, growth) | As last *reported*. Companies file quarterly, so these move a few times a year, not daily. Cached 24h locally. |
| Rankings + risk scores | Recomputed only when you run the screener or press Refresh data. |
| Local files (dashboard, spreadsheet) | Regenerated daily at 21:35 by the launch agent, plus whenever you press Refresh data. |
| Opened as a file, or the hosted link | Frozen snapshot. It shows the date it was generated and says so at the top. The hosted link changes **only** when someone re-publishes it. |

Nothing updates on its own unless `serve.py` is running.

## Or just generate the files

```bash
cd ~/vwrp-screener && source venv/bin/activate && python screener.py
```

Outputs land in `output/`:

- `vwrp_screen_<date>.xlsx` — spreadsheet with autofilter, frozen panes and
  colour-coded opportunity/risk/debt/growth columns
- `dashboard.html` — interactive screener; open it in any browser (static
  snapshot when opened directly, live when served by `serve.py`)
- `artifact.html` — same page without the document wrapper, for publishing to
  a shareable URL

First run takes ~10 minutes (it fetches ~330 companies). Results are cached for
24h, so re-runs are near-instant.

## Options

```bash
python screener.py --top 100                 # narrow to the 100 largest
python screener.py --refresh                 # ignore cache, re-fetch everything
python screener.py --max-pe 20 --max-de 80   # only stocks passing these filters
python screener.py --min-growth 10           # only revenue growth above 10%
```

The dashboard has the same filters as live controls, so you usually only need
the plain `python screener.py` and then filter in the browser.

## What it measures

Every column is explained in full inside the dashboard itself — open the
**"What every column means"** panel underneath the table.

| Column | Meaning |
|---|---|
| Rank | Position by opportunity score, best first |
| Price / Day % / Cur | Latest price, move vs previous close, and quote currency |
| Opportunity score | 0–100 composite, higher is better |
| Weight % of set | Share of the holdings shown, from full market cap at live spot FX |
| P/E trailing / forward | Earnings multiple, past 12m and forward estimate |
| Debt/Equity % | Total debt as % of shareholder equity |
| Net debt/EBITDA | Leverage relative to cash earnings; >3x is stretched |
| Rev growth YoY / prior yr | Last two annual revenue growth rates |
| Rev CAGR % | Compound annual revenue growth across available years |
| Revenue trend | Accelerating / Steady / Decelerating / Recovering / Contracting |
| Risk score | 0–100 composite, lower is safer |
| Risk rating | Low <35, Moderate <50, Elevated <65, High 65+ |
| Data coverage % | How much of the risk model had data for this stock |
| Flags | Plain-English warnings (high debt, contracting revenue, etc.) |

### Opportunity score weighting

Ranks the table, best first.

| Component | Weight | Inputs |
|---|---|---|
| Value | 30% | P/E, P/B, EV/EBITDA — scored *against the stock's own sector median* |
| Growth | 30% | Revenue YoY, CAGR, trend direction |
| Quality | 25% | ROE, net margin, debt/equity, free cash flow, current ratio |
| Stability | 15% | Beta, realised volatility, max drawdown |

Valuation is scored sector-relative on purpose. Judged on raw multiples, banks
and insurers sweep the top of any value screen because they trade on
structurally low P/E and P/B by convention — which says nothing about whether
one bank is better value than another.

### Risk score weighting

Note this runs in the opposite direction: **lower is safer**.

| Component | Weight | Inputs |
|---|---|---|
| Leverage | 25% | Debt/equity, net debt/EBITDA |
| Volatility | 25% | Beta, realised 1y volatility, max drawdown |
| Valuation | 20% | Forward (or trailing) P/E, price/book |
| Growth quality | 20% | Revenue CAGR, latest YoY, trend direction |
| Profitability | 10% | ROE, net margin, free cash flow sign |

Weights are renormalised over whichever inputs have data, so a stock missing
debt figures still scores — check **Data coverage %** before leaning on it.
Banks and insurers commonly sit at 75% because debt/equity is not meaningful
for them.

## Limitations worth knowing

- **The holdings list is an approximation.** Vanguard puts the full constituent
  list behind an account gate, so `universe.csv` holds ~330 global large-caps as
  candidates; the script ranks them by live market cap and keeps the top N. That
  mirrors how a cap-weighted index allocates, but FTSE weights by *free float*,
  so exact weights differ. Edit `universe.csv` freely — one Yahoo ticker per
  line — or paste in Vanguard's official list if you obtain it.
- **Weight % is share of the shown set, not of the fund.** VWRP holds ~3,750
  stocks; the top 150 are roughly half the fund. A name at 6% here is nearer 3%
  of the actual ETF.
- **Fundamentals lag.** Yahoo Finance reports as last filed, so figures can be a
  quarter behind.
- P/E, debt/equity, margins and growth are ratios and so currency-neutral.
  Market caps are converted to USD at spot FX.
- **The opportunity score rewards cheap multiples**, so it will surface value
  traps and cyclicals at peak earnings alongside genuine bargains. A high rank
  is a prompt to look closer, not a conclusion. Read the Flags column and the
  risk rating next to it.
- Dual listings are de-duplicated (HSBC trades in both London and Hong Kong);
  the larger listing is kept.
- One ticker (`MMC`, Marsh & McLennan) currently fails Yahoo's quote endpoint and
  is skipped. Others recover automatically via the retry sweeps.

Not investment advice.

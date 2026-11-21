# Whisper Beast 2026 — Build Tracker

A live price tracker for my custom PC build. Tracks current prices on every part, shows a running total vs budget, and keeps a price history per part.

**Live dashboard**: https://emckenna.github.io/my-new-build/

## How it works

- `parts.json` defines the build — parts, target prices, retailer links, and Pricify part numbers
- A GitHub Actions cron job runs every 4 hours (GitHub usually fires it 2–3 times a day), fetches prices, and commits `prices.json` and `price_history.json` back to the repo
- GitHub Pages serves `index.html`, which reads those files and renders the dashboard
- Prices older than 48 hours (9 days for Pricify, which publishes weekly) don't count toward the total and show struck through on the dashboard

## Price sources

| Source | How | Status |
|---|---|---|
| Amazon | camelcamelcamel alerts RSS feed (`CCC_RSS_URL` secret), matched by ASIN | Working — add a CCC alert for each part's Amazon link |
| [Pricify](https://pricify.ai) | Weekly open data on [GitHub](https://github.com/pricify-ai/pc-hardware-prices) (CC BY 4.0), matched by part number | Working — top 100 products per category only |
| Newegg | Page scrape | Blocked (403) since Oct 2026 |
| Micro Center | Page scrape | Blocked (403) since Oct 2026 |

## Repo structure

```
parts.json                      # build definition (source of truth)
prices.json                     # last fetched prices (written by Action)
price_history.json              # daily price history (written by Action)
index.html                      # dashboard
style.css                       # dashboard styles
fetch.sh                        # run the fetch locally (sets up .venv)
scripts/
  fetch_prices.py               # price fetch script
.github/
  workflows/
    fetch-prices.yml            # cron every 4h + on-demand dispatch
```

## Viewing the dashboard locally

Browsers block a page opened from a local file (`file://`) from loading the JSON files, so serve the folder instead:

```bash
python3 -m http.server
```

Then open http://localhost:8000.

## Running the price fetch locally

```bash
CCC_RSS_URL=xxx ./fetch.sh
```

Omit `CCC_RSS_URL` to skip Amazon prices. Pass `--dry-run` to `scripts/fetch_prices.py` to fetch without writing files. Newegg and Micro Center block most home and server IPs, so expect 403s for those.

Telegram alerts are currently turned off (the `send_telegram` call is commented out); the summary message is printed instead.

## Triggering a manual price fetch

Via the GitHub Actions UI: **Actions → Fetch Prices → Run workflow**

Or with the GitHub CLI:

```bash
gh workflow run fetch-prices.yml
```

Or via the API:

```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/emckenna/my-new-build/actions/workflows/fetch-prices.yml/dispatches \
  -d '{"ref":"main"}'
```

## Updating the build

Edit `parts.json` and push. The bot commits on every run, so pull first. The dashboard redeploys automatically.

- `"in_build": false` keeps a part tracked but leaves it out of the total (used for the deferred GPU and for alternatives)
- `"alternative_to": "<part id>"` shows how much swapping that part in would save or cost
- The Amazon link must point to the exact product — the CCC price is matched on its ASIN

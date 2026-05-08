# Whisper Beast 2026 — Build Tracker

A live price tracker for my custom PC build. Tracks current prices on variable-cost parts, shows a running total vs budget, and sends Telegram alerts when prices move.

**Live dashboard**: https://emckenna.github.io/my-new-build/

## How it works

- `parts.json` defines the build — part names, target prices, and pcprice.watch endpoints
- A GitHub Actions cron job runs daily, fetches current prices, and commits `prices.json` back to the repo
- GitHub Pages serves `index.html`, which reads both files and renders the dashboard
- Telegram alerts fire when any part price moves more than 2%

## Repo structure

```
parts.json                      # build definition (source of truth)
prices.json                     # last fetched prices (written by Action)
index.html                      # dashboard
style.css                       # dashboard styles
scripts/
  fetch_prices.py               # price fetch script
.github/
  workflows/
    fetch-prices.yml            # daily cron + on-demand dispatch
```

## Running the price fetch locally

```bash
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python3 scripts/fetch_prices.py
```

Omit the env vars to skip the Telegram notification.

## Triggering a manual price fetch

Via the GitHub Actions UI: **Actions → Fetch Prices → Run workflow**

Or via the API:

```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/emckenna/my-new-build/actions/workflows/fetch-prices.yml/dispatches \
  -d '{"ref":"main"}'
```

## Updating the build

Edit `parts.json` directly and push. The dashboard redeploys automatically.

# my-new-build

PC price tracker for the **Whisper Beast 2026** custom build. Tracks live prices on variable-cost parts, displays a dashboard vs budget and prebuilts, and sends Telegram alerts when prices move.

## What this project is

- **Not a web app framework project.** No Node, no npm, no build step. Plain HTML + vanilla JS + Python.
- **GitHub Pages** hosts `index.html` (static, auto-deploys on push to main).
- **GitHub Actions** runs the daily price fetch cron and handles on-demand dispatch.
- **No Vercel, no Firebase, no external KV.** Entirely free infrastructure.

## Key files

| File | Purpose |
|---|---|
| `parts.json` | Source of truth — build definition, part list, target prices, pcprice.watch URLs |
| `prices.json` | Last fetched prices — written by GitHub Action, committed back to repo |
| `index.html` | Dashboard — reads parts.json + prices.json, renders table + totals |
| `scripts/fetch_prices.py` | Price fetcher — hits pcprice.watch, writes prices.json, sends Telegram |
| `.github/workflows/fetch-prices.yml` | Action — daily cron at 14:00 UTC + workflow_dispatch |

## The build

**Whisper Beast 2026** — quiet 1440p gaming + same-box Twitch streaming + Portal SDK dev.

- Budget: **$3,100**
- Variable parts (prices tracked): CPU, GPU, RAM
- Fixed-price components: cooler, motherboard, storage, case, PSU, fans, OS (~$1,130 total)
- Price source: `https://www.pcprice.watch/data/{model_id}_market_data.json`
- Flat threshold: <2% change = no movement

## Data flow

1. GitHub Actions cron runs `fetch_prices.py` daily
2. Script hits pcprice.watch for each part in `parts.json`
3. Compares to previous `prices.json`, determines movement (up/flat/down)
4. Writes updated `prices.json`, commits it back to repo
5. Sends Telegram alert if any part moved (via Sharona's bot token)
6. GitHub Pages redeploys with fresh `prices.json`

## Sharona integration

Sharona (Eric's OpenClaw agent on dobby) can:
- Trigger on-demand price fetch via `workflow_dispatch` GitHub API
- Edit `parts.json` and push to swap parts
- Read `prices.json` inline to answer "what's my build total?"

Secrets needed in GitHub repo:
- `TELEGRAM_BOT_TOKEN` — Sharona's existing bot token
- `TELEGRAM_CHAT_ID` — Eric's chat ID with Sharona

## Open items

- [ ] Validate pcprice.watch model IDs: `ryzen_7_9850x3d` and `ddr5_64gb_6000` (unconfirmed — may need adjustment)
- [ ] Confirm pcprice.watch response shape for `extract_price()` in `fetch_prices.py`
- [ ] Add GitHub PAT for Sharona (needs `repo` + `actions` scope, store on dobby)
- [ ] Confirm Telegram chat ID for Action notifications
- [ ] Enable GitHub Pages on repo (Settings → Pages → Deploy from main branch)

## Rules for editing

- **Do not add a build system.** No webpack, vite, parcel, etc.
- **Do not add a backend server.** The Action is the only "backend."
- **`parts.json` is human-editable** — keep the schema clean and flat.
- **`prices.json` is machine-written** — don't hand-edit it; run the script.
- Dashboard must work by opening `index.html` directly (file://) or via GitHub Pages — no dev server required.

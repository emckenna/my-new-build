# My New Build — Stack & Architecture Handoff
**Date**: May 8, 2026  
**Companion doc**: `my-new-build-handoff.md` (project context, schema, build data)

---

## Chosen Stack

| Layer | Technology | Why |
|---|---|---|
| Source of truth | `parts.json` in GitHub repo | Flat, human-editable, DB-ready later |
| Parts updates | Sharona → git push | Already has exec/write/git on dobby |
| Price fetching | GitHub Actions cron | Free, no external platform |
| Price history | `prices.json` committed by Action | Simple, no KV service needed |
| Dashboard hosting | GitHub Pages | Free static hosting, auto-deploys on push |
| Telegram alerts | GitHub Action → Telegram Bot API | Direct, uses Sharona's existing bot token |
| On-demand triggers | Sharona → GitHub API workflow_dispatch | Fire price fetch or updates on demand |

**No Vercel. No Firebase. No external KV service. Entirely free.**

---

## Repo Structure

```
my-new-build/
  parts.json              <- build definition (Sharona edits this)
  prices.json             <- last fetched prices (Action writes this)
  index.html              <- dashboard (plain HTML + vanilla JS)
  scripts/
    fetch_prices.py       <- price fetch logic (called by Action)
  .github/
    workflows/
      fetch-prices.yml    <- cron + on-demand price fetch
```

---

## Data Flow

### 1. Sharona updates a part
```
Eric: "Sharona, swap the GPU to RX 9070 XT"
  -> Sharona edits parts.json on dobby
  -> git commit + git push to my-new-build
  -> GitHub Pages auto-redeploys dashboard
```

Sharona's exec call:
```bash
git -C ~/github/my-new-build add parts.json
git -C ~/github/my-new-build commit -m "Swap GPU to RX 9070 XT"
git -C ~/github/my-new-build push
```

### 2. Scheduled price fetch (daily)
```
GitHub Actions cron (daily)
  -> fetch-prices.yml runs
  -> hits market_url for each part in parts.json
  -> compares to prices.json (last known)
  -> writes updated prices.json
  -> commits prices.json back to repo
  -> if movement detected -> sends Telegram alert
  -> GitHub Pages redeploys with fresh prices.json
```

### 3. Eric requests on-demand price check
```
Eric: "Sharona, check prices now"
  -> Sharona calls GitHub API workflow_dispatch
  -> fetch-prices.yml runs immediately
  -> same flow as above
  -> Telegram summary sent back
```

Sharona's exec call:
```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/OWNER/my-new-build/actions/workflows/fetch-prices.yml/dispatches \
  -d '{"ref":"main"}'
```

### 4. Dashboard live view
```
Browser loads index.html (served by GitHub Pages)
  -> reads prices.json (last fetched, committed by Action)
  -> reads parts.json (build definition)
  -> optionally fetches live market_url per part (client-side)
  -> renders table: name / target / last price / live price / movement
  -> shows running total vs budget vs prebuilts
```

---

## prices.json Schema

```json
{
  "last_fetched": "2026-05-08T14:00:00Z",
  "parts": {
    "cpu": {
      "last_price": 499.00,
      "previous_price": 514.00,
      "movement": "down",
      "source": "pcprice.watch"
    },
    "gpu": {
      "last_price": 1202.00,
      "previous_price": 1249.00,
      "movement": "down",
      "source": "pcprice.watch"
    },
    "ram": {
      "last_price": 189.00,
      "previous_price": 189.00,
      "movement": "flat",
      "source": "pcprice.watch"
    }
  }
}
```

Movement values: `"up"` / `"flat"` / `"down"`. Threshold for flat: <2% change.

---

## fetch-prices.yml

```yaml
name: Fetch Prices

on:
  schedule:
    - cron: '0 14 * * *'
  workflow_dispatch:

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Fetch prices
        run: python3 scripts/fetch_prices.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

      - name: Commit updated prices.json
        run: |
          git config user.name "price-bot"
          git config user.email "bot@noreply"
          git add prices.json
          git diff --staged --quiet || git commit -m "chore: update prices $(date -u +%Y-%m-%d)"
          git push
```

---

## Telegram Notification Format

```
🟢 RTX 5080 dropped $47 → now $1,202 (was $1,249)
🔴 Ryzen 9850X3D up $15 → now $514 (was $499)
➖ DDR5 64GB — no change ($189)
──────────────────────────────
Build total:  $3,021  ↓ $32 vs yesterday
vs budget:    $79 under
vs Skytech:   $678 cheaper (64GB/4TB config)
```

---

## Secrets Required

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Sharona's existing bot token |
| `TELEGRAM_CHAT_ID` | Eric's Telegram chat ID with Sharona |
| `GITHUB_TOKEN` | Auto-provided by Actions |

Sharona's on-demand dispatch needs a Personal Access Token with `repo` and `actions` scope. Store on dobby as an env var.

---

## Sharona Skill (Future, Optional)

| Eric says | Sharona does |
|---|---|
| "Check prices" | Triggers workflow_dispatch via GitHub API |
| "Swap GPU to X" | Edits parts.json, commits, pushes |
| "What's my build total?" | Reads prices.json + parts.json, replies inline |
| "Show build status" | Posts dashboard URL to Telegram |

---

## Open Items

1. Validate model_ids — `ryzen_7_9850x3d` and `ddr5_64gb_6000` unconfirmed on pcprice.watch
2. GitHub PAT for Sharona — generate token, store on dobby
3. Telegram chat ID — confirm Eric's chat ID for Action notifications
4. Movement threshold — 2% proposed for flat, adjust to taste
5. Live vs cached — decide if dashboard hits pcprice.watch client-side or relies on prices.json

---

## Suggested Build Order

1. Create `my-new-build` repo, commit `parts.json`
2. Enable GitHub Pages
3. Write `scripts/fetch_prices.py`
4. Add `.github/workflows/fetch-prices.yml`
5. Add secrets to repo
6. Test via manual `workflow_dispatch` in GitHub UI
7. Build `index.html` dashboard
8. Add Sharona skill (optional, last)
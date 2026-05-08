# PC Price Tracker — Project Handoff
**Date**: May 8, 2026  
**Continuing from**: Claude conversation (no project)  
**Continuing in**: New Claude project  

---

## What This Is

A Vercel-hosted live dashboard and price-tracking app for a custom PC build. The app shows the current proposed build, fetches live pricing from pcprice.watch, displays a running total, and shows per-part price movement indicators (up / flat / down). When prices move, it notifies Eric via Telegram through Sharona (his OpenClaw agent, already running on dobby).

---

## Current State

### Done
- **`parts.json` schema locked** — the source of truth for the build definition
- **`parts.json` populated** — full build entered from the May 2026 build doc
- **Price source identified** — pcprice.watch provides structured JSON endpoints:
  - `https://www.pcprice.watch/data/{model_id}_market_data.json` — live listings, current lowest price
  - `https://www.pcprice.watch/data/{model_id}_sales_data.json` — historical sold prices, percentiles, 7/30/90-day medians
- **`parse_seed.py`** — converts a PCPartPicker markdown export into `parts.json` format
- **`parse_custom_build.py`** — converts a custom build markdown doc into `parts.json` format

### Not Started
- Vercel app / repo setup
- Frontend dashboard (live view)
- Serverless cron function (price fetching + KV storage)
- Telegram notification via Sharona's bot
- `validate_endpoints.py` — confirms pcprice.watch model_ids return 200 before committing

---

## The parts.json Schema

```json
{
  "_meta": {
    "generated": "2026-05-08",
    "schema_version": "1.0"
  },
  "build": {
    "name": "Whisper Beast 2026",
    "description": "...",
    "budget": 3100,
    "last_updated": "2026-05-08"
  },
  "parts": [
    {
      "id": "cpu",
      "name": "AMD Ryzen 7 9850X3D",
      "category": "cpu",
      "description": "...",
      "target_price": 499,
      "model_id": "ryzen_7_9850x3d",
      "market_url": "https://www.pcprice.watch/data/ryzen_7_9850x3d_market_data.json",
      "last_price": null,
      "last_checked": null,
      "alt_urls": []
    }
  ],
  "extras": [
    {
      "id": "cooler",
      "name": "Arctic Liquid Freezer III 360",
      "category": "cpu cooler",
      "description": "...",
      "fixed_price": 130
    }
  ],
  "prebuilts": [
    {
      "id": "skytech-32",
      "name": "Skytech King 95 (32GB/2TB)",
      "cpu": "Ryzen 7 9800X3D",
      "ram": "32GB",
      "storage": "2TB",
      "price": 2999,
      "note": "Half RAM, half storage, older CPU"
    }
  ]
}
```

### Schema rules
- **`parts`** — trackable components with pcprice.watch endpoints. `last_price` and `last_checked` are null until the first cron run.
- **`extras`** — fixed-cost components (no price tracking). Contribute to total via `fixed_price`.
- **`prebuilts`** — comparison systems. Displayed alongside custom build total.
- **`alt_urls`** — reserved for additional price sources per part. Empty array for now, no logic built around it yet.
- The schema is intentionally flat — designed to migrate cleanly to a DB table later without restructuring.

---

## Current Build Summary

| Role | Part | Target | Street |
|---|---|---|---|
| CPU | AMD Ryzen 7 9850X3D | $499 | $499 |
| GPU | MSI RTX 5080 Ventus 3X OC 16GB | $999 (MSRP) | ~$1,249 |
| RAM | Corsair Vengeance 64GB DDR5-6000 CL40 | $196 | $196 |
| Cooler | Arctic Liquid Freezer III 360 | — | $130 |
| Motherboard | ASRock X870 LiveMixer WiFi | — | $230 |
| Storage | WD Black SN850X 4TB NVMe Gen4 | — | $260 |
| Case | Fractal Design Define 7 Compact | — | $140 |
| PSU | Corsair RM1000e 1000W 80+ Gold | — | $150 |
| Fans | Noctua NF-A12x25 PWM 3-Pack | — | $80 |
| OS | Windows 11 Pro | — | $140 |
| **Total** | | **$2,824** at MSRP | **~$3,074** at street |

Budget: $3,100. The $250 GPU gap (MSRP vs street) is the primary signal to watch.

---

## Planned App Architecture

```
GitHub repo (pc-price-tracker)
  parts.json              ← build definition, committed manually when build changes
  src/
    app/                  ← frontend dashboard (Next.js or plain HTML)
    functions/
      fetch-prices.js     ← Vercel cron: fetches prices, updates KV, fires Telegram
```

**Data flow:**
1. Page loads → reads `parts.json` → fetches live `market_url` per tracked part
2. Compares current price to `last_price` in Vercel KV → renders up/flat/down indicator
3. Sums tracked parts (live price) + extras (fixed_price) → current total
4. Cron runs daily → detects movement → sends Telegram message if threshold crossed

**Price movement storage:** Vercel KV (not git commits). Keeps `parts.json` as a clean build definition, not a price log.

**Telegram notifications:** App calls the Telegram Bot API directly using Sharona's existing bot token. Sharona doesn't need an OpenClaw skill for this — the message just appears in Eric's existing Telegram chat with her.

**Notification format:**
```
🟢 RTX 5080 dropped $47 → now $1,202 (was $1,249)
🔴 Ryzen 7 9850X3D up $15 → now $514
─────────────────────────────────
Build total: $2,987 ↓ $32 since yesterday
```

---

## pcprice.watch API Notes

- Endpoints confirmed working: `rx6600`, `rtx4070`, `ryzen_7_5800x`
- GPU model_id format: no separators, all lowercase (`rtx5080`, `rx6600`, `rtx5060ti`)
- CPU model_id format: underscores (`ryzen_7_5800x`, `i5_14600k`)
- RAM model_id format: unknown — `ddr5_64gb_6000` is a guess, needs validation
- `ryzen_7_9850x3d` is unconfirmed — chip launched Jan 2026, may not be in their catalog yet
- Updates every 8 hours, Euro-centric site — prices may show EUR even for US listings, normalize in fetch logic
- Both `_market_data.json` (current listings) and `_sales_data.json` (sold history + percentiles) confirmed working
- Buy signal logic: compare current lowest (`_market_data`) to 90-day p25 (`_sales_data`) — at or below p25 = buy signal

---

## Open Items

1. **Validate model_ids** — write `validate_endpoints.py`, fire HEAD requests against all `market_url` fields, flag 404s. `ryzen_7_9850x3d` and `ddr5_64gb_6000` are the uncertain ones.
2. **Alt URLs** — `alt_urls: []` is reserved per part for additional price sources. No logic built yet.
3. **DB migration** — schema is flat and DB-ready. Migration deferred until app outgrows JSON.
4. **Swapping parts** — three options discussed: edit JSON directly, tell Sharona to update it, or admin UI in the dashboard. Not decided yet.
5. **Buy signal threshold** — what % movement triggers a Telegram alert. Not configured.
6. **Prebuilt price tracking** — prebuilts currently have a single static price. Could add `market_url` per prebuilt later for live comparison.

---

## Sharona / OpenClaw Context

- Sharona runs on **dobby** (Ubuntu 24.04, IP 10.0.0.139), managed via `sudo systemctl restart openclaw-gateway.service`
- Communicates via Telegram **@mysharona_oc_bot**
- Uses `google/gemini-2.5-flash` via Google provider
- Skill deployment: `~/github/occ-mymentor/skills/` → `deploy-skills` → `update-mentor`
- The pc-price-tracker Telegram notifications use Sharona's bot token directly — no new OpenClaw skill needed for notifications
- If a "check my build prices" conversational skill is wanted later, it would follow the same SKILL.md pattern as existing occ-mymentor skills

---

## Files Produced This Session

| File | Purpose |
|---|---|
| `parts.json` | Current build definition, schema source of truth |
| `parse_seed.py` | Parses PCPartPicker markdown export → parts.json |
| `parse_custom_build.py` | Parses custom build markdown doc → parts.json |

All three should live in the `pc-price-tracker` repo once it's created.

---

## Suggested Next Steps

1. Create `pc-price-tracker` GitHub repo, commit `parts.json`
2. Run `validate_endpoints.py` (write it first) to confirm pcprice.watch coverage
3. Scaffold Vercel project — Next.js or plain HTML, connect to GitHub repo
4. Build the frontend dashboard (live price fetch + movement indicators + total)
5. Add Vercel KV for last-price storage
6. Write `fetch-prices.js` serverless cron function
7. Wire up Telegram notifications using Sharona's bot token

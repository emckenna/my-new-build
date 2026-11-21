# my-new-build

PC price tracker for the **Whisper Beast 2026** custom build. Tracks live prices on every part, displays a dashboard vs budget, and (once re-enabled) sends Telegram alerts when prices move.

## What this project is

- **Not a web app framework project.** No Node, no npm, no build step. Plain HTML + vanilla JS + Python.
- **GitHub Pages** hosts `index.html` (static, auto-deploys on push to main): https://emckenna.github.io/my-new-build/
- **GitHub Actions** runs the price fetch cron and handles on-demand dispatch.
- **No Vercel, no Firebase, no external KV.** Entirely free infrastructure.

## Key files

| File | Purpose |
|---|---|
| `parts.json` | Source of truth — build definition, parts, target prices, retailer URLs, Pricify part numbers |
| `prices.json` | Last fetched prices per part/retailer, with per-retailer `fetched_at` — written by the Action |
| `price_history.json` | One entry per part per day (fresh prices only) — written by the Action, drives the sparklines |
| `index.html` + `style.css` | Dashboard — reads the three JSON files, renders table, totals, cost chart |
| `scripts/fetch_prices.py` | Price fetcher — scrapes/reads all sources, writes prices + history |
| `fetch.sh` | Local runner — creates `.venv`, installs deps, runs the fetcher |
| `.github/workflows/fetch-prices.yml` | Action — cron every 4h (GitHub actually fires ~2–3×/day) + `workflow_dispatch` |

## The build

**Whisper Beast 2026** — quiet (<26 dBA) 1440p gaming + same-box Twitch streaming + Portal SDK dev, on AM5.

- Budget: **$3,100**
- `parts` (price-tracked): CPU, GPU, RAM, motherboard, storage, case, PSU, plus alternatives
- `extras` (fixed price): cooler, fans, OS
- Replaces TYRANT1 (i7-6850K / X99 / DDR4, RTX 3080 12GB, all-SATA storage). The 3080, SATA SSDs and possibly the Win10 Pro key carry over; DDR4 and the Asetek AIO do not.

### Build decisions (Nov 2026)

- **RTX 5080 deferred** — keeping the 3080 for now (`in_build: false`). Still tracked so a drop toward target is visible.
- **Alternatives tracked side by side** (`in_build: false` + `alternative_to`): 32GB RAM kit vs 64GB, 2TB SN850X vs 4TB. Undecided — the dashboard shows the swap delta.
- **OS priced at $0** assuming the Win10 Pro key is retail and transfers (OEM keys don't; then it's ~$140).

## parts.json schema

Per part: `id`, `name`, `category`, `description`, `url`, `target_price`, `retailers` (`newegg` / `microcenter` / `amazon` URL or null), `pricify` (`site` + maker `part_number`), and optionally:

- `in_build: false` — tracked and shown under "Watching", but excluded from the build total, cost chart, total sparkline, and Telegram total
- `alternative_to: "<part id>"` — dashboard shows "Swap for X: saves/costs $N"
- `note` — shown under the part name

Amazon prices are matched by the `/dp/<ASIN>` in the Amazon URL, so **the ASIN must be the exact product** (we've had wrong-variant ASINs: Define 7 XL, 5080 White).

## Price sources

| Source | Key in prices.json | How | Status |
|---|---|---|---|
| Newegg | `newegg` | HTML scrape (`urllib`) | **403 from GitHub runners since ~2026-10-14** |
| Micro Center | `microcenter` | HTML scrape (`cloudscraper`) | **403 since ~2026-10-14** |
| Amazon via camelcamelcamel | `amazon` (`amazon_3p` reserved) | CCC alerts RSS feed (`CCC_RSS_URL` secret), matched by ASIN | Working. Eric adds an alert on CCC per ASIN. Feed titles don't say Amazon vs 3rd-party, so 3P alerts land in `amazon` too; newest item per ASIN wins |
| Pricify | `pricify` (+ `pricify_store`, `pricify_url`) | Weekly JSON from `github.com/pricify-ai/pc-hardware-prices` (`latest/json/<site>.json`), matched by `part_number` | Working. Top-100 products per category only; store prices only (often Micro Center in-store). CC BY 4.0 — keep the credit in the dashboard footer |

pcprice.watch (used eBay sold prices) is **not** used — its `/data/{model}_market_data.json` endpoints 404. A free Best Buy Products API key (developer.bestbuy.com) is a possible future source.

### Staleness

Every retailer price has a timestamp in `fetched_at`. Failed fetches carry the old price and old timestamp forward. Only **fresh** prices count toward `lowest_price`, history, and totals: within 48h, or 9 days for Pricify (weekly releases, dated by Pricify's own day, not download time). If a part has no fresh price, `stale: true` and the stale minimum is used; the dashboard strikes stale prices through. The 48h/9-day windows exist in both `fetch_prices.py` and `index.html` — keep them in sync.

## Data flow

1. Action runs `fetch_prices.py` (deps: `beautifulsoup4`, `cloudscraper`)
2. Script reads CCC RSS + Pricify JSON once, then tries Newegg/Micro Center per part
3. Computes lowest fresh price, movement vs previous (<2% = flat), stale flag
4. Writes `prices.json` + `price_history.json`; the Action commits them (`chore: update prices …`) and pushes
5. GitHub Pages redeploys

The bot commits on every run, so **pull before editing** and expect to rebase.

## Telegram

`send_telegram(msg)` is **commented out** in `main()` — no alerts are being sent. The message is still built and printed to the Action log. Secrets `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (Sharona's bot, Eric's chat) are wired into the workflow.

## Sharona integration

Sharona (Eric's OpenClaw agent on dobby) can trigger `workflow_dispatch`, edit/push `parts.json`, and read `prices.json` to answer "what's my build total?" — she should sum only `in_build` parts plus `extras`, using `lowest_price`.

## Open items

- [ ] Newegg/Micro Center 403s — find a working approach or drop them
- [ ] Add CCC alert for the corrected Define 7 ASIN `B08146JLXK`
- [ ] Pick the right Amazon listing for the RTX 5080 Ventus 3X OC (current `B0DSWQNGYF` is the White edition)
- [ ] Decide RAM (32 vs 64GB) and storage (2 vs 4TB), then flip `in_build`
- [ ] Re-enable Telegram (and consider alerting on target-price crossings, not just >2% step moves)
- [ ] Optional: Best Buy API source (needs key as a repo secret)
- [ ] GitHub PAT for Sharona (`repo` + `actions` scope, store on dobby)

## Rules for editing

- **Do not add a build system.** No webpack, vite, parcel, etc.
- **Do not add a backend server.** The Action is the only "backend."
- **`parts.json` is human-editable** — keep the schema clean and flat.
- **`prices.json` / `price_history.json` are machine-written** — don't hand-edit them; run the script.
- Dashboard must work by opening `index.html` directly (file://) or via GitHub Pages — no dev server required.
- Retailers block local/dev IPs too, so a local fetch can't validate scraper changes; test with mocked fetchers, then verify via a dispatched Action run.

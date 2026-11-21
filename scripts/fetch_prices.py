#!/usr/bin/env python3
"""
Fetch current prices from Newegg and Microcenter for all tracked parts,
update prices.json, and send a Telegram summary if prices moved.

Dependencies: beautifulsoup4 cloudscraper (pip install beautifulsoup4 cloudscraper)
"""

import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import cloudscraper
from bs4 import BeautifulSoup

PARTS_FILE = "parts.json"
PRICES_FILE = "prices.json"
HISTORY_FILE = "price_history.json"
FLAT_THRESHOLD = 0.02
STALE_HOURS = 48
RETAILERS = ("newegg", "microcenter", "amazon", "amazon_3p")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CCC_RSS_URL = os.environ.get("CCC_RSS_URL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_html_mc(url):
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_ccc_rss():
    """Fetch the CCC alerts RSS feed and return {asin: {"amazon"|"amazon_3p": price}}."""
    content = fetch_html(CCC_RSS_URL)
    root = ET.fromstring(content)
    prices = {}
    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        print(f"  CCC item: {title}")

        # Serialize description back to string so href attributes are preserved
        desc_el = item.find("description")
        desc_raw = ET.tostring(desc_el, encoding="unicode") if desc_el is not None else ""

        asin_m = re.search(r"camelcamelcamel\.com/product/([A-Z0-9]{10})(?![A-Z0-9])", desc_raw)
        if not asin_m:
            continue

        price_m = re.search(r"\$([\d,]+\.?\d*)", title)
        if not price_m:
            price_m = re.search(r"currently:\s*\$([\d,]+\.?\d*)", desc_raw)
        if not price_m:
            continue

        text = (title + " " + desc_raw).lower()
        if re.search(r"\bused\b", text):
            continue
        kind = "amazon_3p" if re.search(r"3rd party|third party", text) else "amazon"

        # Feed is newest-first; keep the most recent price for each ASIN + price type
        prices.setdefault(asin_m.group(1), {}).setdefault(
            kind, float(price_m.group(1).replace(",", ""))
        )
    return prices


def parse_newegg(html):
    soup = BeautifulSoup(html, "html.parser")

    # First-party price (Newegg direct listing)
    el = soup.select_one(".price-new-right")
    if el:
        text = el.get_text(" ", strip=True)
        m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
        if m:
            return float(m.group().replace(",", ""))

    # Fallback: JSON-LD structured data
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
            offers = data.get("offers") or data.get("Offers")
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
                if price:
                    return float(price)
        except Exception:
            pass

    raise ValueError("Price not found on Newegg page")


def parse_microcenter(html):
    soup = BeautifulSoup(html, "html.parser")

    # Primary: itemprop="price"
    el = soup.find(itemprop="price")
    if el:
        content = el.get("content") or el.get_text(strip=True)
        m = re.search(r"[\d,]+\.?\d*", content.replace(",", ""))
        if m:
            return float(m.group().replace(",", ""))

    # Fallback: span with content attribute (e.g. <span content="439.99" id="pricing2">)
    el = soup.select_one("span[content]")
    if el:
        content = el.get("content", "")
        m = re.search(r"[\d,]+\.?\d*", content.replace(",", ""))
        if m:
            return float(m.group().replace(",", ""))

    # Fallback: #pricing span or .price span
    for selector in ("#pricing span", ".price span", ".pricemain"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
            if m:
                return float(m.group().replace(",", ""))

    # Fallback: JSON-LD structured data (present even when out of stock)
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
            if data.get("@type") == "Product":
                price = data.get("offers", {}).get("price")
                if price:
                    return float(price)
        except Exception:
            pass

    raise ValueError("Price not found on Microcenter page")


PARSERS = {
    "newegg": parse_newegg,
    "microcenter": parse_microcenter,
}


FETCHERS = {
    "microcenter": fetch_html_mc,
}


def fetch_price(retailer, url):
    fetcher = FETCHERS.get(retailer, fetch_html)
    html = fetcher(url)
    return PARSERS[retailer](html)


def load_previous():
    try:
        with open(PRICES_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"parts": {}}


def load_history():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def is_fresh(fetched_at, now):
    if not fetched_at:
        return False
    age = now - datetime.fromisoformat(fetched_at)
    return age.total_seconds() < STALE_HOURS * 3600


def fresh_prices(data, now):
    """Retailer prices in a part result that were fetched within STALE_HOURS."""
    fetched = data.get("fetched_at", {})
    return {r: data[r] for r in RETAILERS if data.get(r) is not None and is_fresh(fetched.get(r), now)}


def append_history(history, results, date_str, now):
    for part_id, data in results.items():
        entry = {"date": date_str, **fresh_prices(data, now)}
        if data.get("lowest_price") is not None and not data.get("stale"):
            entry["lowest"] = data["lowest_price"]
        if part_id not in history:
            history[part_id] = []
        # One entry per date; later runs that day replace it
        if history[part_id] and history[part_id][-1]["date"] == date_str:
            history[part_id][-1] = entry
        else:
            history[part_id].append(entry)
    return history


def movement(old, new):
    if old is None:
        return "new"
    change = (new - old) / old
    if abs(change) < FLAT_THRESHOLD:
        return "flat"
    return "up" if new > old else "down"


def format_telegram(results, parts_meta, budget, extras_total, now):
    lines = []
    variable_total = 0
    any_moved = False

    for part_id, data in results.items():
        lowest = data.get("lowest_price")
        prev = data.get("previous_lowest")
        mov = data.get("movement", "new")
        name = parts_meta[part_id]["name"]
        if not parts_meta[part_id].get("in_build", True):
            name += " (not in build)"
        icon = {"up": "🔴", "down": "🟢", "flat": "➖", "new": "🆕"}.get(mov, "➖")

        labels = {"newegg": "NE", "microcenter": "MC", "amazon": "AMZ", "amazon_3p": "AMZ-3P"}
        prices_str = "  ".join(f"{labels[r]} ${p:.0f}" for r, p in fresh_prices(data, now).items())
        if data.get("stale"):
            prices_str = f"stale — last seen at {data.get('lowest_at')}"

        if lowest is None:
            lines.append(f"⚠️ {name} — no price fetched")
            continue

        if mov in ("up", "down") and prev is not None:
            delta = abs(lowest - prev)
            direction = "dropped" if mov == "down" else "up"
            lines.append(f"{icon} {name} {direction} ${delta:.0f} → ${lowest:.0f}  [{prices_str}]")
            any_moved = True
        else:
            lines.append(f"{icon} {name} — ${lowest:.0f}  [{prices_str}]")

        if parts_meta[part_id].get("in_build", True):
            variable_total += lowest

    grand_total = variable_total + extras_total
    vs_budget = budget - grand_total

    lines.append("─" * 36)
    lines.append(f"Build total:  ${grand_total:,.0f}")
    lines.append(f"vs budget:    ${vs_budget:+,.0f}")

    return "\n".join(lines), any_moved


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, skipping.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("Telegram sent:", resp.status)


def main(dry_run=False):
    if dry_run:
        print("--- DRY RUN: no files will be written ---")
    with open(PARTS_FILE) as f:
        build = json.load(f)

    previous = load_previous()
    prev_parts = previous.get("parts", {})
    extras_total = sum(e["fixed_price"] for e in build.get("extras", []))

    ccc_prices = {}
    if CCC_RSS_URL:
        try:
            ccc_prices = fetch_ccc_rss()
            print(f"CCC RSS: {len(ccc_prices)} Amazon prices fetched")
        except Exception as e:
            print(f"CCC RSS ERROR: {e}")

    now = datetime.now(timezone.utc)
    results = {}
    parts_meta = {}

    for part in build["parts"]:
        part_id = part["id"]
        parts_meta[part_id] = part
        retailers = part.get("retailers", {})
        prev = prev_parts.get(part_id, {})
        prev_fetched = prev.get("fetched_at", {})
        part_result = {}
        fetched_at = {}

        def carry_forward(retailer):
            if retailer in prev:
                part_result[retailer] = prev[retailer]
                if retailer in prev_fetched:
                    fetched_at[retailer] = prev_fetched[retailer]

        for retailer, url in retailers.items():
            if not url or retailer == "amazon":
                continue
            print(f"Fetching {part['name']} from {retailer} ...")
            try:
                price = fetch_price(retailer, url)
                part_result[retailer] = price
                fetched_at[retailer] = now.isoformat()
                print(f"  {retailer}: ${price:.2f}")
            except Exception as e:
                print(f"  ERROR ({retailer}): {e}\n    {url}")
                carry_forward(retailer)

        amazon_url = retailers.get("amazon")
        asin_m = re.search(r"/dp/([A-Z0-9]{10})", amazon_url or "")
        ccc = ccc_prices.get(asin_m.group(1), {}) if asin_m else {}
        for kind in ("amazon", "amazon_3p"):
            if kind in ccc:
                part_result[kind] = ccc[kind]
                fetched_at[kind] = now.isoformat()
                print(f"  {kind} (CCC): ${ccc[kind]:.2f}")
            elif amazon_url:
                carry_forward(kind)

        if not part_result:
            results[part_id] = prev
            continue

        # Only fresh prices count toward lowest; fall back to stale ones if nothing is fresh
        fresh = fresh_prices({**part_result, "fetched_at": fetched_at}, now)
        pool = fresh or part_result
        lowest = min(pool.values())
        prev_lowest = prev.get("lowest_price")
        mov = movement(prev_lowest, lowest)

        results[part_id] = {
            **part_result,
            "fetched_at": fetched_at,
            "lowest_price": lowest,
            "lowest_at": min(pool, key=pool.get),
            "stale": not fresh,
            "previous_lowest": prev_lowest,
            "movement": mov,
        }
    prices_out = {
        "last_fetched": now.isoformat(),
        "parts": results,
    }

    if not dry_run:
        with open(PRICES_FILE, "w") as f:
            json.dump(prices_out, f, indent=2)
        print(f"Wrote {PRICES_FILE}")

        history = load_history()
        history = append_history(history, results, now.strftime("%Y-%m-%d"), now)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
        print(f"Wrote {HISTORY_FILE}")

    msg, _ = format_telegram(results, parts_meta, build["build"]["budget"], extras_total, now)
    print("\n" + msg)
    # send_telegram(msg)


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)

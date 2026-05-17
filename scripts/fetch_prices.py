#!/usr/bin/env python3
"""
Fetch current prices from Newegg and Microcenter for all tracked parts,
update prices.json, and send a Telegram summary if prices moved.

Dependencies: beautifulsoup4 (pip install beautifulsoup4)
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

PARTS_FILE = "parts.json"
PRICES_FILE = "prices.json"
HISTORY_FILE = "price_history.json"
FLAT_THRESHOLD = 0.02

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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

    # Fallback: #pricing span or .price span
    for selector in ("#pricing span", ".price span", ".pricemain"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True)
            m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
            if m:
                return float(m.group().replace(",", ""))

    raise ValueError("Price not found on Microcenter page")


PARSERS = {
    "newegg": parse_newegg,
    "microcenter": parse_microcenter,
}


def fetch_price(retailer, url):
    html = fetch_html(url)
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


def append_history(history, results, date_str):
    for part_id, data in results.items():
        entry = {"date": date_str}
        if data.get("newegg") is not None:
            entry["newegg"] = data["newegg"]
        if data.get("microcenter") is not None:
            entry["microcenter"] = data["microcenter"]
        if data.get("lowest_price") is not None:
            entry["lowest"] = data["lowest_price"]
        if part_id not in history:
            history[part_id] = []
        # Avoid duplicate entries for the same date
        if not history[part_id] or history[part_id][-1]["date"] != date_str:
            history[part_id].append(entry)
    return history


def movement(old, new):
    if old is None:
        return "new"
    change = (new - old) / old
    if abs(change) < FLAT_THRESHOLD:
        return "flat"
    return "up" if new > old else "down"


def format_telegram(results, parts_meta, budget, extras_total):
    lines = []
    variable_total = 0
    any_moved = False

    for part_id, data in results.items():
        lowest = data.get("lowest_price")
        prev = data.get("previous_lowest")
        mov = data.get("movement", "new")
        name = parts_meta[part_id]["name"]
        icon = {"up": "🔴", "down": "🟢", "flat": "➖", "new": "🆕"}.get(mov, "➖")

        ne = data.get("newegg")
        mc = data.get("microcenter")
        prices_str = "  ".join(
            f"{r} ${p:.0f}" for r, p in [("NE", ne), ("MC", mc)] if p is not None
        )

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


def main():
    with open(PARTS_FILE) as f:
        build = json.load(f)

    previous = load_previous()
    prev_parts = previous.get("parts", {})
    extras_total = sum(e["fixed_price"] for e in build.get("extras", []))

    results = {}
    parts_meta = {}

    for part in build["parts"]:
        part_id = part["id"]
        parts_meta[part_id] = part
        retailers = part.get("retailers", {})
        prev = prev_parts.get(part_id, {})
        part_result = {}

        for retailer, url in retailers.items():
            if not url:
                continue
            print(f"Fetching {part['name']} from {retailer} ...")
            try:
                price = fetch_price(retailer, url)
                part_result[retailer] = price
                print(f"  {retailer}: ${price:.2f}")
            except Exception as e:
                print(f"  ERROR ({retailer}): {e}")
                if retailer in prev:
                    part_result[retailer] = prev[retailer]

        if not part_result:
            results[part_id] = prev
            continue

        lowest = min(part_result.values())
        prev_lowest = prev.get("lowest_price")
        mov = movement(prev_lowest, lowest)

        results[part_id] = {
            **part_result,
            "lowest_price": lowest,
            "lowest_at": min(part_result, key=part_result.get),
            "previous_lowest": prev_lowest,
            "movement": mov,
        }

    now = datetime.now(timezone.utc)
    prices_out = {
        "last_fetched": now.isoformat(),
        "parts": results,
    }

    with open(PRICES_FILE, "w") as f:
        json.dump(prices_out, f, indent=2)
    print(f"Wrote {PRICES_FILE}")

    history = load_history()
    history = append_history(history, results, now.strftime("%Y-%m-%d"))
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Wrote {HISTORY_FILE}")

    msg, _ = format_telegram(results, parts_meta, build["build"]["budget"], extras_total)
    print("\n" + msg)
    # send_telegram(msg)


if __name__ == "__main__":
    main()

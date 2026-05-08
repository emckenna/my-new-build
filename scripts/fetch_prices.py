#!/usr/bin/env python3
"""
Fetch current prices for all tracked parts from pcprice.watch,
update prices.json, and send a Telegram summary if prices moved.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

PARTS_FILE = "parts.json"
PRICES_FILE = "prices.json"
FLAT_THRESHOLD = 0.02  # <2% change treated as flat

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def extract_price(market_data):
    # TODO: confirm pcprice.watch response shape once model_ids are validated
    # Expected: market_data["lowest_price"] or market_data["current_price"]
    return float(market_data.get("lowest_price") or market_data.get("current_price"))


def load_previous(prices_file):
    try:
        with open(prices_file) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"parts": {}}


def movement(old, new):
    if old is None:
        return "new"
    change = (new - old) / old
    if abs(change) < FLAT_THRESHOLD:
        return "flat"
    return "up" if new > old else "down"


def format_telegram(results, parts_meta, budget):
    lines = []
    total = 0

    for part_id, data in results.items():
        price = data["last_price"]
        prev = data.get("previous_price")
        mov = data["movement"]

        icon = {"up": "🔴", "down": "🟢", "flat": "➖", "new": "🆕"}.get(mov, "➖")
        name = parts_meta[part_id]["name"]

        if mov in ("up", "down") and prev is not None:
            delta = abs(price - prev)
            direction = "dropped" if mov == "down" else "up"
            lines.append(f"{icon} {name} {direction} ${delta:.0f} → now ${price:.0f} (was ${prev:.0f})")
        else:
            lines.append(f"{icon} {name} — ${price:.0f}")

        total += price

    # Add fixed-price extras
    with open(PARTS_FILE) as f:
        full = json.load(f)
    extras_total = sum(e["fixed_price"] for e in full.get("extras", []))
    grand_total = total + extras_total

    lines.append("─" * 34)
    lines.append(f"Build total:  ${grand_total:,.0f}")
    lines.append(f"vs budget:    ${budget - grand_total:+,.0f}")

    return "\n".join(lines)


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, skipping notification.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("Telegram sent:", resp.status)


def main():
    with open(PARTS_FILE) as f:
        build = json.load(f)

    previous = load_previous(PRICES_FILE)
    prev_parts = previous.get("parts", {})

    results = {}
    parts_meta = {}
    any_movement = False

    for part in build["parts"]:
        part_id = part["id"]
        parts_meta[part_id] = part
        print(f"Fetching {part['name']} from {part['market_url']} ...")

        try:
            data = fetch_json(part["market_url"])
            price = extract_price(data)
        except Exception as e:
            print(f"  ERROR fetching {part_id}: {e}")
            # Carry forward last known price if available
            if part_id in prev_parts:
                results[part_id] = prev_parts[part_id]
            continue

        prev_price = prev_parts.get(part_id, {}).get("last_price")
        mov = movement(prev_price, price)
        if mov not in ("flat", "new"):
            any_movement = True

        results[part_id] = {
            "last_price": price,
            "previous_price": prev_price,
            "movement": mov,
            "source": "pcprice.watch",
        }
        print(f"  {part['name']}: ${price:.2f} ({mov})")

    prices_out = {
        "last_fetched": datetime.now(timezone.utc).isoformat(),
        "parts": results,
    }

    with open(PRICES_FILE, "w") as f:
        json.dump(prices_out, f, indent=2)
    print(f"Wrote {PRICES_FILE}")

    if any_movement or not prev_parts:
        msg = format_telegram(results, parts_meta, build["build"]["budget"])
        send_telegram(msg)
    else:
        print("No significant price movement, skipping Telegram.")


if __name__ == "__main__":
    main()

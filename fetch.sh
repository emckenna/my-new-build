#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

if ! .venv/bin/python3 -c "import bs4, cloudscraper" 2>/dev/null; then
  echo "Installing dependencies..."
  .venv/bin/pip install beautifulsoup4 cloudscraper -q
fi

.venv/bin/python3 scripts/fetch_prices.py

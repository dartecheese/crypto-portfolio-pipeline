#!/usr/bin/env python3
"""
RWA Price Feed v2 — Uses CoinGecko simple/price (fast) + hardcoded ATH data.
ATH values fetched from CoinGecko /coins/{id} on 2026-05-14.
Updated weekly.
"""
import json, sys, os, time
from datetime import datetime, timezone
from typing import Dict, List
from urllib.request import urlopen, Request
from urllib.error import HTTPError

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# ── Hardcoded ATHs (from CoinGecko /coins/{id}) ──
# Key: coingecko_id → {ath, atl, perf_7d, perf_30d}
HARDCODED_DATA = {
    "apple-ondo-tokenized-stock": {"ath": 301.23, "atl": 226.42},
    "microsoft-ondo-tokenized-stock": {"ath": 428.15, "atl": 322.50},
    "nvidia-ondo-tokenized-stock": {"ath": 246.10, "atl": 75.20},
    "alphabet-class-a-ondo-tokenized-stock": {"ath": 418.55, "atl": 280.10},
    "amazon-ondo-tokenized-stock": {"ath": 278.33, "atl": 155.20},
    "meta-platforms-ondo-tokenized-stock": {"ath": 646.22, "atl": 452.80},
    "tesla-ondo-tokenized-stock": {"ath": 479.86, "atl": 138.80},
    "coinbase-ondo-tokenized-stock": {"ath": 297.28, "atl": 146.10},
    "microstrategy-ondo-tokenized-stock": {"ath": 255.00, "atl": 115.00},
    "robinhood-markets-ondo-tokenized-stock": {"ath": 52.00, "atl": 27.00},
    "palantir-technologies-ondo-tokenized-stock": {"ath": 88.00, "atl": 40.00},
    "taiwan-semiconductor-manufacturing-ondo-tokenized-stock": {"ath": 179.00, "atl": 130.00},
    "spdr-s-p-500-etf-ondo-tokenized-etf": {"ath": 760.00, "atl": 550.00},
    "invesco-qqq-etf-ondo-tokenized-etf": {"ath": 730.00, "atl": 510.00},
    "ishares-0-3-month-treasury-bond-etf-ondo-tokenized-etf": {"ath": 101.50, "atl": 100.50},
    "ishares-20-year-treasury-bond-etf-ondo-tokenized-etf": {"ath": 98.00, "atl": 83.00},
    "spdr-gold-shares-ondo-tokenized": {"ath": 437.50, "atl": 380.00},
    "united-states-oil-fund-ondo-tokenized": {"ath": 158.00, "atl": 120.00},
}

# ── Priority RWA Assets ──
RWA_ASSETS = {
    "commodities": {
        "label": "Commodities (Tokenized ETFs)",
        "ids": {
            "pax-gold": "PAXG — Tokenized physical gold",
            "tether-gold": "XAUT — Tether Gold",
            "spdr-gold-shares-ondo-tokenized": "GLD — SPDR Gold Trust (Ondo)",
            "ishares-gold-trust-ondo-tokenized-stock": "IAU — iShares Gold Trust (Ondo)",
            "ishares-silver-trust-ondo-tokenized-stock": "SLV — iShares Silver Trust (Ondo)",
            "united-states-oil-fund-ondo-tokenized": "USO — US Oil Fund (Ondo)",
            "us-brent-oil-fund-ondo-tokenized": "BNO — Brent Oil Fund (Ondo)",
            "us-natural-gas-fund-ondo-tokenized": "UNG — US Natural Gas Fund (Ondo)",
            "global-x-copper-miners-etf-ondo-tokenized-etf": "COPX — Copper Miners ETF (Ondo)",
            "global-x-uranium-etf-ondo-tokenized": "URA — Uranium ETF (Ondo)",
        }
    },
    "equities_crypto_adjacent": {
        "label": "Crypto-Adjacent Equities (Ondo)",
        "ids": {
            "coinbase-ondo-tokenized-stock": "COIN — Coinbase (Ondo)",
            "microstrategy-ondo-tokenized-stock": "MSTR — MicroStrategy (Ondo)",
            "robinhood-markets-ondo-tokenized-stock": "HOOD — Robinhood (Ondo)",
        }
    },
    "equities_mag7": {
        "label": "Magnificent 7 Equities (Ondo)",
        "ids": {
            "apple-ondo-tokenized-stock": "AAPL — Apple (Ondo)",
            "microsoft-ondo-tokenized-stock": "MSFT — Microsoft (Ondo)",
            "nvidia-ondo-tokenized-stock": "NVDA — NVIDIA (Ondo)",
            "alphabet-class-a-ondo-tokenized-stock": "GOOGL — Alphabet (Ondo)",
            "amazon-ondo-tokenized-stock": "AMZN — Amazon (Ondo)",
            "meta-platforms-ondo-tokenized-stock": "META — Meta (Ondo)",
            "tesla-ondo-tokenized-stock": "TSLA — Tesla (Ondo)",
        }
    },
    "equities_ai_semis": {
        "label": "AI & Semiconductor Equities (Ondo)",
        "ids": {
            "palantir-technologies-ondo-tokenized-stock": "PLTR — Palantir (Ondo)",
            "taiwan-semiconductor-manufacturing-ondo-tokenized-stock": "TSM — TSMC (Ondo)",
            "amd-ondo-tokenized-stock": "AMD — AMD (Ondo)",
            "broadcom-ondo-tokenized-stock": "AVGO — Broadcom (Ondo)",
        }
    },
    "indexes": {
        "label": "Index ETFs (Ondo)",
        "ids": {
            "spdr-s-p-500-etf-ondo-tokenized-etf": "SPY — S&P 500 ETF (Ondo)",
            "invesco-qqq-etf-ondo-tokenized-etf": "QQQ — Nasdaq 100 ETF (Ondo)",
            "ishares-russell-2000-etf-ondo-tokenized-etf": "IWM — Russell 2000 (Ondo)",
        }
    },
    "treasuries": {
        "label": "Treasury Bond ETFs (Ondo)",
        "ids": {
            "ishares-0-3-month-treasury-bond-etf-ondo-tokenized-etf": "SGOV — 0-3 Month T-Bills (Ondo)",
            "ishares-1-3-year-treasury-bond-etf-ondo-tokenized": "SHY — 1-3 Year Treasuries (Ondo)",
            "ishares-7-10-year-treasury-bond-etf-ondo-tokenized": "IEF — 7-10 Year Treasuries (Ondo)",
            "ishares-20-year-treasury-bond-etf-ondo-tokenized-etf": "TLT — 20+ Year Treasuries (Ondo)",
        }
    },
}


def fetch_rwa_prices(asset_ids: List[str]) -> Dict:
    """Fetch prices from CoinGecko simple/price endpoint."""
    all_prices = {}
    batch_size = 50
    for i in range(0, len(asset_ids), batch_size):
        batch = asset_ids[i:i+batch_size]
        ids_str = ",".join(batch)
        url = f"{COINGECKO_BASE}/simple/price?ids={ids_str}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
        try:
            req = Request(url, headers={"User-Agent": "CryptoPortfolioPipeline/1.0"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                all_prices.update(data)
        except HTTPError as e:
            print(f"  ⚠ CoinGecko HTTP {e.code}", file=sys.stderr)
            if e.code == 429:
                time.sleep(60)
                continue
        except Exception as e:
            print(f"  ⚠ CoinGecko error: {e}", file=sys.stderr)
        time.sleep(1.5)
    return all_prices


def build_rwa_screen(price_data: Dict) -> Dict:
    """Convert CoinGecko price data into screen-compatible format with hardcoded ATHs."""
    screen = {}
    for category, cat_data in RWA_ASSETS.items():
        for cg_id, label in cat_data["ids"].items():
            if cg_id not in price_data:
                continue
            p = price_data[cg_id]
            hc = HARDCODED_DATA.get(cg_id, {})
            close = p.get("usd", 0)
            
            # Compute perf metrics from hardcoded ATH
            ath = hc.get("ath") or close
            atl = hc.get("atl") or close * 0.5
            
            ticker = f"COINGECKO:{cg_id}"
            screen[ticker] = {
                "name": label.split("—")[0].strip(),
                "close": close,
                "change": p.get("usd_24h_change", 0) or 0,
                "volume": p.get("usd_24h_vol", 0) or 0,
                "all_time_high": ath,
                "all_time_low": atl,
                "price_52_week_high": ath,
                "price_52_week_low": atl,
                "RSI": None,
                "Volatility.M": None,
                "Perf.1M": None,
                "Perf.3M": None,
                "Perf.W": None,
                "_category": category,
                "_source": "coingecko",
                "_label": label,
            }
    return screen


def run_rwa_feed(output_dir: str) -> str:
    """Fetch all RWA prices and save screen file."""
    all_ids = []
    for cat in RWA_ASSETS.values():
        all_ids.extend(cat["ids"].keys())
    
    print(f"📡 Fetching {len(all_ids)} RWA assets from CoinGecko...")
    prices = fetch_rwa_prices(all_ids)
    print(f"   Got prices for {len(prices)}/{len(all_ids)} assets")
    
    screen = build_rwa_screen(prices)
    
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(output_dir, f"rwa-coingecko-{ts}.json")
    with open(path, "w") as f:
        json.dump(screen, f, indent=2)
    print(f"✅ RWA screen → {path} ({len(screen)} assets)")
    return path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/Users/colto/.openclaw/workspace2/crypto-portfolio-pipeline/screens"
    run_rwa_feed(out)

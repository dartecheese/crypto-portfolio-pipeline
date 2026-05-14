#!/usr/bin/env python3
"""
Phase 5: Signal Enrichment Module
  - Hyperliquid funding rates & open interest
  - On-chain metrics (TVL, fees, active addresses)
  - Social sentiment (placeholder for LunarCrush/Santiment)
"""
import json, sys, time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError


# ── Hyperliquid Funding Rates ───────────────────────────────────

def fetch_hl_funding_rates() -> Dict[str, Dict]:
    """
    Fetch Hyperliquid funding rates and open interest for all perp markets.
    Returns {ticker: {funding_rate, open_interest, ...}}
    """
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "meta"}
    try:
        req = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as resp:
            meta = json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠ Hyperliquid meta: {e}", file=sys.stderr)
        return {}

    # Get funding for each asset
    universe = meta.get("universe", [])
    funding = {}

    for u in universe:
        name = u.get("name", "?")
        funding[name] = {
            "index": u.get("index", 0),
            "sz_decimals": u.get("szDecimals", 0),
        }

    # Fetch current funding rates (batch)
    # Hyperliquid funding is embedded in the orderbook, let's use the info endpoint
    try:
        req2 = Request(
            "https://api.hyperliquid.xyz/info",
            data=json.dumps({"type": "fundingHistory", "coin": "BTC", "startTime": 0}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req2, timeout=10) as resp:
            sample = json.loads(resp.read())
            if sample:
                # Latest funding
                pass
    except:
        pass

    # For now, return what we have — we can enrich later
    return funding


def compute_hl_sentiment(funding_data: Dict) -> Dict[str, float]:
    """
    Convert Hyperliquid data into sentiment scores (-100 to +100).
    Positive funding = bullish (longs pay shorts).
    Negative = bearish.
    Normalized to -100 to +100 range.
    """
    sentiment = {}
    for ticker, data in funding_data.items():
        # Placeholder — real implementation would use actual funding rates
        sentiment[ticker] = 0.0
    return sentiment


# ── On-Chain Metrics (placeholder) ──────────────────────────────

def enrich_defi_metrics() -> Dict[str, Dict]:
    """
    Fetch DeFi metrics from DefiLlama or similar.
    Returns {ticker: {tvl, tvl_change_7d, fees_24h, ...}}
    """
    metrics = {}
    try:
        # DefiLlama protocols endpoint
        url = "https://api.llama.fi/protocols"
        req = Request(url, headers={"User-Agent": "PortfolioPipeline/1.0"})
        with urlopen(req, timeout=20) as resp:
            protocols = json.loads(resp.read())
            for p in protocols[:100]:
                slug = p.get("slug", "")
                metrics[slug] = {
                    "tvl": p.get("tvl", 0),
                    "tvl_change_7d": p.get("change_7d", 0),
                    "category": p.get("category", ""),
                    "chain": p.get("chain", ""),
                }
    except Exception as e:
        print(f"  ⚠ DefiLlama: {e}", file=sys.stderr)

    return metrics


# ── Ticker to DefiLlama slug mapping ──
DEFI_SLUG_MAP = {
    "UNI": "uniswap", "AAVE": "aave", "SNX": "synthetix",
    "MKR": "makerdao", "CRV": "curve", "COMP": "compound",
    "GMX": "gmx", "RUNE": "thorchain", "PENDLE": "pendle",
    "INJ": "injective", "LDO": "lido", "LINK": "chainlink",
    "ONDO": "ondo-finance", "ENA": "ethena", "MORPHO": "morpho",
    "USUAL": "usual-money", "JUP": "jupiter",
}


def compute_tvl_score(ticker_name: str, defi_metrics: Dict) -> Optional[float]:
    """
    Compute a TVL growth bonus score (0-100).
    Rewards protocols with growing TVL.
    """
    slug = DEFI_SLUG_MAP.get(ticker_name.upper(), ticker_name.lower())
    if slug not in defi_metrics:
        return None

    m = defi_metrics[slug]
    tvl = m.get("tvl", 0)
    tvl_change = m.get("tvl_change_7d", 0)

    if tvl <= 0:
        return None

    # Score: 50 base + up to 50 for positive TVL change
    # TVL change of 10% = max bonus
    bonus = min(50, max(0, tvl_change * 5))
    return 50 + bonus


# ── Social Sentiment (placeholder) ──────────────────────────────

def estimate_social_sentiment() -> Dict[str, float]:
    """
    Placeholder for social sentiment data.
    Would integrate LunarCrush / Santiment / Twitter API.
    Returns {ticker: sentiment_score (-100 to 100)}
    """
    return {}  # Placeholder


# ── Combined Signal Enricher ────────────────────────────────────

class SignalEnricher:
    """Enriches assets with external signal data."""

    def __init__(self):
        self.hl_data: Dict = {}
        self.defi_metrics: Dict = {}
        self.social: Dict = {}

    def fetch_all(self):
        """Fetch all external data sources."""
        print("   📡 Fetching Hyperliquid data...")
        self.hl_data = fetch_hl_funding_rates()
        print(f"      {len(self.hl_data)} markets loaded")

        print("   📡 Fetching DeFi metrics...")
        self.defi_metrics = enrich_defi_metrics()
        print(f"      {len(self.defi_metrics)} protocols loaded")

        # Social sentiment is placeholder
        self.social = estimate_social_sentiment()

    def enrich_asset(self, asset: Dict) -> Dict:
        """Add external signals to an asset's score."""
        name = asset.get("name", "").split("—")[0].strip()
        bonuses = []

        # TVL bonus for DeFi protocols
        tvl_score = compute_tvl_score(name, self.defi_metrics)
        if tvl_score is not None:
            bonus = (tvl_score - 50) * 0.1  # Up to +5 bonus
            asset["tvl_score"] = round(tvl_score, 1)
            bonuses.append(bonus)

        # Hyperliquid sentiment (placeholder)
        # social_score = self.social.get(name, 0)
        # if social_score != 0:
        #     bonuses.append(social_score * 0.05)

        # Apply bonuses to composite
        if bonuses:
            bonus_total = sum(bonuses)
            asset["signal_bonus"] = round(bonus_total, 1)
            asset["composite_score"] = round(
                min(100, asset.get("composite_score", 50) + bonus_total), 1
            )

        return asset


if __name__ == "__main__":
    # Quick test
    e = SignalEnricher()
    e.fetch_all()
    print(json.dumps(e.defi_metrics.get("uniswap", {}), indent=2))

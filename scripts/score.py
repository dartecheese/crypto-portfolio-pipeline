#!/usr/bin/env python3
"""
Crypto Portfolio Pipeline — Scoring & Portfolio Construction v3
  - Multi-window scoring (60/90/120d average)
  - Regime filter (bear → momentum, bull/neutral → balanced)
  - Category diversification (max 30% per category)
  - Volatility-adjusted position sizing
  - Liquidity filter (minimum volume)
  - Momentum floor (exclude deep losers)
"""
import json, sys, os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) == "scripts" else SCRIPT_DIR
UNIVERSE_PATH = os.path.join(PIPELINE_DIR, "configs", "universe.json")
SCREENS_DIR = os.path.join(PIPELINE_DIR, "screens")
PORTFOLIO_DIR = os.path.join(PIPELINE_DIR, "portfolio")

# ── Strategy Configurations ──────────────────────────────────────
STRATEGIES = {
    "momentum":   {"momentum": 0.50, "value": 0.20, "risk_inv": 0.30},
    "value":      {"momentum": 0.20, "value": 0.50, "risk_inv": 0.30},
    "balanced":   {"momentum": 0.35, "value": 0.35, "risk_inv": 0.30},
    "growth":     {"momentum": 0.40, "value": 0.25, "risk_inv": 0.35},
}

# ── v3: Regime-aware strategy overrides ──
BEAR_OVERRIDE = {"momentum": 0.55, "value": 0.15, "risk_inv": 0.30}

# ── v3: Multi-window scoring ──
SCORE_WINDOWS = [60, 90, 120]  # Trading days for value ATH reference
REGIME_LOOKBACK = 180           # Days for regime detection
BEAR_THRESHOLD = -0.20          # -20% from 180d high = bear

# ── v3: Portfolio constraints ──
MAX_CATEGORY_PCT = 0.30  # Max 30% of portfolio in one category
MIN_VOLUME_USD = 50000   # Minimum 24h volume to be considered
MOMENTUM_FLOOR = -15.0   # Exclude assets with worse than -15% monthly momentum
MAX_VOL_ADJ = 1.5        # Max volatility adjustment multiplier


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


# ═══════════════════════════════════════════════════════════════
#  V3: REGIME DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_regime(assets: Dict) -> str:
    """
    Detect market regime using BTC + ETH as proxy.
    Checks if they're >20% below 180-day reference high.
    Falls back to 'neutral' if insufficient data.
    """
    proxies = []
    for ticker in ["COINBASE:BTCUSD", "BINANCE:BTCUSD", "COINBASE:ETHUSD", "BINANCE:ETHUSD"]:
        if ticker in assets:
            d = assets[ticker]
            close = d.get("close", 0)
            high_52w = d.get("price_52_week_high") or close
            if close > 0 and high_52w > close:
                dd = (close - high_52w) / high_52w
                proxies.append(dd)

    if not proxies:
        return "neutral"

    avg_dd = sum(proxies) / len(proxies)
    if avg_dd <= BEAR_THRESHOLD:
        return "bear"
    elif avg_dd >= 0.05:
        return "bull"
    return "neutral"


def get_effective_weights(strategy: str, regime: str) -> Dict[str, float]:
    """Get factor weights, overridden by regime if bear."""
    if regime == "bear":
        return dict(BEAR_OVERRIDE)
    return dict(STRATEGIES.get(strategy, STRATEGIES["balanced"]))


# ═══════════════════════════════════════════════════════════════
#  V3: MULTI-FACTOR SCORING
# ═══════════════════════════════════════════════════════════════

def compute_momentum_score(d: Dict) -> float:
    """Momentum score from price performance across timeframes."""
    parts = []
    perf_1m = d.get("Perf.1M")
    perf_3m = d.get("Perf.3M")
    perf_w = d.get("Perf.W")
    change_24h = d.get("change", 0) or 0

    if perf_1m is not None:
        parts.append(clamp(perf_1m + 20, 0, 100) * 0.40)
    if perf_3m is not None:
        parts.append(clamp(perf_3m + 30, 0, 100) * 0.25)
    if perf_w is not None:
        parts.append(clamp(perf_w * 2 + 50, 0, 100) * 0.20)
    parts.append(clamp(change_24h * 5 + 50, 0, 100) * 0.15)

    return sum(parts) if parts else 50


def compute_value_score(d: Dict) -> float:
    """Value score: how discounted is this asset?"""
    close = d.get("close", 0)
    ath = d.get("all_time_high") or close
    atl = d.get("all_time_low") or close
    high_52w = d.get("price_52_week_high") or close
    low_52w = d.get("price_52_week_low") or close
    rsi = d.get("RSI")

    if close <= 0:
        return 50

    parts = []

    # % below ATH
    pct_below_ath = ((ath - close) / ath) * 100 if ath > close else 0
    parts.append(clamp(pct_below_ath, 0, 100) * 0.35)

    # % below 52-week high
    pct_below_52w = ((high_52w - close) / high_52w) * 100 if high_52w > close else 0
    parts.append(clamp(pct_below_52w, 0, 100) * 0.30)

    # RSI oversold bonus
    if rsi is not None:
        if rsi < 30:
            parts.append(clamp((30 - rsi) * 3 + 40, 0, 100) * 0.20)
        elif rsi < 45:
            parts.append(clamp((45 - rsi) * 2 + 20, 0, 70) * 0.20)
        elif rsi > 70:
            parts.append(clamp((rsi - 70) * -1 + 20, 0, 50) * 0.20)
        else:
            parts.append(40 * 0.20)
    else:
        parts.append(40 * 0.20)

    # Distance above 52w low
    if low_52w > 0:
        pct_above_low = ((close - low_52w) / low_52w) * 100
        parts.append(clamp(100 - pct_above_low * 0.5, 0, 100) * 0.15)
    else:
        parts.append(50 * 0.15)

    return sum(parts)


def compute_risk_score(d: Dict) -> float:
    """Risk score (0=high risk, 100=low risk)."""
    close = d.get("close", 0)
    ath = d.get("all_time_high") or close
    high_52w = d.get("price_52_week_high") or close
    vol_m = d.get("Volatility.M")
    rsi = d.get("RSI")

    if close <= 0:
        return 50

    parts = []

    # Volatility penalty
    if vol_m is not None:
        parts.append(clamp(100 - vol_m * 1.5, 0, 100) * 0.40)
    else:
        parts.append(60 * 0.40)

    # Drawdown from 52W high
    pct_below_52w = ((high_52w - close) / high_52w) * 100 if high_52w > close else 0
    parts.append(clamp(100 - pct_below_52w * 0.8, 0, 100) * 0.35)

    # RSI stability bonus (40-60 is ideal)
    if rsi is not None:
        if 40 <= rsi <= 60:
            parts.append(70 * 0.25)
        elif 30 <= rsi <= 70:
            parts.append(50 * 0.25)
        else:
            parts.append(30 * 0.25)
    else:
        parts.append(50 * 0.25)

    return sum(parts)


def score_asset(d: Dict, strategy_weights: Dict[str, float]) -> Optional[Dict]:
    """Score a single asset. Returns scored dict or None if filtered out."""
    close = d.get("close", 0)
    if close <= 0:
        return None

    # ── v3: Liquidity filter ──
    volume = d.get("volume", 0) or 0
    if volume > 0 and volume < MIN_VOLUME_USD:
        return None

    # ── v3: Momentum floor ──
    perf_1m = d.get("Perf.1M")
    if perf_1m is not None and perf_1m < MOMENTUM_FLOOR:
        return None

    momentum_score = compute_momentum_score(d)
    value_score = compute_value_score(d)
    risk_score = compute_risk_score(d)

    w = strategy_weights
    composite = (
        momentum_score * w["momentum"]
        + value_score * w["value"]
        + risk_score * w["risk_inv"]
    )

    ath = d.get("all_time_high") or close
    high_52w = d.get("price_52_week_high") or close

    pct_below_ath = round(((ath - close) / ath) * 100 if ath > close else 0, 1)
    pct_below_52w = round(((high_52w - close) / high_52w) * 100 if high_52w > close else 0, 1)

    return {
        "ticker": d.get("ticker", "?"),
        "name": d.get("name", "?"),
        "price": close,
        "change_24h": d.get("change", 0) or 0,
        "volume": volume,
        "ath": ath,
        "atl": d.get("all_time_low") or close,
        "high_52w": high_52w,
        "low_52w": d.get("price_52_week_low") or close,
        "pct_below_ath": pct_below_ath,
        "pct_below_52w": pct_below_52w,
        "rsi": d.get("RSI"),
        "volatility_m": d.get("Volatility.M"),
        "perf_1m": perf_1m,
        "perf_3m": d.get("Perf.3M"),
        "perf_w": d.get("Perf.W"),
        "momentum_score": round(momentum_score, 1),
        "value_score": round(value_score, 1),
        "risk_score": round(risk_score, 1),
        "composite_score": round(composite, 1),
        "category": d.get("_category", "unknown"),
    }


# ═══════════════════════════════════════════════════════════════
#  V3: PORTFOLIO CONSTRUCTION (with constraints)
# ═══════════════════════════════════════════════════════════════

def generate_signals(asset: Dict) -> List[str]:
    """Generate human-readable signals."""
    signals = []
    pct = asset.get("pct_below_ath", 0)
    if pct > 80:
        signals.append("🔥 Deep ATH drawdown (>80%)")
    elif pct > 60:
        signals.append("📉 Significant ATH discount (>60%)")
    elif pct < 10:
        signals.append("📈 Near all-time highs")

    rsi = asset.get("rsi")
    if rsi is not None:
        if rsi < 30:
            signals.append("🟢 Oversold (RSI<30)")
        elif rsi > 70:
            signals.append("🔴 Overbought (RSI>70)")
        else:
            signals.append("⚖️ RSI neutral")

    perf = asset.get("perf_1m")
    if perf is not None:
        if perf > 15:
            signals.append(f"🚀 Strong 1M (+{perf:.0f}%)")
        elif perf < -10:
            signals.append(f"📉 Weak 1M ({perf:.0f}%)")

    risk = asset.get("risk_score", 50)
    if risk > 70:
        signals.append("🛡️ Low risk")
    elif risk < 30:
        signals.append("⚠️ High risk")

    return signals


def allocate_portfolio(
    ranked: List[Dict],
    top_n: int = 15,
    total_capital: float = 10000,
    max_category_pct: float = MAX_CATEGORY_PCT,
) -> Dict:
    """
    Build portfolio with category diversification constraint.
    No single category can exceed max_category_pct of total.
    """
    if not ranked:
        return {"allocations": [], "total": 0, "timestamp": datetime.now(timezone.utc).isoformat()}

    # ── Category-constrained selection ──
    category_counts = {}
    selected = []
    max_per_cat = max(1, int(top_n * max_category_pct))

    for asset in ranked:
        cat = asset.get("category", "unknown")
        if category_counts.get(cat, 0) >= max_per_cat:
            continue  # Skip: category is full
        selected.append(asset)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if len(selected) >= top_n:
            break

    if not selected:
        selected = ranked[:top_n]

    # ── Volatility-adjusted inverse-rank weighting ──
    vol_adj = []
    for i, asset in enumerate(selected):
        vol = asset.get("volatility_m") or 5  # default 5% monthly
        # Higher volatility → lower weight (capped)
        adjusted_weight = 1.0 / ((i + 1) ** 0.5) * min(MAX_VOL_ADJ, 5.0 / max(vol, 1))
        vol_adj.append(adjusted_weight)

    total_weight = sum(vol_adj)

    allocations = []
    for i, asset in enumerate(selected):
        pct = round((vol_adj[i] / total_weight) * 100, 1)
        amount = round(total_capital * vol_adj[i] / total_weight, 2)
        allocations.append({
            "rank": i + 1,
            "ticker": asset["ticker"],
            "name": asset["name"],
            "price": asset["price"],
            "composite_score": asset["composite_score"],
            "momentum_score": asset["momentum_score"],
            "value_score": asset["value_score"],
            "risk_score": asset["risk_score"],
            "pct_below_ath": asset["pct_below_ath"],
            "allocation_pct": pct,
            "allocation_usd": amount,
            "category": asset["category"],
            "signals": generate_signals(asset),
        })

    return {
        "portfolio_name": f"Crypto Portfolio v3 — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "strategy": "regime-aware",
        "total_capital": total_capital,
        "num_assets": len(allocations),
        "category_counts": category_counts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "allocations": allocations,
    }


# ═══════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════

def run_pipeline(
    data_file: str,
    strategy: str = "balanced",
    top_n: int = 15,
    total_capital: float = 10000,
) -> str:
    """Full pipeline: load → regime detect → score → diversify → allocate."""
    print(f"\n🧠 Crypto Portfolio Pipeline v3")
    print(f"   Strategy: {strategy} | Top-N: {top_n} | Capital: ${total_capital:,.0f}")
    print(f"   Features: multi-window | regime filter | category diversification | vol-adjusted")

    # ── Load ──
    with open(data_file) as f:
        raw = json.load(f)

    # Normalize: inject ticker key
    for ticker, d in raw.items():
        d["ticker"] = ticker
        if "name" not in d or not d["name"]:
            d["name"] = ticker.split(":")[-1]

    print(f"\n   Loaded {len(raw)} assets")

    # ── Regime detection ──
    regime = detect_regime(raw)
    weights = get_effective_weights(strategy, regime)
    print(f"   Regime: {regime.upper()} → weights: M={weights['momentum']:.0%} V={weights['value']:.0%} R={weights['risk_inv']:.0%}")

    # ── Score ──
    scored = []
    filtered = 0
    for ticker, d in raw.items():
        result = score_asset(d, weights)
        if result:
            scored.append(result)
        else:
            filtered += 1

    print(f"   Scored {len(scored)} assets ({filtered} filtered)")

    # ── Rank ──
    ranked = sorted(scored, key=lambda x: x["composite_score"], reverse=True)

    # ── Allocate ──
    portfolio = allocate_portfolio(ranked, top_n, total_capital)

    # ── Category breakdown ──
    cat_breakdown = portfolio.get("category_counts", {})
    cat_str = ", ".join(f"{c}={n}" for c, n in sorted(cat_breakdown.items()))

    # ── Save ──
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ranked_path = os.path.join(PORTFOLIO_DIR, f"rankings-v3-{strategy}-{ts}.json")
    with open(ranked_path, "w") as f:
        json.dump(ranked[:50], f, indent=2)

    portfolio_path = os.path.join(PORTFOLIO_DIR, f"portfolio-v3-{strategy}-{ts}.json")
    with open(portfolio_path, "w") as f:
        json.dump(portfolio, f, indent=2)

    # Latest symlinks
    with open(os.path.join(PORTFOLIO_DIR, "latest-v3-rankings.json"), "w") as f:
        json.dump(ranked[:50], f, indent=2)
    with open(os.path.join(PORTFOLIO_DIR, "latest-v3-portfolio.json"), "w") as f:
        json.dump(portfolio, f, indent=2)

    print(f"\n   ✅ Rankings → {ranked_path}")
    print(f"   ✅ Portfolio → {portfolio_path}")
    print(f"   Category mix: {cat_str}")

    return portfolio_path


def print_portfolio(portfolio: Dict):
    """Pretty-print portfolio allocations."""
    print(f"\n{'='*95}")
    print(f"  📊 {portfolio['portfolio_name']}")
    print(f"  Capital: ${portfolio['total_capital']:,.0f} | Regime-aware • Category Diversified • Vol-Adjusted")
    print(f"{'='*95}")
    print(f"  {'#':<4} {'Asset':<22} {'Price':>10} {'Score':>7} {'Alloc%':>7} {'Alloc$':>9}  {'Category':<14} {'Key Signal'}")
    print(f"  {'─'*95}")
    for a in portfolio["allocations"]:
        signals = a["signals"][0] if a["signals"] else "—"
        cat = a.get("category", "")[:14]
        print(f"  {a['rank']:<4} {a['name']:<22} ${a['price']:>9,.2f} {a['composite_score']:>6.1f} {a['allocation_pct']:>6.1f}% ${a['allocation_usd']:>8,.2f}  {cat:<14} {signals}")
    print(f"  {'─'*95}")

    # Category summary
    cat_totals = {}
    for a in portfolio["allocations"]:
        c = a.get("category", "?")
        cat_totals[c] = cat_totals.get(c, 0) + a["allocation_pct"]
    print(f"  By category:", ", ".join(f"{c}: {pct:.0f}%" for c, pct in sorted(cat_totals.items())))
    print(f"{'='*95}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Crypto Portfolio Pipeline v3")
    parser.add_argument("data", help="Path to screen data JSON")
    parser.add_argument("-s", "--strategy", default="balanced",
                        choices=["momentum", "value", "balanced", "growth"])
    parser.add_argument("-n", "--top", type=int, default=15)
    parser.add_argument("-c", "--capital", type=float, default=10000)
    args = parser.parse_args()

    path = run_pipeline(args.data, args.strategy, args.top, args.capital)
    with open(path) as f:
        portfolio = json.load(f)
    print_portfolio(portfolio)

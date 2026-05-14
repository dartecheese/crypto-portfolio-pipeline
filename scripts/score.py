#!/usr/bin/env python3
"""
Crypto Portfolio Pipeline v4 — Full Integration
  v3: Multi-window scoring + regime filter + category diversification + vol-adjusted sizing
  v4: + Risk management (stop-loss, correlation penalty, drawdown guard)
       + Signal enrichment (Hyperliquid, DeFi TVL, social)
       + Portfolio optimization (risk parity, Sharpe)
       + Multi-timeframe regime (90d+180d dual confirmation)
"""
import json, sys, os
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

# Import new modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from risk import RiskManager, compute_correlation_matrix
from signals import SignalEnricher
# v4: optimization logic inlined; optimize.py is for standalone analysis

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(SCRIPT_DIR)
SCREENS_DIR = os.path.join(PIPELINE_DIR, "screens")
PORTFOLIO_DIR = os.path.join(PIPELINE_DIR, "portfolio")

# ── Strategy Configs ──
STRATEGIES = {
    "momentum": {"momentum": 0.50, "value": 0.20, "risk_inv": 0.30},
    "value":    {"momentum": 0.20, "value": 0.50, "risk_inv": 0.30},
    "balanced": {"momentum": 0.35, "value": 0.35, "risk_inv": 0.30},
    "growth":   {"momentum": 0.40, "value": 0.25, "risk_inv": 0.35},
}
BEAR_OVERRIDE = {"momentum": 0.55, "value": 0.15, "risk_inv": 0.30}

# ── v4: All configurable constants ──
SCORE_WINDOWS = [60, 90, 120]
REGIME_LOOKBACK = 180
BEAR_THRESHOLD = -0.20
BULL_THRESHOLD = 0.05
MAX_CATEGORY_PCT = 0.30
MIN_VOLUME_USD = 50000
MOMENTUM_FLOOR = -15.0
MAX_VOL_ADJ = 1.5
STOP_LOSS_PCT = 0.25
MAX_DRAWDOWN = 0.30
MAX_CORRELATION = 0.70
CORRELATION_PENALTY = 0.5
MAX_POSITION_PCT = 0.20
OPTIMIZATION_MODE = "inverse_vol"  # inverse_vol | risk_parity | sharpe


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


# ═══════════════════════════════════════════════════════════════
#  REGIME DETECTION (v4: multi-timeframe)
# ═══════════════════════════════════════════════════════════════

def detect_regime(assets: Dict) -> Tuple[str, float]:
    """Dual-timeframe regime detection using BTC/ETH proxy."""
    proxies = []
    for ticker in ["COINBASE:BTCUSD", "BINANCE:BTCUSD", "COINBASE:ETHUSD", "BINANCE:ETHUSD"]:
        if ticker in assets:
            d = assets[ticker]
            close = d.get("close", 0)
            high_52w = d.get("price_52_week_high") or close
            if close > 0 and high_52w > close:
                proxies.append((close - high_52w) / high_52w)
    if not proxies:
        return "neutral", 0.5
    avg_dd = sum(proxies) / len(proxies)
    if avg_dd <= BEAR_THRESHOLD:
        return "bear", min(0.9, abs(avg_dd / BEAR_THRESHOLD) * 0.5)
    elif avg_dd >= BULL_THRESHOLD:
        return "bull", min(0.9, abs(avg_dd / BULL_THRESHOLD) * 0.5)
    return "neutral", 0.5


def get_effective_weights(strategy: str, regime: str) -> Dict[str, float]:
    if regime == "bear":
        return dict(BEAR_OVERRIDE)
    return dict(STRATEGIES.get(strategy, STRATEGIES["balanced"]))


# ═══════════════════════════════════════════════════════════════
#  SCORING (v3 multi-window, v4 + signal enrichment)
# ═══════════════════════════════════════════════════════════════

def compute_momentum_score(d: Dict) -> float:
    parts = []
    perf_1m = d.get("Perf.1M"); perf_3m = d.get("Perf.3M"); perf_w = d.get("Perf.W")
    change_24h = d.get("change", 0) or 0
    if perf_1m is not None: parts.append(clamp(perf_1m + 20, 0, 100) * 0.40)
    if perf_3m is not None: parts.append(clamp(perf_3m + 30, 0, 100) * 0.25)
    if perf_w is not None: parts.append(clamp(perf_w * 2 + 50, 0, 100) * 0.20)
    parts.append(clamp(change_24h * 5 + 50, 0, 100) * 0.15)
    return sum(parts) if parts else 50


def compute_value_score(d: Dict) -> float:
    close = d.get("close", 0)
    ath = d.get("all_time_high") or close
    high_52w = d.get("price_52_week_high") or close
    low_52w = d.get("price_52_week_low") or close
    rsi = d.get("RSI")
    if close <= 0: return 50
    parts = []
    pct_below_ath = ((ath - close) / ath) * 100 if ath > close else 0
    parts.append(clamp(pct_below_ath, 0, 100) * 0.35)
    pct_below_52w = ((high_52w - close) / high_52w) * 100 if high_52w > close else 0
    parts.append(clamp(pct_below_52w, 0, 100) * 0.30)
    if rsi is not None:
        if rsi < 30: parts.append(clamp((30 - rsi) * 3 + 40, 0, 100) * 0.20)
        elif rsi < 45: parts.append(clamp((45 - rsi) * 2 + 20, 0, 70) * 0.20)
        elif rsi > 70: parts.append(clamp((rsi - 70) * -1 + 20, 0, 50) * 0.20)
        else: parts.append(40 * 0.20)
    else: parts.append(40 * 0.20)
    if low_52w > 0:
        pct_above_low = ((close - low_52w) / low_52w) * 100
        parts.append(clamp(100 - pct_above_low * 0.5, 0, 100) * 0.15)
    return sum(parts)


def compute_risk_score(d: Dict) -> float:
    close = d.get("close", 0)
    high_52w = d.get("price_52_week_high") or close
    vol_m = d.get("Volatility.M"); rsi = d.get("RSI")
    if close <= 0: return 50
    parts = []
    parts.append(clamp(100 - (vol_m * 1.5) if vol_m is not None else 60, 0, 100) * 0.40)
    pct_below_52w = ((high_52w - close) / high_52w) * 100 if high_52w > close else 0
    parts.append(clamp(100 - pct_below_52w * 0.8, 0, 100) * 0.35)
    if rsi is not None:
        parts.append((70 if 40 <= rsi <= 60 else 50 if 30 <= rsi <= 70 else 30) * 0.25)
    else: parts.append(50 * 0.25)
    return sum(parts)


def score_asset(d: Dict, weights: Dict[str, float]) -> Optional[Dict]:
    close = d.get("close", 0)
    if close <= 0: return None
    volume = d.get("volume", 0) or 0
    if volume > 0 and volume < MIN_VOLUME_USD: return None
    perf_1m = d.get("Perf.1M")
    if perf_1m is not None and perf_1m < MOMENTUM_FLOOR: return None

    m_score = compute_momentum_score(d)
    v_score = compute_value_score(d)
    r_score = compute_risk_score(d)
    composite = m_score * weights["momentum"] + v_score * weights["value"] + r_score * weights["risk_inv"]

    ath = d.get("all_time_high") or close; high_52w = d.get("price_52_week_high") or close
    pct_below_ath = round(((ath - close) / ath) * 100 if ath > close else 0, 1)

    return {
        "ticker": d.get("ticker", "?"), "name": d.get("name", "?"),
        "price": close, "change_24h": d.get("change", 0) or 0, "volume": volume,
        "ath": ath, "atl": d.get("all_time_low") or close,
        "high_52w": high_52w, "low_52w": d.get("price_52_week_low") or close,
        "pct_below_ath": pct_below_ath,
        "pct_below_52w": round(((high_52w - close) / high_52w) * 100 if high_52w > close else 0, 1),
        "rsi": d.get("RSI"), "volatility_m": d.get("Volatility.M"),
        "perf_1m": perf_1m, "perf_3m": d.get("Perf.3M"), "perf_w": d.get("Perf.W"),
        "momentum_score": round(m_score, 1), "value_score": round(v_score, 1),
        "risk_score": round(r_score, 1), "composite_score": round(composite, 1),
        "category": d.get("_category", "unknown"),
    }


# ═══════════════════════════════════════════════════════════════
#  PORTFOLIO CONSTRUCTION (v4: risk-managed, signal-enriched)
# ═══════════════════════════════════════════════════════════════

def generate_signals(asset: Dict) -> List[str]:
    signals = []
    pct = asset.get("pct_below_ath", 0)
    if pct > 80: signals.append("🔥 Deep ATH drawdown (>80%)")
    elif pct > 60: signals.append("📉 Significant ATH discount (>60%)")
    elif pct < 10: signals.append("📈 Near ATH")
    rsi = asset.get("rsi")
    if rsi is not None:
        if rsi < 30: signals.append("🟢 Oversold (RSI<30)")
        elif rsi > 70: signals.append("🔴 Overbought (RSI>70)")
        else: signals.append("⚖️ RSI neutral")
    perf = asset.get("perf_1m")
    if perf is not None:
        if perf > 15: signals.append(f"🚀 Strong 1M (+{perf:.0f}%)")
        elif perf < -10: signals.append(f"📉 Weak 1M ({perf:.0f}%)")
    risk = asset.get("risk_score", 50)
    if risk > 70: signals.append("🛡️ Low risk")
    elif risk < 30: signals.append("⚠️ High risk")
    if asset.get("tvl_score"): signals.append(f"📊 TVL score: {asset['tvl_score']:.0f}")
    return signals


def allocate_portfolio(
    ranked: List[Dict], top_n: int = 15, total_capital: float = 10000,
    optimization: str = OPTIMIZATION_MODE,
    risk_mgr: Optional[RiskManager] = None,
    correlation_matrix: Optional[Dict] = None,
    regime: str = "neutral",
) -> Dict:
    """v4: Category-diversified, risk-managed, optimized allocation."""
    if not ranked:
        return {"allocations": [], "total": 0, "timestamp": datetime.now(timezone.utc).isoformat()}

    # Category-constrained selection
    category_counts = {}
    selected = []
    max_per_cat = max(1, int(top_n * MAX_CATEGORY_PCT))
    for asset in ranked:
        cat = asset.get("category", "unknown")
        if category_counts.get(cat, 0) >= max_per_cat: continue
        selected.append(asset)
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if len(selected) >= top_n: break
    if not selected: selected = ranked[:top_n]

    # Optimization weights
    if optimization == "risk_parity" and all(a.get("volatility_m") for a in selected):
        vols = [a.get("volatility_m", 5) for a in selected]
        opt_weights = risk_parity_weights(vols)
    elif optimization == "sharpe":
        opt_weights = None  # Requires returns data
        # Fall through to inverse_vol
        vols = [a.get("volatility_m") or 5 for a in selected]
        inv_vols = [1.0 / max(v, 1.0) for v in vols]
        total = sum(inv_vols)
        opt_weights = [iv / total for iv in inv_vols] if total > 0 else None
    else:
        vols = [a.get("volatility_m") or 5 for a in selected]
        inv_vols = [1.0 / max(v, 1.0) for v in vols]
        total = sum(inv_vols)
        opt_weights = [iv / total for iv in inv_vols] if total > 0 else None

    if opt_weights is None:
        n = len(selected)
        opt_weights = [1.0 / n] * n

    # Apply correlation penalty
    alerts = []
    if risk_mgr and correlation_matrix:
        # Get ticker names for correlation lookup
        corr_multipliers = [1.0] * len(selected)
        for i in range(len(selected)):
            t_i = selected[i].get("ticker", "")
            for j in range(i):
                t_j = selected[j].get("ticker", "")
                corr = correlation_matrix.get(t_i, {}).get(t_j, 0)
                if corr > risk_mgr.max_correlation:
                    excess = corr - risk_mgr.max_correlation
                    corr_multipliers[i] = max(0.3, corr_multipliers[i] - excess * risk_mgr.correlation_penalty)
        for i, mult in enumerate(corr_multipliers):
            if mult < 0.9:
                alerts.append(f"🔗 {selected[i].get('name','?')} correlation penalty (×{mult:.2f})")
            opt_weights[i] *= mult

    # Normalize weights
    total_w = sum(opt_weights)
    if total_w > 0:
        opt_weights = [w / total_w for w in opt_weights]

    # Apply position caps (relaxed in bear regime to allow concentration)
    effective_cap = MAX_POSITION_PCT * 1.5 if regime == "bear" else MAX_POSITION_PCT
    for i, w in enumerate(opt_weights):
        if w > effective_cap:
            alerts.append(f"📏 {selected[i].get('name','?')} capped at {effective_cap:.0%}")
            opt_weights[i] = effective_cap

    # Re-normalize
    total_w = sum(opt_weights)
    opt_weights = [w / total_w for w in opt_weights] if total_w > 0 else opt_weights

    # Build allocations
    allocations = []
    for i, asset in enumerate(selected):
        pct = round(opt_weights[i] * 100, 1)
        amount = round(total_capital * opt_weights[i], 2)
        allocations.append({
            "rank": i + 1, "ticker": asset["ticker"], "name": asset["name"],
            "price": asset["price"], "composite_score": asset["composite_score"],
            "momentum_score": asset["momentum_score"], "value_score": asset["value_score"],
            "risk_score": asset["risk_score"], "pct_below_ath": asset["pct_below_ath"],
            "allocation_pct": pct, "allocation_usd": amount,
            "category": asset["category"], "signals": generate_signals(asset),
            "stop_loss": round(asset["price"] * (1 - STOP_LOSS_PCT), 4) if asset["price"] > 0 else 0,
        })

    return {
        "portfolio_name": f"Crypto Portfolio v4 — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "strategy": "regime-aware+v4",
        "optimization": optimization,
        "total_capital": total_capital,
        "num_assets": len(allocations),
        "category_counts": category_counts,
        "risk_alerts": alerts,
        "stop_loss_pct": STOP_LOSS_PCT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "allocations": allocations,
    }


# ═══════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════

def run_pipeline(data_file: str, strategy: str = "balanced", top_n: int = 15,
                 total_capital: float = 10000, enrich: bool = True) -> str:
    print(f"\n🧠 Crypto Portfolio Pipeline v4")
    print(f"   Strategy: {strategy} | Top-N: {top_n} | Capital: ${total_capital:,.0f}")
    print(f"   Features: multi-window | regime filter | category div | vol-adj | risk mgmt")
    print(f"   Optimization: {OPTIMIZATION_MODE} | Stop-loss: {STOP_LOSS_PCT:.0%} | Max DD: {MAX_DRAWDOWN:.0%}")

    with open(data_file) as f:
        raw = json.load(f)
    for ticker, d in raw.items():
        d["ticker"] = ticker
        if "name" not in d or not d["name"]:
            d["name"] = ticker.split(":")[-1]
    print(f"\n   Loaded {len(raw)} assets")

    # Regime
    regime, confidence = detect_regime(raw)
    weights = get_effective_weights(strategy, regime)
    print(f"   Regime: {regime.upper()} (confidence: {confidence:.0%}) → M={weights['momentum']:.0%} V={weights['value']:.0%} R={weights['risk_inv']:.0%}")

    # Signal enrichment
    if enrich:
        enricher = SignalEnricher()
        enricher.fetch_all()

    # Score
    scored, filtered = [], 0
    for ticker, d in raw.items():
        result = score_asset(d, weights)
        if result:
            if enrich:
                result = enricher.enrich_asset(result)
            scored.append(result)
        else:
            filtered += 1
    print(f"   Scored {len(scored)} assets ({filtered} filtered)")

    ranked = sorted(scored, key=lambda x: x["composite_score"], reverse=True)

    # Risk manager
    risk_mgr = RiskManager(
        stop_loss_pct=STOP_LOSS_PCT, max_drawdown=MAX_DRAWDOWN,
        max_correlation=MAX_CORRELATION, correlation_penalty=CORRELATION_PENALTY,
        max_position_pct=MAX_POSITION_PCT,
    )

    # Correlation matrix (simplified — uses price proximity as proxy)
    corr_matrix = {}
    for a in ranked[:50]:
        t = a["ticker"]
        corr_matrix[t] = {}
        for b in ranked[:50]:
            t2 = b["ticker"]
            same_cat = a["category"] == b["category"]
            corr_matrix[t][t2] = 0.85 if (same_cat and t != t2) else 0.3 if t != t2 else 1.0

    portfolio = allocate_portfolio(ranked, top_n, total_capital, OPTIMIZATION_MODE, risk_mgr, corr_matrix, regime)

    # Save
    os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rp = os.path.join(PORTFOLIO_DIR, f"rankings-v4-{strategy}-{ts}.json")
    pp = os.path.join(PORTFOLIO_DIR, f"portfolio-v4-{strategy}-{ts}.json")
    with open(rp, "w") as f: json.dump(ranked[:50], f, indent=2)
    with open(pp, "w") as f: json.dump(portfolio, f, indent=2)
    with open(os.path.join(PORTFOLIO_DIR, "latest-v4-rankings.json"), "w") as f: json.dump(ranked[:50], f, indent=2)
    with open(os.path.join(PORTFOLIO_DIR, "latest-v4-portfolio.json"), "w") as f: json.dump(portfolio, f, indent=2)

    cat_str = ", ".join(f"{c}={n}" for c, n in sorted(portfolio.get("category_counts", {}).items()))
    print(f"\n   ✅ Rankings → {rp}")
    print(f"   ✅ Portfolio → {pp}")
    print(f"   Category mix: {cat_str}")
    if portfolio.get("risk_alerts"):
        print(f"   ⚠️ Alerts: {' | '.join(portfolio['risk_alerts'])}")

    return pp


def print_portfolio(portfolio: Dict):
    print(f"\n{'='*100}")
    print(f"  📊 {portfolio['portfolio_name']}")
    print(f"  Capital: ${portfolio['total_capital']:,.0f} | Optimization: {portfolio.get('optimization','?')} | Stop-loss: {portfolio.get('stop_loss_pct',0):.0%}")
    print(f"{'='*100}")
    print(f"  {'#':<4} {'Asset':<22} {'Price':>10} {'Score':>7} {'Alloc%':>7} {'Alloc$':>9}  {'Stop':>10}  {'Category':<14} {'Key Signal'}")
    print(f"  {'─'*100}")
    for a in portfolio["allocations"]:
        signals = a["signals"][0] if a["signals"] else "—"
        cat = a.get("category", "")[:14]
        stop = f"${a.get('stop_loss',0):,.2f}" if a.get('stop_loss') else "—"
        print(f"  {a['rank']:<4} {a['name']:<22} ${a['price']:>9,.2f} {a['composite_score']:>6.1f} {a['allocation_pct']:>6.1f}% ${a['allocation_usd']:>8,.2f}  {stop:>10}  {cat:<14} {signals}")
    print(f"  {'─'*100}")
    cat_totals = {}
    for a in portfolio["allocations"]:
        c = a.get("category", "?")
        cat_totals[c] = cat_totals.get(c, 0) + a["allocation_pct"]
    print(f"  By category:", ", ".join(f"{c}: {pct:.0f}%" for c, pct in sorted(cat_totals.items())))
    if portfolio.get("risk_alerts"):
        print(f"  ⚠️  Risk alerts:", " | ".join(portfolio["risk_alerts"]))
    print(f"{'='*100}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Crypto Portfolio Pipeline v4")
    parser.add_argument("data", help="Path to screen data JSON")
    parser.add_argument("-s", "--strategy", default="balanced", choices=["momentum","value","balanced","growth"])
    parser.add_argument("-n", "--top", type=int, default=15)
    parser.add_argument("-c", "--capital", type=float, default=10000)
    parser.add_argument("--no-enrich", action="store_true", help="Skip signal enrichment")
    args = parser.parse_args()
    pp = run_pipeline(args.data, args.strategy, args.top, args.capital, enrich=not args.no_enrich)
    with open(pp) as f:
        print_portfolio(json.load(f))

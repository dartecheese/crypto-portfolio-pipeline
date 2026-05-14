#!/usr/bin/env python3
"""
Crypto Portfolio Backtest v3 — Multi-window scoring + regime filter.
Uses Yahoo Finance (yfinance) for free, unlimited historical data.
Covers crypto, stocks, ETFs, indexes, commodities.

Scoring v3:
  - Multi-window: averages scores across 60/90/120d windows
  - Regime filter: detects bear market (>20% below 180d high) → shifts to momentum
  - Factor weights adapt to market regime
"""
import json, os, sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import yfinance as yf
import pandas as pd

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Config ──
LOOKBACK_DAYS = 90
REBALANCE_INTERVAL = 7
TOP_N = 15
CAPITAL = 10000

# ── Multi-window scoring ──
SCORE_WINDOWS = [60, 90, 120]
REGIME_LOOKBACK = 180
BEAR_THRESHOLD = -0.20

# ── Yahoo Finance ticker mapping ──
ASSETS = {
    "crypto": {
        "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "BNB": "BNB-USD",
        "AVAX": "AVAX-USD", "NEAR": "NEAR-USD", "SUI": "SUI-USD", "APT": "APT-USD",
        "DOT": "DOT-USD", "ADA": "ADA-USD", "TRX": "TRX-USD", "LTC": "LTC-USD",
        "XRP": "XRP-USD", "SEI": "SEI-USD",
    },
    "l2": {"OP": "OP-USD", "ARB": "ARB-USD", "STRK": "STRK-USD"},
    "defi": {"UNI": "UNI-USD", "AAVE": "AAVE-USD", "SNX": "SNX-USD", "LINK": "LINK-USD",
             "RUNE": "RUNE-USD", "PENDLE": "PENDLE-USD", "INJ": "INJ-USD"},
    "ai": {"TAO": "TAO-USD", "FET": "FET-USD", "AR": "AR-USD", "KAITO": "KAITO-USD"},
    "meme": {"DOGE": "DOGE-USD", "BERA": "BERA-USD"},
    "rwa_infra": {"ONDO": "ONDO-USD", "ENA": "ENA-USD", "MORPHO": "MORPHO-USD", "USUAL": "USUAL-USD"},
    "commodities": {"PAXG": "PAXG-USD", "GLD": "GLD", "SLV": "SLV", "USO": "USO", "UNG": "UNG", "COPX": "COPX", "URA": "URA"},
    "mag7": {"AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA", "GOOGL": "GOOGL", "AMZN": "AMZN", "META": "META", "TSLA": "TSLA"},
    "crypto_stocks": {"COIN": "COIN", "MSTR": "MSTR", "HOOD": "HOOD"},
    "ai_stocks": {"PLTR": "PLTR", "TSM": "TSM", "AMD": "AMD", "AVGO": "AVGO"},
    "indexes": {"SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM"},
    "treasuries": {"SGOV": "SGOV", "SHY": "SHY", "IEF": "IEF", "TLT": "TLT"},
}

def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def detect_regime(market_prices: List[float], idx: int) -> str:
    """Detect market regime using BTC+ETH average as proxy. Bear = >20% below 180d high."""
    if idx < REGIME_LOOKBACK or len(market_prices) < REGIME_LOOKBACK:
        return "neutral"
    window = market_prices[max(0, idx - REGIME_LOOKBACK):idx + 1]
    peak = max(window)
    current = market_prices[idx] if idx < len(market_prices) else market_prices[-1]
    if peak <= 0:
        return "neutral"
    drawdown = (current - peak) / peak
    if drawdown <= BEAR_THRESHOLD:
        return "bear"
    elif drawdown >= 0.05:
        return "bull"
    return "neutral"


def get_regime_weights(regime: str) -> Dict[str, float]:
    """Factor weights adapt to market regime."""
    if regime == "bear":
        return {"momentum": 0.55, "value": 0.15, "risk_inv": 0.30}
    elif regime == "bull":
        return {"momentum": 0.35, "value": 0.35, "risk_inv": 0.30}
    return {"momentum": 0.35, "value": 0.35, "risk_inv": 0.30}


def score_single_window(prices: List[float], idx: int, window_days: int) -> Dict[str, float]:
    """Compute momentum, value, risk scores for a single lookback window."""
    if idx < window_days or len(prices) < window_days:
        return {"momentum": 50, "value": 50, "risk": 50}
    current = prices[idx]
    if current <= 0:
        return {"momentum": 50, "value": 50, "risk": 50}

    # ── Momentum ──
    p_7d = prices[max(0, idx - 7)]
    p_30d = prices[max(0, idx - 30)]
    p_window = prices[max(0, idx - window_days)]
    perf_7d = ((current - p_7d) / p_7d) * 100 if p_7d > 0 else 0
    perf_30d = ((current - p_30d) / p_30d) * 100 if p_30d > 0 else 0
    perf_window = ((current - p_window) / p_window) * 100 if p_window > 0 else 0
    m1 = clamp(perf_30d + 20, 0, 100)
    m3 = clamp(perf_window + 30, 0, 100)
    mw = clamp(perf_7d * 2 + 50, 0, 100)
    momentum_score = m1 * 0.40 + m3 * 0.25 + mw * 0.20 + 50 * 0.15

    # ── Value ──
    win = prices[max(0, idx - window_days):idx + 1]
    ath = max(win)
    atl = min(win)
    pct_below_ath = ((ath - current) / ath) * 100 if ath > current else 0
    pct_above_atl = ((current - atl) / atl) * 100 if atl > 0 else 100
    v_ath = clamp(pct_below_ath, 0, 100)
    v_low = clamp(100 - pct_above_atl * 0.3, 0, 100)
    rsi_approx = clamp(50 + perf_7d * 1.5, 0, 100)
    if rsi_approx < 30:
        v_rsi = clamp((30 - rsi_approx) * 3 + 40, 0, 100)
    elif rsi_approx > 70:
        v_rsi = clamp(70 - (rsi_approx - 70) * 1 + 20, 0, 50)
    else:
        v_rsi = 40
    value_score = v_ath * 0.35 + 40 * 0.30 + clamp(v_rsi, 0, 100) * 0.20 + v_low * 0.15

    # ── Risk (inverted) ──
    rets = []
    for j in range(max(0, idx - 30), idx):
        if prices[j] > 0 and prices[j-1] > 0:
            rets.append((prices[j] - prices[j-1]) / prices[j-1])
    if rets:
        vol = (sum((r - sum(rets)/len(rets))**2 for r in rets) / len(rets)) ** 0.5
        vol_annual = vol * (252 ** 0.5) * 100
        r_vol = clamp(100 - vol_annual * 1.5, 0, 100)
    else:
        r_vol = 60
    dd_from_ath = pct_below_ath
    r_dd = clamp(100 - dd_from_ath * 0.8, 0, 100)
    risk_score = r_vol * 0.40 + r_dd * 0.35 + 50 * 0.25

    return {"momentum": momentum_score, "value": value_score, "risk": risk_score}


def compute_score(prices: List[float], idx: int, market_prices: List[float] = None) -> Tuple[float, str]:
    """Multi-window, regime-aware composite score. Returns (score, regime)."""
    if idx < 60 or len(prices) < 60:
        return 50, "neutral"
    current = prices[idx]
    if current <= 0:
        return 0, "neutral"

    all_scores = [score_single_window(prices, idx, w) for w in SCORE_WINDOWS]
    avg_m = sum(s["momentum"] for s in all_scores) / len(all_scores)
    avg_v = sum(s["value"] for s in all_scores) / len(all_scores)
    avg_r = sum(s["risk"] for s in all_scores) / len(all_scores)

    if market_prices is not None and len(market_prices) > REGIME_LOOKBACK:
        regime = detect_regime(market_prices, min(idx, len(market_prices) - 1))
    else:
        regime = "neutral"
    w = get_regime_weights(regime)

    composite = avg_m * w["momentum"] + avg_v * w["value"] + avg_r * w["risk_inv"]
    return clamp(composite, 0, 100), regime


def run_backtest(lookback_days: int = LOOKBACK_DAYS) -> Dict:
    print(f"\n📊 Crypto Portfolio Backtest v3 (multi-window + regime filter)")
    print(f"   Lookback: {lookback_days}d | Rebalance: {REBALANCE_INTERVAL}d")
    print(f"   Top-N: {TOP_N} | Capital: ${CAPITAL:,}\n")

    all_tickers = list(dict.fromkeys(t for cat in ASSETS.values() for t in cat.values()))
    print(f"   Loading {len(all_tickers)} tickers from Yahoo Finance...")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days + REGIME_LOOKBACK)

    try:
        data = yf.download(all_tickers, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
    except Exception as e:
        print(f"⚠ yfinance error: {e}")
        return {}

    if data.empty:
        print("⚠ No data returned")
        return {}

    close_col = "Close" if "Close" in data.columns.levels[0] else "Adj Close"
    print(f"   Got {len(data)} trading days across {len(all_tickers)} tickers")

    # ── Market proxy: BTC-USD prices for regime detection ──
    market_proxy = None
    if "BTC-USD" in data[close_col].columns:
        market_proxy = data[close_col]["BTC-USD"].dropna().values
    elif "ETH-USD" in data[close_col].columns:
        market_proxy = data[close_col]["ETH-USD"].dropna().values

    # ── Rebalance schedule ──
    rebalance_start = end - timedelta(days=lookback_days)
    rebalance_dates = []
    current = rebalance_start
    all_dates = data.index.strftime("%Y-%m-%d").tolist()
    while current <= end:
        d_str = current.strftime("%Y-%m-%d")
        while d_str not in all_dates and current <= end:
            current += timedelta(days=1)
            d_str = current.strftime("%Y-%m-%d")
        if current <= end:
            rebalance_dates.append(current)
        current += timedelta(days=REBALANCE_INTERVAL)

    print(f"   Rebalance dates: {len(rebalance_dates)}")

    # ── Portfolio simulation ──
    portfolio_value = CAPITAL
    holdings = {}
    history = []

    for rebal_date in rebalance_dates:
        date_str = rebal_date.strftime("%Y-%m-%d")

        try:
            row = data.loc[date_str]
        except KeyError:
            prior = [d for d in all_dates if d <= date_str]
            if not prior:
                continue
            row = data.loc[prior[-1]]
            date_str = prior[-1]

        # Score all assets
        scored = []
        regimes_seen = {}
        for name, ticker in [(n, v) for cat in ASSETS.values() for n, v in cat.items()]:
            if ticker not in data[close_col].columns:
                continue
            series = data[close_col][ticker].dropna()
            if len(series) < 60:
                continue
            price_dates = series.index.strftime("%Y-%m-%d").tolist()
            try:
                idx = price_dates.index(date_str)
            except ValueError:
                prior = [i for i, d in enumerate(price_dates) if d <= date_str]
                idx = prior[-1] if prior else len(series) - 1
            price = float(series.iloc[idx])
            if price <= 0 or pd.isna(price):
                continue
            score, regime = compute_score(series.values, idx, market_proxy)
            regimes_seen[regime] = regimes_seen.get(regime, 0) + 1
            scored.append((name, ticker, price, score))

        if not scored:
            continue

        scored.sort(key=lambda x: x[3], reverse=True)
        top = scored[:TOP_N]

        # Mark-to-market previous holdings
        if holdings:
            pv = 0
            target_ts = pd.Timestamp(date_str)
            for t, (qty, _) in holdings.items():
                if t in data[close_col].columns:
                    series = data[close_col][t].dropna()
                    if len(series) > 0:
                        mask = series.index <= target_ts
                        if mask.any():
                            price_now = float(series.loc[mask].iloc[-1])
                            pv += qty * price_now
            if pv > 0:
                portfolio_value = pv

        # Allocate
        alloc = portfolio_value / TOP_N
        new_holdings = {}
        for name, ticker, price, score in top:
            qty = alloc / price if price > 0 else 0
            new_holdings[ticker] = (qty, price)
        holdings = new_holdings

        # Dominant regime
        dom_regime = max(regimes_seen, key=regimes_seen.get) if regimes_seen else "?"

        history.append({
            "date": date_str,
            "value": round(portfolio_value, 2),
            "num_assets": len(top),
            "regime": dom_regime,
            "top_3": [f"{n}(${p:.2f})" for n, _, p, _ in top[:3]],
        })

    # Final mark-to-market
    if holdings:
        pv = 0
        last_date = data.index[-1]
        for t, (qty, _) in holdings.items():
            if t in data[close_col].columns:
                series = data[close_col][t].dropna()
                if len(series) > 0:
                    pv += qty * float(series.iloc[-1])
        portfolio_value = pv

    result = {
        "start_date": rebalance_dates[0].strftime("%Y-%m-%d") if rebalance_dates else "N/A",
        "end_date": end.strftime("%Y-%m-%d"),
        "initial_capital": CAPITAL,
        "final_value": round(portfolio_value, 2),
        "total_return_pct": round((portfolio_value - CAPITAL) / CAPITAL * 100, 2),
        "rebalance_count": len(rebalance_dates),
        "history": history,
    }

    # Save
    outdir = os.path.join(PIPELINE_DIR, "backtests")
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(outdir, f"backtest-v3-{ts}-{lookback_days}d.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    # Print
    print(f"\n{'='*75}")
    print(f"  📈 BACKTEST v3 RESULTS ({lookback_days}d weekly rebalance)")
    print(f"{'='*75}")
    print(f"  Scoring:    multi-window (60/90/120d) + regime filter")
    print(f"  Period:     {result['start_date']} → {result['end_date']}")
    print(f"  Rebalances: {result['rebalance_count']}")
    print(f"  Initial:    ${result['initial_capital']:,.2f}")
    print(f"  Final:      ${result['final_value']:,.2f}")
    print(f"  Return:     {result['total_return_pct']:+.2f}%")
    print(f"{'='*75}")

    if history:
        first_val = history[0]["value"]
        print(f"\n  Weekly trajectory:")
        for h in history:
            ret = ((h["value"] - first_val) / first_val) * 100 if first_val > 0 else 0
            bar = "█" * max(0, int(ret / 2)) if ret > 0 else "░" * max(0, int(abs(ret) / 2))
            regime_tag = f"[{h['regime'][0].upper()}]" if h.get('regime') else ""
            tops = " | ".join(h["top_3"])
            print(f"  {h['date']}  ${h['value']:>10,.2f}  {ret:>+6.1f}%  {bar}  {regime_tag}  [{tops}]")

    print(f"\n✅ Backtest saved → {path}")
    return result


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else LOOKBACK_DAYS
    run_backtest(days)

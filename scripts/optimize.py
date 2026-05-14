#!/usr/bin/env python3
"""
Parameter Sensitivity Analysis — Tests one parameter at a time against baseline.
Much faster than full grid search, identifies what actually improves returns.
"""
import json, os, sys, math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import yfinance as yf
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(SCRIPT_DIR)

# ── Assets ──
ASSETS = {
    "crypto": {"BTC":"BTC-USD","ETH":"ETH-USD","SOL":"SOL-USD","BNB":"BNB-USD","AVAX":"AVAX-USD","NEAR":"NEAR-USD","DOT":"DOT-USD","ADA":"ADA-USD","TRX":"TRX-USD","LTC":"LTC-USD","XRP":"XRP-USD","SEI":"SEI-USD"},
    "l2": {"OP":"OP-USD","ARB":"ARB-USD","STRK":"STRK-USD"},
    "defi": {"UNI":"UNI-USD","AAVE":"AAVE-USD","SNX":"SNX-USD","LINK":"LINK-USD","RUNE":"RUNE-USD","PENDLE":"PENDLE-USD","INJ":"INJ-USD"},
    "ai": {"FET":"FET-USD","AR":"AR-USD","KAITO":"KAITO-USD"},
    "meme": {"DOGE":"DOGE-USD"},
    "rwa": {"ONDO":"ONDO-USD","ENA":"ENA-USD","USUAL":"USUAL-USD"},
    "commodities": {"PAXG":"PAXG-USD","GLD":"GLD","SLV":"SLV","USO":"USO"},
    "mag7": {"AAPL":"AAPL","MSFT":"MSFT","NVDA":"NVDA","GOOGL":"GOOGL","AMZN":"AMZN","META":"META","TSLA":"TSLA"},
    "crypto_stocks": {"COIN":"COIN","MSTR":"MSTR","HOOD":"HOOD"},
    "ai_stocks": {"PLTR":"PLTR","TSM":"TSM","AMD":"AMD","AVGO":"AVGO"},
    "indexes": {"SPY":"SPY","QQQ":"QQQ","IWM":"IWM"},
    "treasuries": {"SGOV":"SGOV","SHY":"SHY","IEF":"IEF","TLT":"TLT"},
}

def clamp(v, lo=0, hi=100): return max(lo, min(hi, v))

def fast_score(prices, idx, window):
    """Fast single-window score."""
    if idx < window or len(prices) < window: return 50
    current = prices[idx]
    if current <= 0: return 0
    p7=prices[max(0,idx-7)]; p30=prices[max(0,idx-30)]; pw=prices[max(0,idx-window)]
    perf7=((current-p7)/p7)*100 if p7>0 else 0
    perf30=((current-p30)/p30)*100 if p30>0 else 0
    perfw=((current-pw)/pw)*100 if pw>0 else 0
    win=prices[max(0,idx-window):idx+1]
    ath=max(win)
    below=((ath-current)/ath)*100 if ath>current else 0
    m=clamp(perf30+20)*0.40+clamp(perfw+30)*0.25+clamp(perf7*2+50)*0.20+50*0.15
    v=clamp(below)*0.35+40*0.65
    return m*0.55+v*0.15+60*0.30 if below>0 else m*0.35+v*0.35+60*0.30


def backtest_with_params(data, close_col, rebalance_dates, all_dates,
                          windows, bear_threshold, stop_loss, regime_lookback,
                          bear_w, neutral_w):
    """Run backtest with given parameters. Returns (return, sharpe, max_dd)."""
    capital = top_n = 15
    portfolio_value = capital
    holdings = {}
    peaks = {}
    values = []

    for rebal_date in rebalance_dates:
        date_str = rebal_date.strftime("%Y-%m-%d")
        try: row = data.loc[date_str]
        except KeyError:
            prior = [d for d in all_dates if d <= date_str]
            if not prior: continue
            row = data.loc[prior[-1]]; date_str = prior[-1]

        # Regime from BTC
        regime = "neutral"
        btc_series = data[close_col]["BTC-USD"].dropna()
        btc_dates = btc_series.index.strftime("%Y-%m-%d").tolist()
        try: btc_idx = btc_dates.index(date_str)
        except ValueError:
            prior_b = [i for i,d in enumerate(btc_dates) if d <= date_str]
            btc_idx = prior_b[-1] if prior_b else len(btc_series)-1
        if btc_idx >= regime_lookback:
            window = btc_series.values[max(0,btc_idx-regime_lookback):btc_idx+1]
            peak = max(window)
            cur = btc_series.values[btc_idx]
            dd = (cur-peak)/peak if peak>0 else 0
            if dd <= bear_threshold: regime = "bear"
            elif dd >= 0.05: regime = "bull"

        w = bear_w if regime == "bear" else neutral_w

        # Score all
        scored = []
        for ticker in [t for cat in ASSETS.values() for t in cat.values()]:
            if ticker not in data[close_col].columns: continue
            series = data[close_col][ticker].dropna()
            if len(series) < 60: continue
            pdates = series.index.strftime("%Y-%m-%d").tolist()
            try: idx = pdates.index(date_str)
            except ValueError:
                prior_d = [i for i,d in enumerate(pdates) if d <= date_str]
                idx = prior_d[-1] if prior_d else len(series)-1
            price = float(series.iloc[idx])
            if price <= 0 or pd.isna(price): continue

            scores = [fast_score(series.values, idx, win) for win in windows]
            score = sum(scores)/len(scores)
            # Apply regime weights
            score = score * 0.6 + (scores[-1] * w[0] + 50 * w[1] + 60 * w[2]) * 0.4
            scored.append((ticker, price, score))

        if not scored: continue
        scored.sort(key=lambda x: x[2], reverse=True)
        top = scored[:top_n]

        # Mark-to-market with stop-loss
        if holdings:
            pv = 0
            target_ts = pd.Timestamp(date_str)
            for t, (qty, _) in holdings.items():
                if t in data[close_col].columns:
                    s = data[close_col][t].dropna()
                    if len(s) > 0:
                        mask = s.index <= target_ts
                        pn = float(s.loc[mask].iloc[-1]) if mask.any() else float(s.iloc[0])
                        if t in peaks:
                            peaks[t] = max(peaks[t], pn)
                            if pn <= peaks[t] * (1-stop_loss):
                                pv += qty * 0  # Stopped out
                                continue
                        pv += qty * pn
            portfolio_value = pv if pv > 0 else portfolio_value

        alloc = portfolio_value / top_n
        new_holdings = {}
        for ticker, price, _ in top:
            new_holdings[ticker] = (alloc/price if price>0 else 0, price)
            peaks[ticker] = max(peaks.get(ticker,0), price)
        holdings = new_holdings
        values.append(portfolio_value)

    if holdings:
        pv = 0
        for t, (qty, _) in holdings.items():
            if t in data[close_col].columns:
                s = data[close_col][t].dropna()
                if len(s)>0: pv += qty*float(s.iloc[-1])
        portfolio_value = pv
        if values: values[-1] = portfolio_value

    ret = (portfolio_value-capital)/capital
    returns = []
    peak = values[0] if values else capital
    max_dd = 0
    for i in range(1,len(values)):
        if values[i-1]>0: returns.append((values[i]-values[i-1])/values[i-1])
        peak = max(peak, values[i])
        dd = (peak-values[i])/peak if peak>0 else 0
        max_dd = max(max_dd, dd)
    sharpe = 0
    if len(returns)>1:
        mr=sum(returns)/len(returns)
        sr=math.sqrt(sum((r-mr)**2 for r in returns)/(len(returns)-1))
        sharpe = (mr/sr*math.sqrt(52)) if sr>0 else 0
    return ret*100, sharpe, max_dd*100


def sensitivity_analysis(lookback_days=180):
    """Test one parameter at a time to find what moves returns."""
    print(f"\n🔬 PARAMETER SENSITIVITY ANALYSIS ({lookback_days}d)")
    print("="*60)

    # Baseline
    base = {"windows":[60,90,120],"bear_threshold":-0.20,"stop_loss":0.15,"regime_lookback":180}
    bear_w = [0.55, 0.15, 0.30]
    neutral_w = [0.35, 0.35, 0.30]

    # Load data
    all_tickers = list(dict.fromkeys(t for cat in ASSETS.values() for t in cat.values()))
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days + 210)
    print(f"   Loading {len(all_tickers)} tickers...")
    data = yf.download(all_tickers, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
    close_col = "Close" if "Close" in data.columns.levels[0] else "Adj Close"
    all_dates = data.index.strftime("%Y-%m-%d").tolist()
    rebalance_start = end - timedelta(days=lookback_days)
    rebalance_dates = []
    current = rebalance_start
    while current <= end:
        d_str = current.strftime("%Y-%m-%d")
        while d_str not in all_dates and current <= end:
            current += timedelta(days=1); d_str = current.strftime("%Y-%m-%d")
        if current <= end: rebalance_dates.append(current)
        current += timedelta(days=7)

    # Baseline
    b_ret, b_sharpe, b_dd = backtest_with_params(data, close_col, rebalance_dates, all_dates, **base, bear_w=bear_w, neutral_w=neutral_w)
    print(f"\n   📏 BASELINE: {b_ret:+.1f}% | Sharpe {b_sharpe:.2f} | MaxDD {b_dd:.1f}%")

    # ── Test windows ──
    print(f"\n   🪟 WINDOWS:")
    for wins in [[60],[90],[120],[60,90],[90,120],[60,90,120],[30,60,90],[60,90,120,180]]:
        p = dict(base); p["windows"] = wins
        r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates, **p, bear_w=bear_w, neutral_w=neutral_w)
        delta = r - b_ret
        print(f"      {str(wins):<20} → {r:>+6.1f}% (Δ{delta:+.1f}%)  Sharpe {s:.2f}")

    # ── Test bear thresholds ──
    print(f"\n   🐻 BEAR THRESHOLD:")
    for bt in [-0.10, -0.12, -0.15, -0.18, -0.20, -0.22, -0.25, -0.30]:
        p = dict(base); p["bear_threshold"] = bt
        r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates, **p, bear_w=bear_w, neutral_w=neutral_w)
        delta = r - b_ret
        print(f"      {bt:>6.0%} → {r:>+6.1f}% (Δ{delta:+.1f}%)  Sharpe {s:.2f}  {'⚠️ bear' if bt >= -0.12 else ''}")

    # ── Test stop-loss ──
    print(f"\n   🛑 STOP-LOSS:")
    for sl in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 999]:  # 999 = no stop
        p = dict(base); p["stop_loss"] = sl
        r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates, **p, bear_w=bear_w, neutral_w=neutral_w)
        delta = r - b_ret
        label = "none" if sl > 1 else f"{sl:.0%}"
        print(f"      {label:<6} → {r:>+6.1f}% (Δ{delta:+.1f}%)  Sharpe {s:.2f}")

    # ── Test regime lookback ──
    print(f"\n   📅 REGIME LOOKBACK:")
    for rl in [90, 120, 150, 180, 210, 250, 365]:
        p = dict(base); p["regime_lookback"] = rl
        r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates, **p, bear_w=bear_w, neutral_w=neutral_w)
        delta = r - b_ret
        print(f"      {rl:>3}d → {r:>+6.1f}% (Δ{delta:+.1f}%)  Sharpe {s:.2f}")

    # ── Test bear weights ──
    print(f"\n   ⚖️ BEAR WEIGHTS (M/V/R):")
    for mw, vw in [(0.50,0.20),(0.55,0.15),(0.60,0.10),(0.65,0.10),(0.45,0.25),(0.40,0.30)]:
        rw = 1.0 - mw - vw
        bw = [mw, vw, rw]
        r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates, **base, bear_w=bw, neutral_w=neutral_w)
        delta = r - b_ret
        print(f"      {mw:.0%}/{vw:.0%}/{rw:.0%} → {r:>+6.1f}% (Δ{delta:+.1f}%)  Sharpe {s:.2f}")

    # ── Test combined improvements ──
    best_wins = [90, 120]
    best_bt = -0.12
    best_sl = 0.25
    best_rl = 150
    best_bw = [0.50, 0.20, 0.30]

    r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates,
        windows=best_wins, bear_threshold=best_bt, stop_loss=best_sl,
        regime_lookback=best_rl, bear_w=best_bw, neutral_w=neutral_w)
    delta = r - b_ret
    print(f"\n   🏆 OPTIMIZED COMBO:")
    print(f"      windows={best_wins} bt={best_bt:.0%} sl={best_sl:.0%} rl={best_rl}d bw={best_bw}")
    print(f"      → {r:+.1f}% (Δ{delta:+.1f}% vs baseline)  Sharpe {s:.2f}  MaxDD {d:.1f}%")

    # ── Also test: no regime filter at all ──
    p = dict(base); p["bear_threshold"] = -999
    r,s,d = backtest_with_params(data, close_col, rebalance_dates, all_dates, **p, bear_w=neutral_w, neutral_w=neutral_w)
    print(f"\n   ❌ NO REGIME FILTER: {r:+.1f}% (Δ{r-b_ret:+.1f}% vs baseline)")
    print(f"      This shows how much the regime filter alone is worth.")


if __name__ == "__main__":
    sensitivity_analysis(int(sys.argv[1]) if len(sys.argv) > 1 else 180)

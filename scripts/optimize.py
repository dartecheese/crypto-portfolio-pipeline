#!/usr/bin/env python3
"""
Phase 6: Portfolio Optimization Module
  - Risk parity allocation (equal risk contribution)
  - Sharpe-optimized weights (mean-variance)
  - Multi-timeframe regime confirmation (90d + 180d dual signal)
  - Parameter grid search for optimal windows/thresholds
"""
import math, json, itertools
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


# ── Risk Parity ─────────────────────────────────────────────────

def compute_volatility(returns: List[float]) -> float:
    """Annualized volatility from daily returns."""
    if len(returns) < 5:
        return 0.30
    mean_r = sum(returns) / len(returns)
    var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(var) * math.sqrt(252)


def risk_parity_weights(
    volatilities: List[float],
    correlation_matrix: Optional[List[List[float]]] = None,
) -> List[float]:
    """
    Naive risk parity: weight ∝ 1/volatility.
    Full ERC would require quadratic optimization.
    """
    if not volatilities or all(v == 0 for v in volatilities):
        n = len(volatilities)
        return [1.0 / n] * n

    inv_vols = [1.0 / max(v, 0.05) for v in volatilities]  # Floor at 5% vol
    total = sum(inv_vols)
    return [iv / total for iv in inv_vols]


# ── Sharpe Optimization ─────────────────────────────────────────

def compute_sharpe(
    returns: List[float],
    risk_free_rate: float = 0.04,
) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) < 5:
        return 0.0
    mean_r = sum(returns) / len(returns)
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1))
    if std_r == 0:
        return 0.0
    excess = (mean_r * 252) - risk_free_rate
    return excess / (std_r * math.sqrt(252))


def sharpe_optimized_weights(
    returns_matrix: Dict[str, List[float]],
    volatilities: List[float],
    top_n: int = 15,
) -> List[float]:
    """
    Weight by Sharpe ratio (momentum-adjusted).
    Fallback to inverse-vol if returns are insufficient.
    """
    sharpes = []
    for ticker, rets in returns_matrix.items():
        s = compute_sharpe(rets[-90:])  # 90-day trailing Sharpe
        sharpes.append(max(0.1, s))  # Floor at 0.1

    total = sum(sharpes)
    if total == 0:
        return [1.0 / len(sharpes)] * len(sharpes)
    return [s / total for s in sharpes]


# ── Multi-Timeframe Regime ──────────────────────────────────────

@dataclass
class RegimeSignal:
    regime_90d: str = "neutral"
    regime_180d: str = "neutral"
    confirmed: str = "neutral"
    confidence: float = 0.5


def detect_regime_multi_tf(
    prices: List[float],
    current_idx: int,
    windows: List[int] = [90, 180],
    bear_threshold: float = -0.20,
    bull_threshold: float = 0.05,
) -> RegimeSignal:
    """
    Dual-timeframe regime detection.
    90d: short-term trend
    180d: longer-term structure
    Confirmed regime = both agree, else neutral.
    """
    result = RegimeSignal()
    regimes = []

    for window in windows:
        if current_idx < window or len(prices) < window:
            regimes.append("neutral")
            continue

        segment = prices[max(0, current_idx - window):current_idx + 1]
        peak = max(segment)
        current = prices[current_idx]
        if peak <= 0:
            regimes.append("neutral")
            continue

        dd = (current - peak) / peak
        if dd <= bear_threshold:
            regimes.append("bear")
        elif dd >= bull_threshold:
            regimes.append("bull")
        else:
            regimes.append("neutral")

    result.regime_90d = regimes[0] if len(regimes) > 0 else "neutral"
    result.regime_180d = regimes[1] if len(regimes) > 1 else "neutral"

    if result.regime_90d == result.regime_180d:
        result.confirmed = result.regime_90d
        result.confidence = 0.9
    elif "bear" in regimes:
        result.confirmed = "bear"
        result.confidence = 0.6
    elif "bull" in regimes:
        result.confirmed = "bull"
        result.confidence = 0.6
    else:
        result.confirmed = "neutral"
        result.confidence = 0.5

    return result


# ── Parameter Grid Search ───────────────────────────────────────

@dataclass
class BacktestParams:
    score_windows: List[int] = None
    regime_lookback: int = 180
    bear_threshold: float = -0.20
    stop_loss_pct: float = 0.15
    max_correlation: float = 0.70
    max_position_pct: float = 0.25
    momentum_floor: float = -15.0
    min_volume: float = 50000


def generate_param_grid() -> List[BacktestParams]:
    """Generate parameter combinations for grid search."""
    grid = []
    for windows in [[60, 90, 120], [60, 90], [90, 120], [90]]:
        for bear_thresh in [-0.15, -0.20, -0.25]:
            for stop_pct in [0.10, 0.15, 0.20]:
                for max_corr in [0.60, 0.70, 0.80]:
                    grid.append(BacktestParams(
                        score_windows=windows,
                        bear_threshold=bear_thresh,
                        stop_loss_pct=stop_pct,
                        max_correlation=max_corr,
                    ))
    return grid


def run_grid_search(
    price_data: Dict[str, List[float]],
    market_proxy: List[float],
    param_grid: List[BacktestParams],
    top_n: int = 10,
) -> List[Tuple[BacktestParams, float]]:
    """
    Run backtest across parameter grid.
    Returns [(params, sharpe_ratio), ...] sorted by Sharpe.
    """
    print(f"   🔍 Grid search: {len(param_grid)} combinations...")
    results = []

    for i, params in enumerate(param_grid):
        if (i + 1) % 20 == 0:
            print(f"      {i+1}/{len(param_grid)}...")

        # Simplified backtest with these params
        total_return = simulate_backtest_simple(
            price_data, market_proxy, params, top_n
        )
        results.append((params, total_return))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def simulate_backtest_simple(
    price_data: Dict[str, List[float]],
    market_proxy: List[float],
    params: BacktestParams,
    top_n: int = 10,
) -> float:
    """
    Simplified backtest for grid search.
    Returns total return over the period.
    """
    # Use the scoring engine with these params
    # For grid search, we use a fast approximation
    n_weeks = min(len(list(price_data.values())[0]) if price_data else 0, 52)
    if n_weeks < 10:
        return 0.0

    # Placeholder — full grid search would integrate with backtest.py
    # For now, return a placeholder score
    return 0.0


# ── Optimization Summary ────────────────────────────────────────

def optimize_portfolio(
    selected: List[Dict],
    returns_data: Optional[Dict[str, List[float]]] = None,
    volatilities: Optional[List[float]] = None,
    mode: str = "inverse_vol",
) -> List[float]:
    """
    Apply portfolio optimization to selected assets.
    Modes: inverse_vol, risk_parity, sharpe
    """
    if mode == "sharpe" and returns_data:
        return sharpe_optimized_weights(returns_data, volatilities or [], len(selected))
    elif mode == "risk_parity" and volatilities:
        return risk_parity_weights(volatilities)
    else:
        # Inverse volatility (simplest, most robust)
        if volatilities:
            inv_vols = [1.0 / max(v / 100, 0.05) for v in volatilities]
            total = sum(inv_vols)
            return [iv / total for iv in inv_vols] if total > 0 else [1.0/len(selected)] * len(selected)
        n = len(selected)
        return [1.0 / n] * n

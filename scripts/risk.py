#!/usr/bin/env python3
"""
Phase 4: Risk Management Module
  - Trailing stop-loss (15% from entry/peak)
  - Correlation penalty (downweight correlated assets)
  - Max drawdown guard (halt if >20% portfolio drawdown)
Integrates into the scoring pipeline.
"""
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


# ── Trailing Stop-Loss ──────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    entry_price: float
    peak_price: float
    quantity: float
    entry_date: str

    @property
    def stop_price(self) -> float:
        """15% trailing stop from peak."""
        return self.peak_price * 0.85

    @property
    def is_stopped(self) -> bool:
        return self.peak_price > 0 and self.stop_price > 0

    def update_peak(self, current_price: float):
        if current_price > self.peak_price:
            self.peak_price = current_price

    def should_exit(self, current_price: float) -> bool:
        return current_price <= self.stop_price


class StopLossManager:
    """Manages trailing stop-loss for all positions."""

    def __init__(self, stop_pct: float = 0.15):
        self.stop_pct = stop_pct
        self.positions: Dict[str, Position] = {}

    def open(self, ticker: str, price: float, qty: float, date: str):
        self.positions[ticker] = Position(
            ticker=ticker,
            entry_price=price,
            peak_price=price,
            quantity=qty,
            entry_date=date,
        )

    def update(self, ticker: str, current_price: float):
        if ticker in self.positions:
            self.positions[ticker].update_peak(current_price)

    def check(self, ticker: str, current_price: float) -> bool:
        """Returns True if position should be exited."""
        if ticker not in self.positions:
            return False
        return self.positions[ticker].should_exit(current_price)

    def get_stops(self) -> Dict[str, float]:
        """Get current stop prices for all positions."""
        return {t: p.stop_price for t, p in self.positions.items() if p.is_stopped}

    def remove(self, ticker: str):
        self.positions.pop(ticker, None)


# ── Correlation Penalty ─────────────────────────────────────────

def pearson_correlation(x: List[float], y: List[float]) -> float:
    """Compute Pearson correlation between two equal-length series."""
    n = min(len(x), len(y))
    if n < 5:
        return 0.0

    mx = sum(x[:n]) / n
    my = sum(y[:n]) / n

    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    denom_x = math.sqrt(sum((xi - mx) ** 2 for xi in x[:n]))
    denom_y = math.sqrt(sum((yi - my) ** 2 for yi in y[:n]))

    if denom_x == 0 or denom_y == 0:
        return 0.0
    return num / (denom_x * denom_y)


def compute_correlation_matrix(
    price_data: Dict[str, List[float]],
    lookback: int = 30,
) -> Dict[str, Dict[str, float]]:
    """Compute pairwise correlation matrix from price series."""
    tickers = list(price_data.keys())
    matrix = {}
    for t1 in tickers:
        matrix[t1] = {}
        for t2 in tickers:
            if t1 == t2:
                matrix[t1][t2] = 1.0
            elif t2 in matrix and t1 in matrix[t2]:
                matrix[t1][t2] = matrix[t2][t1]
            else:
                p1 = price_data[t1][-lookback:] if len(price_data[t1]) >= lookback else price_data[t1]
                p2 = price_data[t2][-lookback:] if len(price_data[t2]) >= lookback else price_data[t2]
                matrix[t1][t2] = pearson_correlation(p1, p2)
    return matrix


def apply_correlation_penalty(
    selected: List[Dict],
    correlation_matrix: Dict[str, Dict[str, float]],
    max_correlation: float = 0.70,
    penalty_strength: float = 0.5,
) -> List[float]:
    """
    Downweight assets that are highly correlated with already-selected assets.
    Returns adjustment multipliers (0-1) for each asset.
    """
    n = len(selected)
    multipliers = [1.0] * n

    for i in range(n):
        ticker_i = selected[i].get("ticker", "")
        for j in range(i):
            ticker_j = selected[j].get("ticker", "")
            corr = correlation_matrix.get(ticker_i, {}).get(ticker_j, 0)
            if corr > max_correlation:
                # Penalty: reduce weight proportional to correlation excess
                excess = corr - max_correlation
                penalty = excess * penalty_strength
                multipliers[i] = max(0.3, multipliers[i] - penalty)

    return multipliers


# ── Max Drawdown Guard ──────────────────────────────────────────

@dataclass
class DrawdownGuard:
    """Tracks portfolio drawdown and can halt rebalancing."""

    max_drawdown_pct: float = 0.20      # Halt if >20% drawdown
    portfolio_peak: float = 0.0
    current_drawdown: float = 0.0
    is_halted: bool = False
    halt_reason: str = ""

    def update(self, portfolio_value: float):
        if portfolio_value > self.portfolio_peak:
            self.portfolio_peak = portfolio_value

        if self.portfolio_peak > 0:
            self.current_drawdown = (self.portfolio_peak - portfolio_value) / self.portfolio_peak
        else:
            self.current_drawdown = 0

        if self.current_drawdown > self.max_drawdown_pct and not self.is_halted:
            self.is_halted = True
            self.halt_reason = f"Max drawdown ({self.current_drawdown:.1%}) > {self.max_drawdown_pct:.0%}"

    def should_halt(self) -> bool:
        return self.is_halted

    def resume_if_recovered(self, portfolio_value: float) -> bool:
        """Resume if recovered to within 10% drawdown."""
        if self.is_halted and self.portfolio_peak > 0:
            dd = (self.portfolio_peak - portfolio_value) / self.portfolio_peak
            if dd < self.max_drawdown_pct * 0.5:
                self.is_halted = False
                return True
        return False


# ── Combined Risk Manager ───────────────────────────────────────

class RiskManager:
    """Centralized risk management for portfolio construction."""

    def __init__(
        self,
        stop_loss_pct: float = 0.15,
        max_drawdown: float = 0.20,
        max_correlation: float = 0.70,
        correlation_penalty: float = 0.5,
        max_position_pct: float = 0.25,
    ):
        self.stop_manager = StopLossManager(stop_loss_pct)
        self.drawdown_guard = DrawdownGuard(max_drawdown)
        self.max_correlation = max_correlation
        self.correlation_penalty = correlation_penalty
        self.max_position_pct = max_position_pct

    def apply_all(
        self,
        selected: List[Dict],
        correlation_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        portfolio_value: float = 0,
    ) -> Tuple[List[Dict], List[str]]:
        """
        Apply all risk measures to a candidate portfolio.
        Returns (adjusted_allocations, alerts).
        """
        alerts = []

        # 1. Drawdown guard
        self.drawdown_guard.update(portfolio_value)
        if self.drawdown_guard.should_halt():
            alerts.append(f"🛑 PORTFOLIO HALTED: {self.drawdown_guard.halt_reason}")
            return [], alerts

        # 2. Correlation penalty
        if correlation_matrix:
            multipliers = apply_correlation_penalty(
                selected, correlation_matrix,
                self.max_correlation, self.correlation_penalty
            )
            for i, mult in enumerate(multipliers):
                if mult < 0.9:
                    alerts.append(f"🔗 {selected[i].get('name','?')} penalized (correlation ×{mult:.2f})")
                if "allocation_pct" in selected[i]:
                    selected[i]["allocation_pct"] = round(selected[i]["allocation_pct"] * mult, 1)
                    selected[i]["allocation_usd"] = round(selected[i].get("allocation_usd", 0) * mult, 2)

        # 3. Position size cap
        for asset in selected:
            pct = asset.get("allocation_pct", 0)
            if pct > self.max_position_pct * 100:
                asset["allocation_pct"] = self.max_position_pct * 100
                asset["allocation_usd"] = round(asset.get("allocation_usd", 0) * self.max_position_pct * 100 / pct, 2)
                alerts.append(f"📏 {asset.get('name','?')} capped at {self.max_position_pct:.0%}")

        return selected, alerts

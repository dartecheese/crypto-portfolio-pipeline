#!/usr/bin/env python3
"""
Phase 7: Performance Dashboard
  - Daily equity curve tracking
  - Drawdown analysis
  - Sharpe ratio computation
  - Strategy comparison
"""
import json, os, sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import math

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_DIR = os.path.join(PIPELINE_DIR, "portfolio")
DASHBOARD_DIR = os.path.join(PIPELINE_DIR, "dashboard")


def load_portfolio_history() -> List[Dict]:
    """Load all historical portfolio snapshots."""
    snapshots = []
    if not os.path.exists(PORTFOLIO_DIR):
        return snapshots

    for fname in sorted(os.listdir(PORTFOLIO_DIR)):
        if not fname.startswith("portfolio-v4-") or not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(PORTFOLIO_DIR, fname)) as f:
                snapshots.append(json.load(f))
        except:
            pass
    return snapshots


def compute_performance_metrics(snapshots: List[Dict]) -> Dict:
    """Compute performance metrics from historical snapshots."""
    if len(snapshots) < 2:
        return {"status": "insufficient_data", "snapshots": len(snapshots)}

    values = [s["total_capital"] for s in snapshots
              if s.get("allocations") and sum(a.get("allocation_usd", 0) for a in s["allocations"]) > 0]

    if len(values) < 2:
        return {"status": "no_valid_data"}

    # Returns
    total_return = (values[-1] - values[0]) / values[0]
    daily_returns = []
    peak = values[0]
    max_dd = 0

    for i in range(1, len(values)):
        r = (values[i] - values[i-1]) / values[i-1] if values[i-1] > 0 else 0
        daily_returns.append(r)
        if values[i] > peak:
            peak = values[i]
        dd = (peak - values[i]) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Sharpe (assuming daily snapshots)
    if len(daily_returns) > 1:
        mean_r = sum(daily_returns) / len(daily_returns)
        std_r = math.sqrt(sum((r - mean_r)**2 for r in daily_returns) / (len(daily_returns) - 1)) if len(daily_returns) > 1 else 0.01
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0

    # Win rate
    positive_days = sum(1 for r in daily_returns if r > 0)
    win_rate = positive_days / len(daily_returns) if daily_returns else 0

    # Category exposure
    cat_exposure = {}
    latest = snapshots[-1]
    for a in latest.get("allocations", []):
        c = a.get("category", "?")
        cat_exposure[c] = cat_exposure.get(c, 0) + a.get("allocation_pct", 0)

    return {
        "period": f"{snapshots[0].get('timestamp','?')[:10]} → {snapshots[-1].get('timestamp','?')[:10]}",
        "snapshots": len(snapshots),
        "total_return_pct": round(total_return * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "latest_value": values[-1],
        "category_exposure": {c: round(p, 1) for c, p in sorted(cat_exposure.items(), key=lambda x: -x[1])},
        "regime": latest.get("strategy", "?"),
        "risk_alerts": latest.get("risk_alerts", []),
    }


def print_dashboard(metrics: Dict):
    """Print a clean dashboard."""
    print(f"\n{'='*60}")
    print(f"  📊 PORTFOLIO DASHBOARD")
    print(f"{'='*60}")
    if metrics.get("status"):
        print(f"  Status: {metrics['status']}")
        return

    print(f"  Period:      {metrics['period']}")
    print(f"  Snapshots:   {metrics['snapshots']}")
    print(f"  Return:      {metrics['total_return_pct']:+.2f}%")
    print(f"  Max DD:      {metrics['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe:      {metrics['sharpe_ratio']:.2f}")
    print(f"  Win Rate:    {metrics['win_rate_pct']:.1f}%")
    print(f"  Value:       ${metrics['latest_value']:,.2f}")
    print(f"  Regime:      {metrics.get('regime','?')}")
    print(f"  Exposure:    {metrics.get('category_exposure',{})}")
    if metrics.get("risk_alerts"):
        print(f"  Alerts:      {' | '.join(metrics['risk_alerts'])}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    snapshots = load_portfolio_history()
    metrics = compute_performance_metrics(snapshots)
    print_dashboard(metrics)

    # Save dashboard
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    path = os.path.join(DASHBOARD_DIR, f"dashboard-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json")
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    with open(os.path.join(DASHBOARD_DIR, "latest.json"), "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"   Dashboard saved → {path}")

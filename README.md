# 🧠 Crypto Portfolio Pipeline

**Multi-asset, crypto-native portfolio construction engine with regime-aware scoring, risk management, and automated rebalancing.**

Covers **67+ assets** across 13 categories: crypto L1/L2, DeFi, AI tokens, memes, tokenized equities (Ondo), commodities (gold, oil, metals), indexes (SPY, QQQ), treasuries, and RWA protocols.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DAILY CRON / MANUAL                   │
├──────────────────┬──────────────────┬───────────────────┤
│  TradingView API │  CoinGecko API   │  Hyperliquid API   │
│  35 crypto/RWA   │  31 Ondo/ETFs    │  230 perp markets  │
│  (RSI, ATH, mom) │  (price, ATH)    │  (PAXG, SPX, etc)  │
├──────────────────┴──────────────────┴───────────────────┤
│              COMBINED SCREEN (67+ assets)                │
├─────────────────────────────────────────────────────────┤
│              REGIME DETECTION                             │
│   Multi-timeframe (90d+180d) → bear/bull/neutral        │
├─────────────────────────────────────────────────────────┤
│          MULTI-WINDOW SCORING ENGINE                      │
│   60d + 90d + 120d windows averaged                      │
│   Momentum (40%) + Value (35%) + Risk-Inv (25%)         │
│   Bear regime → momentum 55%, value 15% (anti-knife)   │
├─────────────────────────────────────────────────────────┤
│           RISK MANAGEMENT                                 │
│   Stop-loss (15% trailing) | Correlation penalty        │
│   Category diversification (max 30%) | Max DD guard     │
│   Volatility-adjusted sizing | Position caps (25%)     │
├─────────────────────────────────────────────────────────┤
│       PORTFOLIO OPTIMIZATION                              │
│   Inverse-vol / Risk parity / Sharpe-optimized           │
├─────────────────────────────────────────────────────────┤
│              OUTPUT + DASHBOARD                           │
│   Ranked allocations + Stop-loss levels + Alerts         │
│   Performance tracking + Equity curve + Sharpe          │
└─────────────────────────────────────────────────────────┘
```

## Asset Universe

| Category | Count | Source | Examples |
|---|---|---|---|
| **Crypto L1** | 14 | TradingView | BTC, ETH, SOL, SUI, NEAR, APT, AVAX |
| **Crypto L2** | 3 | TradingView | OP, ARB, STRK |
| **DeFi** | 7 | TradingView | INJ, RUNE, PENDLE, UNI, SNX, LINK, AAVE |
| **AI Crypto** | 4 | TradingView | TAO, FET, AR, KAITO |
| **Meme** | 2 | TradingView | DOGE, BERA |
| **RWA Infra** | 5 | TradingView + HL | ONDO, ENA, PAXG, MORPHO, USUAL |
| **Commodities** | 10 | CoinGecko/Ondo | GLD, SLV, USO, BNO, UNG, COPX, URA |
| **Mag7 Equities** | 7 | CoinGecko/Ondo | AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA |
| **Crypto Stocks** | 3 | CoinGecko/Ondo | COIN, MSTR, HOOD |
| **AI Stocks** | 4 | CoinGecko/Ondo | PLTR, TSM, AMD, AVGO |
| **Indexes** | 3 | CoinGecko/Ondo | SPY, QQQ, IWM |
| **Treasuries** | 4 | CoinGecko/Ondo | SGOV, SHY, IEF, TLT |
| **Data** | 1 | TradingView | PYTH |

## Backtest Results

| Window | V2 (old) | V4 (regime-aware) | Improvement |
|---|---|---|---|
| **60d** | -2.7% | **+7.5%** | +10.2% |
| **90d** | +36.2%* | **+9.0%** | Realistic, smooth |
| **120d** | +31.0%* | **+9.8%** | Consistent |
| **180d** | +6.1% | **+18.0%** | +11.9% |
| **365d** | -29.3% | **+30.3%** | **+59.6%** |

*V2 inflated by artifacts. V4 is the real number.

**All V4 windows are positive.** The regime filter eliminated the falling-knife problem.

## Quick Start

```bash
# Install dependencies
pip install yfinance --break-system-packages

# Run live pipeline (requires screen data in screens/)
python3 scripts/score.py screens/combined-2026-05-14.json -s balanced -n 15 -c 25000

# Run backtest
python3 scripts/backtest.py 90   # 90-day window
python3 scripts/backtest.py 365  # 1-year window

# Generate dashboard
python3 scripts/dashboard.py
```

## Files

```
crypto-portfolio-pipeline/
├── README.md
├── configs/
│   └── universe.json          ← Asset definitions (67 tickers, 13 categories)
├── screens/                    ← Raw market data
│   ├── screen-YYYY-MM-DD.json  ← TradingView crypto
│   ├── rwa-coingecko-YYYY-MM-DD.json ← Ondo/ETF data
│   └── combined-YYYY-MM-DD.json ← Merged (all sources)
├── portfolio/                  ← Output portfolios
│   ├── portfolio-v4-*.json     ← V4 allocations with stop-loss
│   ├── rankings-v4-*.json      ← V4 full rankings
│   └── latest-v4-*.json        ← Always current
├── backtests/                  ← Historical backtest results
├── dashboard/                  ← Performance metrics
└── scripts/
    ├── score.py                ← Main scoring + portfolio engine (v4)
    ├── backtest.py             ← Backtest engine (yfinance, v3)
    ├── risk.py                 ← Risk management (stop-loss, correlation, DD guard)
    ├── signals.py              ← Signal enrichment (Hyperliquid, DeFi TVL, social)
    ├── optimize.py             ← Portfolio optimization (risk parity, Sharpe, grid search)
    ├── rwa_feed.py             ← CoinGecko RWA price feed
    ├── dashboard.py            ← Performance dashboard
    └── run.sh                  ← Daily cron runner
```

## Strategy Modes

| Mode | Momentum | Value | Risk-Inv | Best For |
|---|---|---|---|---|
| **balanced** | 35% | 35% | 30% | All-weather |
| **momentum** | 50% | 20% | 30% | Trending markets |
| **value** | 20% | 50% | 30% | Mean-reversion |
| **growth** | 40% | 25% | 35% | Risk-on |

**Regime override:** When bear market detected, all modes shift to momentum 55% / value 15% / risk 30%.

## Risk Management

| Feature | Setting | Description |
|---|---|---|
| **Stop-loss** | 15% trailing | Cut positions 15% below peak |
| **Correlation penalty** | Max 0.70 | Downweight correlated assets |
| **Category diversification** | Max 30% | No single category dominates |
| **Max drawdown guard** | 20% | Halt rebalancing if DD exceeds |
| **Position cap** | 25% | Maximum single position size |
| **Volatility adjustment** | 1.5x max | Lower weight for high-vol |
| **Momentum floor** | -15% monthly | Exclude deep losers |
| **Liquidity filter** | $50K min volume | Filter micro-caps |

## Roadmap

- [x] Multi-window scoring (60/90/120d)
- [x] Regime filter (bear → momentum)
- [x] Category diversification
- [x] Volatility-adjusted sizing
- [x] Trailing stop-loss
- [x] Correlation penalty
- [x] Max drawdown guard
- [x] DeFi TVL enrichment (DefiLlama)
- [x] Risk parity / Sharpe optimization
- [x] Multi-timeframe regime
- [x] Parameter grid search framework
- [ ] Hyperliquid funding rate integration
- [ ] Social sentiment (LunarCrush/Santiment)
- [ ] On-chain metrics (active addresses, fees)
- [ ] Live execution bridge (Hyperliquid API)
- [ ] Real-time monitoring dashboard

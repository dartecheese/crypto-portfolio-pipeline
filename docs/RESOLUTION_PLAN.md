# Resolution Plan: Paper Trading Accuracy + Strategy Performance

**Date:** 2026-05-14  
**Problem:** Paper PnL is inflated (~$1,154 → -$2,293 after real costs). Only 1 of 15 strategy types survives.

---

## Root Cause

The two problems are the same problem seen from different angles:

```
Paper engine gives "free" fills      Strategies optimize for the wrong thing
(mid-price, no spread, no fees)  →  (they chase paper alpha that doesn't exist in live)
                ↓                                    ↓
         Inflated PnL                        Deployed to wrong venues
                ↓                                    ↓
         └──────────── Both lead to: ───────────────┘
              Strategies that look profitable but aren't
```

**You can't fix strategy performance without first fixing paper accuracy.**  
**You can't validate paper accuracy without honest cost modeling.**

---

## The Fix: Three Parallel Tracks

### Track 1: Fix Paper Engine (QWNT side — 1 day)

Implement the handover from `docs/QWNT_PAPER_TRADING_REFACTOR.md`.

**Minimum viable fix (spread-only, ~20 lines):**
```typescript
// In paper trade execution:
const liquidity = await getPoolLiquidity(tokenAddress);
const halfSpread = liquidity > 100000 ? 0.005 : liquidity > 50000 ? 0.015 : 0.04;
const fillPrice = side === 'buy' 
  ? midPrice * (1 + halfSpread)
  : midPrice * (1 - halfSpread);
```

**Why this first:** Every strategy decision from this point forward is based on honest PnL.

**Acceptance criteria:**
- No sub-700ms trades
- All trades have `fee_usd > 0`
- Buy price > mid, sell price < mid
- Failed trade count > 0
- Meme agent PnL drops from +$85 → +$30-35 (matches our estimate)

---

### Track 2: Venue Economics Restructure (Strategy side — 1-2 days)

The biggest performance lever is **venue selection**. Spread costs vary by 160x:

| Venue | Spread | Fee | Failure | Total Cost |
|---|---|---|---|---|
| **Hyperliquid** | 0.02-0.05% | 0.025% | 0.5% | **~0.1%** |
| Jupiter (major pairs) | 0.3% | 0.1% | 5% | **~0.5%** |
| Jupiter (mid pairs) | 2% | 0.25% | 10% | **~3%** |
| Pumpswap ($50K+ liq) | 3% | 0.25% | 15% | **~5%** |
| Pumpswap ($10K liq) | **8%** | 0.25% | 20% | **~12%** |
| Pumpswap (<$5K liq) | **15%** | 0.25% | 30% | **~25%** |

**New strategy deployment rules:**

```
┌─────────────────────────────────────────────────────────┐
│                 VENUE-BASED STRATEGY MAP                 │
├──────────────────┬──────────────────────────────────────┤
│ Hyperliquid      │ trend-trader, mean-rev, momentum,    │
│ (0.1% cost)     │ hl-arb → ALL survive easily          │
├──────────────────┼──────────────────────────────────────┤
│ Jupiter major    │ yield-optimizer, swing trader        │
│ (0.5% cost)     │ → survives if alpha > 1%             │
├──────────────────┼──────────────────────────────────────┤
│ Jupiter mid      │ meme-sniper (filtered)               │
│ (3% cost)       │ → needs 5%+ alpha per trade          │
├──────────────────┼──────────────────────────────────────┤
│ Pumpswap $50K+   │ meme-sniper (curated)                │
│ (5% cost)       │ → needs 8%+ alpha, high risk         │
├──────────────────┼──────────────────────────────────────┤
│ Pumpswap <$10K   │ 🚫 DO NOT DEPLOY                    │
│ (12-25% cost)   │ → mathematically impossible to win   │
└──────────────────┴──────────────────────────────────────┘
```

**Specific changes to meme-sniper:**

```typescript
// BEFORE (current)
const tokenFilter = {
  minVolume24h: 10000,
  maxAgeHours: 48,
  // No liquidity filter! Deploys to $1K pools with 15% spread
};

// AFTER (fixed)
const tokenFilter = {
  minVolume24h: 50000,
  minLiquidityUsd: 50000,     // ← CRITICAL: spread drops from 8% → 3%
  maxAgeHours: 72,            // Wider window = more established tokens
  minTrades24h: 200,          // Active trading
  excludePumpswapBondingCurve: true,  // Skip migration-risk tokens
};
```

**Impact estimate on meme-sniper:**
```
Current:  842 trades on tokens avg $10K liq → 8% spread → -$217 aggregate
Fixed:    ~200 trades on tokens $50K+ liq → 3% spread → +$200-400 aggregate
```

---

### Track 3: Agent Lifecycle Management (Strategy side — 1 day)

**Problem:** Losing agents burn their full allocation on spread before dying.

**Fix: Three-strike kill system**

```typescript
interface AgentHealth {
  tradesExecuted: number;
  pnlAfterCosts: number;        // NEW: PnL minus estimated spread + fees
  costBasis: number;            // Total spread + fees paid so far
  killThreshold: number;        // Kill if PnL < -costBasis * N
  
  // Three strikes:
  // Strike 1: After 10 trades, if PnL < -10% → reduce allocation 50%
  // Strike 2: After 20 trades, if PnL < -15% → pause agent 24h
  // Strike 3: After 30 trades, if PnL < -20% → KILL
}

function evaluateAgentHealth(agent: Agent): 'healthy' | 'warn' | 'kill' {
  const { tradesExecuted, pnlAfterCosts, costBasis, allocation } = agent;
  
  if (tradesExecuted >= 30 && pnlAfterCosts < -allocation * 0.20) {
    return 'kill';  // Strike 3: burned 20% of allocation, gone
  }
  if (tradesExecuted >= 20 && pnlAfterCosts < -allocation * 0.15) {
    return 'warn';  // Strike 2: struggling, pause
  }
  if (tradesExecuted >= 10 && pnlAfterCosts < -allocation * 0.10) {
    return 'warn';  // Strike 1: early warning
  }
  return 'healthy';
}
```

**Why this matters:** The 15 worst meme agents drag the aggregate from +$85 to -$217. Killing them at strike 1 (after 10 trades, -10%) would save ~$150 in wasted spread costs.

---

## Combined Impact Estimate

| | Current | After All Fixes |
|---|---|---|
| **Paper engine** | Mid-price fills | Spread-adjusted fills |
| **Meme-sniper aggregate** | -$217 | **+$200 to +$400** |
| **Hyperliquid strats** | $0 (idle) | **+$50-150** (deploy here) |
| **Total portfolio PnL** | -$2,293 | **+$200 to +$600** |
| **Win rate (agent level)** | 35% survive | **50-60% survive** |
| **Max single-agent drawdown** | -$55 (full alloc burned) | **-$11** (killed at strike 1) |

---

## Implementation Order (by impact per hour)

| Step | What | Effort | Impact |
|---|---|---|---|
| **1** | Spread model in paper engine | 2 hours | Fixes price accuracy, enables honest eval |
| **2** | Liquidity filter on meme-sniper | 1 hour | Cuts spread cost from 8% → 3% |
| **3** | Deploy Hyperliquid strats with real capital | 2 hours | Adds profitable, low-cost strategies |
| **4** | Three-strike agent kill system | 2 hours | Caps losses on bad agents |
| **5** | Full fee/latency/MEV model | 4 hours | Completes paper accuracy |
| **6** | Agent realism score in UI | 2 hours | Shows estimated real PnL alongside paper |

**Steps 1-3 (5 hours) get you to a positive portfolio.**
Steps 4-6 complete the system.

---

## The Nuclear Option

If you want maximum performance with minimum code change:

**Kill ALL non-Hyperliquid agents. Deploy everything to Hyperliquid.**

```
Hyperliquid spreads: 0.02-0.05%
vs
Pumpswap spreads: 5-15%

Same alpha, 100-300x lower costs.

trend-trader on HL:    survives easily (0.05% spread)
mean-rev on HL:       survives easily (0.05% spread)
momentum on HL:       survives easily (0.05% spread)
meme-sniper on Solana: mathematically impossible (<$50K liq)

Current deploy:  80% Solana memes, 20% HL
Optimal deploy:  80% HL, 20% curated Solana (liquidity >$50K)
```

---

## Decision Points

1. **Paper engine fix:** Do you want the QWNT team to implement the full handover, or just the spread-only patch first?

2. **Strategy migration:** Move meme-sniper to liquidity-filtered only, or kill it entirely and go all-in on Hyperliquid strats?

3. **Agent lifecycle:** Implement three-strike kills, or simpler "kill if down 15% after 20 trades"?

4. **Pipeline integration:** After paper engine is fixed, should the portfolio pipeline send its weekly picks directly to QWNT as curated agent deployments?

# QWNT Paper Trading — Realism Refactor Handover

**Date:** 2026-05-14  
**Audited by:** Crypto Portfolio Pipeline audit  
**Agent tested:** `p22-meme-high2` (meme-sniper, 842 trades, $55 allocation)  
**Finding:** Paper PnL of +$85.72 is approximately **-$52 to -$90 in live markets** due to unmodeled costs.

---

## The 5 Gaps & Fixes

### GAP 1: Zero Transaction Costs (Priority Fix)

**Current behavior:**
```json
"fee_usd": 0.000000  // on ALL 842 trades
```

**What's missing:**
- DEX swap fee (pumpswap: 0.25%, Jupiter: 0.1-0.3%, Raydium: 0.25%)
- Solana transaction fee (~0.000005 SOL ≈ $0.00001)
- Jito priority tip ($0.001-0.01 for timely inclusion, critical for memes)
- Compute unit cost (higher for complex swap instructions)

**Fix:**
```typescript
// In paper trading engine's executeTrade()
const DEX_FEES = {
  pumpswap: 0.0025,   // 0.25%
  jupiter: 0.001,     // 0.1% (varies by route)
  raydium: 0.0025,    // 0.25%
  default: 0.003,     // 0.3% conservative
};

const PRIORITY_FEE_SOL = 0.00001;  // ~$1.50 at SOL=$150 — Jito tip
const BASE_TX_FEE_SOL = 0.000005;  // Solana base fee

function calculateTradeFees(trade) {
  const dexFee = trade.value * (DEX_FEES[trade.dex] || DEX_FEES.default);
  const priorityFee = PRIORITY_FEE_SOL * solPrice;
  const baseFee = BASE_TX_FEE_SOL * solPrice;
  
  trade.fee_usd = dexFee + priorityFee + baseFee;
  trade.realized_pnl -= trade.fee_usd;  // Subtract from PnL
}
```

**Impact:** ~$0.01-0.02 per $2 trade. Over 842 trades: $8-17.

---

### GAP 2: Bid-Ask Spread (Largest Impact — 70% of the gap)

**Current behavior:**
```
Paper engine fills at mid-price or last-trade price.
No spread applied to buy or sell.
```

**What's missing:**
- Every trade crosses the spread — buys at ask, sells at bid
- Meme coin spreads: 2-5% for liquid tokens ($100K+ pool), 5-15% for mid ($10K-50K), 15-30% for micro ($1K-10K)
- The paper engine is getting "free" fills at mid-price, avoiding ~5% per round-trip

**Fix:**
```typescript
function getSpreadMultiplier(liquidityUsd: number): number {
  // Wider spread for thinner liquidity
  if (liquidityUsd > 100000) return 0.01;   // 1% half-spread
  if (liquidityUsd > 50000)  return 0.015;  // 1.5%
  if (liquidityUsd > 10000)  return 0.04;   // 4%
  if (liquidityUsd > 1000)   return 0.08;   // 8%
  return 0.15;                               // 15%
}

function applySpread(price, side, liquidityUsd) {
  const halfSpread = getSpreadMultiplier(liquidityUsd);
  if (side === 'buy')  return price * (1 + halfSpread);  // Pay ask
  if (side === 'sell') return price * (1 - halfSpread);  // Receive bid
  return price;
}

// Use when recording trade prices:
const midPrice = fetchFromJupiterOrBirdeye(token);
trade.price = applySpread(midPrice, trade.type, poolLiquidity);
```

**Real-time liquidity lookup:**
```typescript
async function getPoolLiquidity(tokenAddress: string): Promise<number> {
  // Cache for 60 seconds to avoid rate limits
  const cached = liquidityCache.get(tokenAddress);
  if (cached && Date.now() - cached.ts < 60000) return cached.value;
  
  const res = await fetch(
    `https://api.dexscreener.com/latest/dex/tokens/${tokenAddress}`
  );
  const data = await res.json();
  const liquidity = data.pairs?.[0]?.liquidity?.usd || 5000; // Default $5K
  liquidityCache.set(tokenAddress, { value: liquidity, ts: Date.now() });
  return liquidity;
}
```

**Impact:** ~5% average round-trip on $2 trades. Over 842 trades: $84-168.

---

### GAP 3: Failed Transactions

**Current behavior:**
```
0 failed transactions out of 842 (0%)
```

**What's missing:**
- Solana congestion: 5-15% normal, 20-40% during meme launches
- Slippage failures: token moves >slippage tolerance before confirmation
- Frontrunning: another tx lands first, your price is stale
- Pump.fun bonding curve migrations: tokens migrate mid-trade

**Fix:**
```typescript
function shouldTransactionFail(token: TokenMetadata): boolean {
  // Base failure rate
  let failRate = 0.05;  // 5% baseline
  
  // Higher failure for meme coins
  if (token.isMemeCoin) failRate += 0.10;
  
  // Higher during high volatility
  if (token.volatility24h > 0.5) failRate += 0.05;
  
  // Higher for pump.fun tokens (migration risk)
  if (token.dex === 'pumpswap' && token.age < 3600) failRate += 0.10;
  
  // Higher during congestion (check Solana TPS)
  const solanaCongestion = getSolanaCongestionLevel();
  if (solanaCongestion > 0.8) failRate += 0.10;
  
  return Math.random() < failRate;
}

function handleFailedTrade(trade) {
  // Still pay priority fee (tx was submitted)
  trade.fee_usd = PRIORITY_FEE_SOL * solPrice;
  trade.status = 'failed';
  trade.pnl = -trade.fee_usd;  // Loss = wasted fee
  
  // Slippage: if trade "partially filled" in simulation
  // then price moved against you — model partial fill at worse price
  if (Math.random() < 0.3) {
    // 30% chance of partial fill at worse price
    const slipPrice = trade.price * (trade.type === 'buy' ? 1.10 : 0.90);
    trade.price = slipPrice;
    trade.status = 'partial';
    // Recalculate PnL with worse price
  }
}
```

**Impact:** 15% × 842 = 126 failed trades × $0.003 wasted fee = $0.38.  
But the hidden cost is missed opportunities and partial fills at worse prices — roughly 3-5% PnL reduction.

---

### GAP 4: Execution Latency

**Current behavior:**
```
8ms between trades (impossible on Solana)
16 of 50 trades executed in <700ms (below minimum block time)
```

**What's missing:**
- Solana block time: 400ms minimum
- RPC latency: 100-300ms
- Transaction confirmation: 100-500ms (longer for congested blocks)
- Total minimum: 700ms per trade (realistic: 1-3 seconds)

**Fix:**
```typescript
const MIN_TRADE_INTERVAL_MS = 700;  // Absolute minimum
const TYPICAL_TRADE_INTERVAL_MS = 1500;  // Typical

function applyExecutionDelay() {
  const delay = MIN_TRADE_INTERVAL_MS + Math.random() * 1500;
  return new Promise(resolve => setTimeout(resolve, delay));
}

// Price drift during execution
function applyPriceDrift(price, side, latencyMs) {
  // Meme coins move fast — even 1 second matters
  const annualizedVol = 5.0;  // 500% annual vol for meme coins
  const secondVol = annualizedVol / Math.sqrt(365 * 24 * 3600);
  const drift = secondVol * (latencyMs / 1000) * (Math.random() - 0.5) * 2;
  
  // Drift is always adverse (slippage direction)
  if (side === 'buy')  return price * (1 + Math.abs(drift));
  if (side === 'sell') return price * (1 - Math.abs(drift));
  return price;
}

// In trade execution:
await applyExecutionDelay();
const executedPrice = applyPriceDrift(midPrice, trade.type, actualLatency);
trade.price = executedPrice;
```

**Impact:** Sub-second trades execute at prices 1-3% worse than the snapshot price. Over 32% of trades affected. ~5-8% total PnL reduction.

---

### GAP 5: MEV & Sandwich Attacks

**Current behavior:**
```
No MEV modeling. Trades >$5 execute with zero MEV loss.
```

**What's missing:**
- Sandwich bots monitor mempool for profitable trades
- Trades >$5 on meme coins are sandwichable
- Estimated 2-5% of value extracted per sandwichable trade
- Jito bundles can mitigate but not eliminate

**Fix:**
```typescript
function isSandwichable(trade): boolean {
  return (
    trade.value > 3 &&                    // Above $3
    trade.token.isMemeCoin &&             // Meme coin
    trade.token.liquidity < 100000 &&     // Thin liquidity
    !trade.useJitoBundle                  // Not protected
  );
}

function applyMEVImpact(trade) {
  if (!isSandwichable(trade)) return;
  
  const sandwichProbability = 0.05;  // 5% chance of being sandwiched
  if (Math.random() < sandwichProbability) {
    const mevLoss = trade.value * (0.02 + Math.random() * 0.05);  // 2-7%
    trade.price *= (trade.type === 'buy') ? (1 + mevLoss/trade.value) : (1 - mevLoss/trade.value);
    trade.mev_loss = mevLoss;
    trade.pnl -= mevLoss;
  }
}
```

**Impact:** ~$6-8 on the 12 sandwichable >$5 trades in this sample.

---

## Implementation Priority

| Priority | Gap | Impact | Effort | Fix |
|---|---|---|---|---|
| **P0** | Spread | -$84 to -$168 | Low | Apply spread multiplier to fills |
| **P1** | Fees | -$8 to -$17 | Low | Add DEX + priority fee calc |
| **P1** | Execution latency | -5-8% PnL | Medium | Enforce min 700ms + price drift |
| **P2** | Failed transactions | -3-5% PnL | Medium | Probabilistic failure + partial fills |
| **P2** | MEV/sandwich | -$6 to -$8 | Low | Probabilistic sandwich model |

**P0+P1 alone fixes ~85% of the gap.**

---

## Implementation Architecture

```
paper-trading-engine/
├── costs/
│   ├── fees.ts            ← DEX fees, priority fees, gas
│   ├── spread.ts          ← Liquidity-based spread model
│   └── slippage.ts        ← Price impact + drift
├── execution/
│   ├── latency.ts         ← Block time delays + price drift
│   ├── failures.ts        ← Probabilistic failure model
│   └── mev.ts             ← Sandwich attack simulation
├── market-data/
│   ├── liquidity.ts       ← DexScreener/Jupiter liquidity cache
│   └── congestion.ts      ← Solana TPS/ congestion monitoring
└── realism-config.ts      ← All configurable parameters
```

### Configurable Parameters (for tuning)

```typescript
interface RealismConfig {
  // Spread
  spreadModel: 'liquidity-based' | 'fixed';
  minHalfSpread: number;        // 0.005 (0.5%)
  maxHalfSpread: number;        // 0.15 (15%)
  
  // Fees
  dexFeeBps: Record<string, number>;  // Per-DEX fee in basis points
  priorityFeeSol: number;       // 0.00001
  baseTxFeeSol: number;         // 0.000005
  
  // Execution
  minBlockTimeMs: number;       // 400
  typicalLatencyMs: number;     // 1500
  priceDriftVolMultiplier: number;  // 1.0 (1x implied vol)
  
  // Failures
  baseFailureRate: number;      // 0.05
  memeCoinFailureBonus: number; // 0.10
  highVolFailureBonus: number;  // 0.05
  
  // MEV
  mevSandwichProbability: number;  // 0.05
  mevLossMinPct: number;        // 0.02
  mevLossMaxPct: number;        // 0.07
  mevMinTradeValue: number;     // 3.0
}
```

---

## Validation After Refactor

After implementing, re-run the same agent and verify:

1. **Per-trade PnL should degrade** — Previously profitable trades should show smaller gains or flip to losses
2. **Win rate should drop** — From 63% trade-level to ~40-50%
3. **Total PnL should be negative** — If the -$52 to -$90 estimate is correct
4. **Spread cost should be the #1 line item** — Should appear in trade logs as `spread_cost_usd`
5. **No sub-700ms trades** — All timestamps should show >= 700ms gaps
6. **Some trades should fail** — Failed trade count should be >0 with wasted fees

### Acceptance Criteria

```
✅ All trades have fee_usd > 0
✅ Buy price > mid price (spread applied)
✅ Sell price < mid price (spread applied)
✅ Min trade interval >= 700ms
✅ Failed trade count > 0 (for strategies with >50 trades)
✅ MEV loss recorded on sandwichable trades
✅ Per-token PnL ≤ paper PnL (always pessimistic vs old engine)
```

---

## Quick Win: Spread-Only Patch

If full refactor is too much right now, this minimal change fixes 70% of the gap:

```typescript
// In your trade recording function, add:
function getRealisticPrice(midPrice, side, tokenAddress) {
  // Fetch liquidity (cached)
  const liquidity = await liquidityCache.get(tokenAddress);
  
  // Simple spread tiers
  let halfSpread = 0.04; // default 4%
  if (liquidity > 100000) halfSpread = 0.005;
  else if (liquidity > 50000) halfSpread = 0.015;
  else if (liquidity > 10000) halfSpread = 0.04;
  else halfSpread = 0.08;
  
  return side === 'buy' 
    ? midPrice * (1 + halfSpread) 
    : midPrice * (1 - halfSpread);
}

// Apply to every trade:
trade.price = await getRealisticPrice(rawPrice, trade.type, trade.token_address);
```

**This single change converts the paper PnL from +$85.72 to approximately +$1 to -$10.**

---

## Key Files to Modify (QWNT repo)

- `/apps/web/src/lib/trading/paper-engine.ts` — Core paper execution
- `/apps/web/src/lib/trading/execution/simulator.ts` — Trade simulation
- `/apps/web/src/lib/trading/costs/fees.ts` — Fee calculation
- `/apps/web/src/lib/market-data/dexscreener.ts` — Liquidity data
- `/apps/web/src/lib/market-data/jupiter.ts` — Price + spread

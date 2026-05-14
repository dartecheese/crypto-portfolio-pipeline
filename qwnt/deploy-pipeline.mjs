// Auto-generated QWNT Deployer — Pipeline v4
// Regime: NEUTRAL | Generated: 2026-05-14T12:30:29.038664+00:00
// 15 agents | $25,000 total capital

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API_BASE = 'https://qwnt.app';
const WALLET_FILE = path.join(__dirname, '..', '.paper-wallets.json');
const TRACKER = path.join(__dirname, '..', 'experiment-tracker.md');
const AGENT_SPACING_MS = 3500;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const WALLET_IDX = 91;  // Pipeline-dedicated wallet range: 91-95
const AGENTS_PER_WALLET = 15;

const PIPELINE_AGENTS = [
  {
    "label": "pipeline-ondo--ondo",
    "name": "ONDO \u2014 Ondo",
    "category": "rwa",
    "modules": [
      "hyperliquid-mean-rev",
      "drift-funding-arb"
    ],
    "allocationUsdc": 1217.5,
    "allocationPct": 4.9,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.2865,
    "pipelineScore": 67.7,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-suiusd",
    "name": "SUIUSD",
    "category": "l1",
    "modules": [
      "trend-trader",
      "hyperliquid-momentum"
    ],
    "allocationUsdc": 1799.59,
    "allocationPct": 7.2,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.9008,
    "pipelineScore": 60.7,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-strkusd",
    "name": "STRKUSD",
    "category": "l2",
    "modules": [
      "trend-trader",
      "hyperliquid-arb"
    ],
    "allocationUsdc": 902.17,
    "allocationPct": 3.6,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.0353,
    "pipelineScore": 59.5,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-dogeusd",
    "name": "DOGEUSD",
    "category": "meme",
    "modules": [
      "meme-sniper"
    ],
    "allocationUsdc": 2400.86,
    "allocationPct": 9.6,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.0851,
    "pipelineScore": 56.1,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-arbusd",
    "name": "ARBUSD",
    "category": "l2",
    "modules": [
      "trend-trader",
      "hyperliquid-arb"
    ],
    "allocationUsdc": 1444.53,
    "allocationPct": 5.8,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.0979,
    "pipelineScore": 55.0,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-uniusd",
    "name": "UNIUSD",
    "category": "defi",
    "modules": [
      "yield-optimizer",
      "dex-arbitrage"
    ],
    "allocationUsdc": 2038.82,
    "allocationPct": 8.2,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 2.709,
    "pipelineScore": 55.0,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-linkusd",
    "name": "LINKUSD",
    "category": "defi",
    "modules": [
      "yield-optimizer",
      "dex-arbitrage"
    ],
    "allocationUsdc": 2424.74,
    "allocationPct": 9.7,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 7.7085,
    "pipelineScore": 54.4,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-morpho--morpho",
    "name": "MORPHO \u2014 Morpho",
    "category": "rwa",
    "modules": [
      "hyperliquid-mean-rev",
      "drift-funding-arb"
    ],
    "allocationUsdc": 1462.31,
    "allocationPct": 5.8,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 1.4632,
    "pipelineScore": 54.0,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-kaitousdt",
    "name": "KAITOUSDT",
    "category": "ai",
    "modules": [
      "trend-trader",
      "hyperliquid-momentum"
    ],
    "allocationUsdc": 1487.07,
    "allocationPct": 5.9,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.3439,
    "pipelineScore": 54.0,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-seiusd",
    "name": "SEIUSD",
    "category": "l1",
    "modules": [
      "trend-trader",
      "hyperliquid-momentum"
    ],
    "allocationUsdc": 1638.79,
    "allocationPct": 6.6,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.0496,
    "pipelineScore": 53.4,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-snxusd",
    "name": "SNXUSD",
    "category": "defi",
    "modules": [
      "yield-optimizer",
      "dex-arbitrage"
    ],
    "allocationUsdc": 1493.05,
    "allocationPct": 6.0,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.2453,
    "pipelineScore": 53.4,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-opusd",
    "name": "OPUSD",
    "category": "l2",
    "modules": [
      "trend-trader",
      "hyperliquid-arb"
    ],
    "allocationUsdc": 1203.07,
    "allocationPct": 4.8,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.1095,
    "pipelineScore": 53.3,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-solusd",
    "name": "SOLUSD",
    "category": "l1",
    "modules": [
      "trend-trader",
      "hyperliquid-momentum"
    ],
    "allocationUsdc": 2399.54,
    "allocationPct": 9.6,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 68.355,
    "pipelineScore": 53.3,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-dotusd",
    "name": "DOTUSD",
    "category": "l1",
    "modules": [
      "trend-trader",
      "hyperliquid-momentum"
    ],
    "allocationUsdc": 1648.79,
    "allocationPct": 6.6,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.9982,
    "pipelineScore": 53.1,
    "tradingMode": "paper"
  },
  {
    "label": "pipeline-pythusd",
    "name": "PYTHUSD",
    "category": "data",
    "modules": [
      "trend-trader"
    ],
    "allocationUsdc": 1439.17,
    "allocationPct": 5.8,
    "riskProfile": "medium",
    "profitMode": "reinvest",
    "stopLoss": 0.0379,
    "pipelineScore": 52.4,
    "tradingMode": "paper"
  }
];

function loadWalletStore() {
  try { return JSON.parse(fs.readFileSync(WALLET_FILE, 'utf-8')); }
  catch { return { wallets: [] }; }
}

function saveWallets(wallets) {
  fs.writeFileSync(WALLET_FILE, JSON.stringify({
    stored_at: new Date().toISOString(),
    wallets
  }, null, 2));
}

async function authenticate(ethWallet) {
  const chal = await fetch(API_BASE + '/api/auth/challenge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ walletAddress: ethWallet.address })
  });
  const { message } = await chal.json();
  const signature = await ethWallet.signMessage(message);
  const res = await fetch(API_BASE + '/api/auth/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ walletAddress: ethWallet.address, signature, message })
  });
  return (await res.json()).token;
}

async function createPipelineAgent(token, ethWallet, spec, seq) {
  const name = `pp-v4-${spec.label}-${seq+1}`;
  const body = {
    name,
    walletAddress: ethWallet.address,
    riskProfile: spec.riskProfile || 'medium',
    modules: spec.modules || ['trend-trader'],
    allocationUsdc: spec.allocationUsdc || 55,
    profitMode: spec.profitMode || 'reinvest',
    allocationAmount: spec.allocationUsdc || 55,
    allocationCurrency: 'usdc',
    tradingMode: spec.tradingMode || 'paper',
    config: { profit_mode: spec.profitMode || 'reinvest' }
  };
  const res = await fetch(API_BASE + '/api/agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body)
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data, name };
}

async function main() {
  console.log('🚀 Deploying Pipeline v4 Portfolio to QWNT');
  console.log(`   Regime: NEUTRAL | ${PIPELINE_AGENTS.length} agents`);
  console.log('');

  const store = loadWalletStore();
  const wallets = store.wallets || [];

  // Use wallet 91 (pipeline-dedicated)
  let wallet = wallets.find(w => w.idx === WALLET_IDX);
  if (!wallet) {
    console.log('⚠ Wallet 91 not found. Create it first.');
    process.exit(1);
  }

  const ethWallet = new ethers.Wallet(wallet.privateKey);
  console.log(`   Wallet #${wallet.idx}: ${ethWallet.address}`);

  const token = await authenticate(ethWallet);
  console.log('   ✅ Authenticated');
  console.log('');

  let success = 0, failed = 0;
  for (let i = 0; i < PIPELINE_AGENTS.length; i++) {
    const agent = PIPELINE_AGENTS[i];
    const result = await createPipelineAgent(token, ethWallet, agent, i);
    if (result.ok) {
      console.log(`   ✅ [${i+1}/${PIPELINE_AGENTS.length}] ${result.name} — $${agent.allocationUsdc}`);
      success++;
    } else {
      console.log(`   ❌ [${i+1}/${PIPELINE_AGENTS.length}] ${agent.label} — HTTP ${result.status}`);
      failed++;
    }
    await sleep(AGENT_SPACING_MS);
  }

  console.log('');
  console.log(`   ✅ ${success} deployed | ❌ ${failed} failed`);
  console.log(`   📊 Check: https://qwnt.app/dashboard`);

  // Update tracker
  const ts = new Date().toISOString().split('T')[0];
  fs.appendFileSync(TRACKER, `\n### Pipeline v4 Deploy — ${ts}\n- Wallet: #${wallet.idx}\n- Agents: ${success} deployed\n- Regime: NEUTRAL\n- Capital: \$25,000\n`);
}

main().catch(console.error);

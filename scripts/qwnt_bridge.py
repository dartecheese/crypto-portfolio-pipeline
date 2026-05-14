#!/usr/bin/env python3
"""
QWNT Bridge — Converts crypto portfolio pipeline output into QWNT agent deployment configs.
Reads latest-v4-portfolio.json, maps assets to QWNT strategy modules, generates deployable configs.
"""
import json, os, sys

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QWNT_DIR = os.path.expanduser("~/qwnt-ai")
PORTFOLIO_FILE = os.path.join(PIPELINE_DIR, "portfolio", "latest-v4-portfolio.json")
OUTPUT_FILE = os.path.join(PIPELINE_DIR, "qwnt", "deploy-config.json")

# ── Asset → QWNT Module Mapping ──
# Each asset category maps to optimal QWNT strategy modules
CATEGORY_TO_MODULES = {
    "l1":       ["trend-trader", "hyperliquid-momentum"],
    "l2":       ["trend-trader", "hyperliquid-arb"],
    "defi":     ["yield-optimizer", "dex-arbitrage"],
    "ai":       ["trend-trader", "hyperliquid-momentum"],
    "meme":     ["meme-sniper"],
    "rwa":      ["hyperliquid-mean-rev", "drift-funding-arb"],
    "commodities": ["hyperliquid-mean-rev"],
    "equities_mag7": ["trend-trader"],
    "equities_crypto_adjacent": ["trend-trader", "hyperliquid-momentum"],
    "equities_ai_semis": ["trend-trader"],
    "equities_finance": ["trend-trader"],
    "indexes":  ["hyperliquid-mean-rev"],
    "treasuries": ["yield-optimizer"],
    "data":     ["trend-trader"],
    "gaming":   ["trend-trader", "meme-sniper"],
}

# ── Regime → QWNT Risk Profile ──
REGIME_TO_RISK = {
    "bear": "safe",
    "neutral": "medium",
    "bull": "high",
}

# All known QWNT modules
ALL_MODULES = [
    "meme-sniper", "trend-trader", "yield-optimizer", "dex-arbitrage",
    "polymarket-arb-real", "drift-funding-arb", "hyperliquid-arb",
    "hyperliquid-momentum", "hyperliquid-mean-rev", "leveraged-trader",
]


def build_qwnt_config(portfolio_file: str = PORTFOLIO_FILE) -> dict:
    """Convert portfolio pipeline output into QWNT deploy config."""
    with open(portfolio_file) as f:
        portfolio = json.load(f)

    allocations = portfolio.get("allocations", [])
    if not allocations:
        print("⚠ No allocations found")
        return {}

    # Determine regime from portfolio metadata
    strategy = portfolio.get("strategy", "")
    regime = "bear" if "bear" in strategy.lower() else "neutral"
    risk_profile = REGIME_TO_RISK.get(regime, "medium")

    # Build agent configs
    agents = []
    total_capital = portfolio.get("total_capital", 25000)

    for alloc in allocations:
        asset_name = alloc.get("name", alloc.get("ticker", "unknown"))
        category = alloc.get("category", "l1")
        allocation_pct = alloc.get("allocation_pct", 0)
        allocation_usd = alloc.get("allocation_usd", 0)
        stop_loss = alloc.get("stop_loss", 0)
        composite_score = alloc.get("composite_score", 0)

        # Map modules
        modules = CATEGORY_TO_MODULES.get(category, ["trend-trader"])

        # Adjust risk profile based on individual asset signals
        asset_risk = risk_profile
        if allocation_pct > 15:
            asset_risk = "high" if risk_profile != "safe" else "medium"

        agents.append({
            "label": f"pipeline-{asset_name.lower().replace(' ','-').replace('—','')[:20]}",
            "name": asset_name,
            "category": category,
            "modules": modules,
            "allocationUsdc": round(allocation_usd, 2),
            "allocationPct": allocation_pct,
            "riskProfile": asset_risk,
            "profitMode": "reinvest",
            "stopLoss": round(stop_loss, 4) if stop_loss else None,
            "pipelineScore": composite_score,
            "tradingMode": "paper",
        })

    config = {
        "generated": portfolio.get("timestamp", ""),
        "source": "crypto-portfolio-pipeline v4",
        "regime": regime,
        "totalCapital": total_capital,
        "riskProfile": risk_profile,
        "stopLossPct": portfolio.get("stop_loss_pct", 0.25),
        "agents": agents,
    }

    # Save
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"✅ QWNT deploy config → {OUTPUT_FILE}")
    print(f"   {len(agents)} agents | Regime: {regime.upper()} | Risk: {risk_profile}")
    print(f"   Total capital: ${total_capital:,.0f}")

    for a in agents:
        print(f"   {a['name']:<22} ${a['allocationUsdc']:>8,.2f} ({a['allocationPct']:>5.1f}%)  [{'+'.join(a['modules'])}]  stop={a['stopLoss']}")

    return config


def generate_deployer_script(config: dict, output_file: str = None) -> str:
    """Generate a Node.js deployer script for QWNT based on the config."""
    if not output_file:
        output_file = os.path.join(os.path.dirname(OUTPUT_FILE), "deploy-pipeline.mjs")

    agents = config.get("agents", [])
    regime = config.get("regime", "neutral")

    script = f'''// Auto-generated QWNT Deployer — Pipeline v4
// Regime: {regime.upper()} | Generated: {config.get("generated", "")}
// {len(agents)} agents | ${config.get("totalCapital", 0):,.0f} total capital

import fs from 'fs';
import path from 'path';
import {{ fileURLToPath }} from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API_BASE = 'https://qwnt.app';
const WALLET_FILE = path.join(__dirname, '..', '.paper-wallets.json');
const TRACKER = path.join(__dirname, '..', 'experiment-tracker.md');
const AGENT_SPACING_MS = 3500;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const WALLET_IDX = 91;  // Pipeline-dedicated wallet range: 91-95
const AGENTS_PER_WALLET = 15;

const PIPELINE_AGENTS = {json.dumps(agents, indent=2)};

function loadWalletStore() {{
  try {{ return JSON.parse(fs.readFileSync(WALLET_FILE, 'utf-8')); }}
  catch {{ return {{ wallets: [] }}; }}
}}

function saveWallets(wallets) {{
  fs.writeFileSync(WALLET_FILE, JSON.stringify({{
    stored_at: new Date().toISOString(),
    wallets
  }}, null, 2));
}}

async function authenticate(ethWallet) {{
  const chal = await fetch(API_BASE + '/api/auth/challenge', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ walletAddress: ethWallet.address }})
  }});
  const {{ message }} = await chal.json();
  const signature = await ethWallet.signMessage(message);
  const res = await fetch(API_BASE + '/api/auth/connect', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ walletAddress: ethWallet.address, signature, message }})
  }});
  return (await res.json()).token;
}}

async function createPipelineAgent(token, ethWallet, spec, seq) {{
  const name = `pp-v4-${{spec.label}}-${{seq+1}}`;
  const body = {{
    name,
    walletAddress: ethWallet.address,
    riskProfile: spec.riskProfile || '{config.get("riskProfile", "medium")}',
    modules: spec.modules || ['trend-trader'],
    allocationUsdc: spec.allocationUsdc || 55,
    profitMode: spec.profitMode || 'reinvest',
    allocationAmount: spec.allocationUsdc || 55,
    allocationCurrency: 'usdc',
    tradingMode: spec.tradingMode || 'paper',
    config: {{ profit_mode: spec.profitMode || 'reinvest' }}
  }};
  const res = await fetch(API_BASE + '/api/agents', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json', Authorization: `Bearer ${{token}}` }},
    body: JSON.stringify(body)
  }});
  const data = await res.json().catch(() => ({{}}));
  return {{ ok: res.ok, status: res.status, data, name }};
}}

async function main() {{
  console.log('🚀 Deploying Pipeline v4 Portfolio to QWNT');
  console.log(`   Regime: {regime.upper()} | ${{PIPELINE_AGENTS.length}} agents`);
  console.log('');

  const store = loadWalletStore();
  const wallets = store.wallets || [];

  // Use wallet 91 (pipeline-dedicated)
  let wallet = wallets.find(w => w.idx === WALLET_IDX);
  if (!wallet) {{
    console.log('⚠ Wallet 91 not found. Create it first.');
    process.exit(1);
  }}

  const ethWallet = new ethers.Wallet(wallet.privateKey);
  console.log(`   Wallet #${{wallet.idx}}: ${{ethWallet.address}}`);

  const token = await authenticate(ethWallet);
  console.log('   ✅ Authenticated');
  console.log('');

  let success = 0, failed = 0;
  for (let i = 0; i < PIPELINE_AGENTS.length; i++) {{
    const agent = PIPELINE_AGENTS[i];
    const result = await createPipelineAgent(token, ethWallet, agent, i);
    if (result.ok) {{
      console.log(`   ✅ [${{i+1}}/${{PIPELINE_AGENTS.length}}] ${{result.name}} — $${{agent.allocationUsdc}}`);
      success++;
    }} else {{
      console.log(`   ❌ [${{i+1}}/${{PIPELINE_AGENTS.length}}] ${{agent.label}} — HTTP ${{result.status}}`);
      failed++;
    }}
    await sleep(AGENT_SPACING_MS);
  }}

  console.log('');
  console.log(`   ✅ ${{success}} deployed | ❌ ${{failed}} failed`);
  console.log(`   📊 Check: https://qwnt.app/dashboard`);

  // Update tracker
  const ts = new Date().toISOString().split('T')[0];
  fs.appendFileSync(TRACKER, `\\n### Pipeline v4 Deploy — ${{ts}}\\n- Wallet: #${{wallet.idx}}\\n- Agents: ${{success}} deployed\\n- Regime: {regime.upper()}\\n- Capital: \${config.get("totalCapital", 0):,.0f}\\n`);
}}

main().catch(console.error);
'''

    with open(output_file, "w") as f:
        f.write(script)

    print(f"\n✅ Deployer script → {output_file}")
    return output_file


if __name__ == "__main__":
    config = build_qwnt_config()
    if config:
        generate_deployer_script(config)

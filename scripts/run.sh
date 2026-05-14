#!/bin/bash
# Crypto Portfolio Pipeline — Daily Runner
# This script is called by a cron-triggered agent session.
# It aggregates TradingView data and runs the scoring engine.
set -euo pipefail

PIPELINE_DIR="/Users/colto/.openclaw/workspace2/crypto-portfolio-pipeline"
TS=$(date -u +"%Y-%m-%d")
SCREEN_FILE="$PIPELINE_DIR/screens/screen-$TS.json"

echo "🧠 Crypto Portfolio Pipeline — $TS"
echo "=================================="

# Run the scoring engine with multiple strategies
cd "$PIPELINE_DIR"

for strat in balanced momentum value; do
    python3 scripts/score.py "$SCREEN_FILE" -s "$strat" -n 15 -c 10000
done

# Print latest portfolio summary
echo ""
echo "📊 Latest Balanced Portfolio:"
python3 -c "
import json
with open('$PIPELINE_DIR/portfolio/latest-portfolio.json') as f:
    p = json.load(f)
print(f\"  Strategy: {p['strategy']} | Assets: {p['num_assets']} | Capital: \${p['total_capital']:,.0f}\")
for a in p['allocations'][:5]:
    print(f\"  #{a['rank']} {a['name']:<20} \${a['price']:>10,.4f}  Score: {a['composite_score']:.1f}  Alloc: {a['allocation_pct']:.1f}%\")
"

echo "✅ Pipeline complete"

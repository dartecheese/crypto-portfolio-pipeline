#!/bin/bash
# Crypto Portfolio Pipeline — Daily Cron Runner
# Run this via cron or OpenClaw cron system to generate daily portfolio + dashboard.
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TS=$(date -u +"%Y-%m-%d")
SCREEN_FILE="$PIPELINE_DIR/screens/screen-$TS.json"
COMBINED_FILE="$PIPELINE_DIR/screens/combined-$TS.json"

echo "🧠 Crypto Portfolio Pipeline — Daily Run"
echo "==========================================="
echo "Date: $TS"
echo ""

# 1. Fetch RWA prices from CoinGecko
echo "📡 Step 1: Fetching RWA prices..."
cd "$PIPELINE_DIR"
python3 scripts/rwa_feed.py screens/ || echo "⚠ RWA feed had errors (continuing)"

# 2. Run scoring pipeline with all strategies
echo ""
echo "📊 Step 2: Scoring & portfolio construction..."
for strat in balanced momentum value; do
    if [ -f "$COMBINED_FILE" ]; then
        DATA="$COMBINED_FILE"
    elif [ -f "$SCREEN_FILE" ]; then
        DATA="$SCREEN_FILE"
    else
        echo "⚠ No screen data found. Run TradingView screens first."
        exit 1
    fi
    python3 scripts/score.py "$DATA" -s "$strat" -n 15 -c 25000 --no-enrich
done

# 3. Generate dashboard
echo ""
echo "📈 Step 3: Performance dashboard..."
python3 scripts/dashboard.py

# 4. Commit and push
echo ""
echo "📤 Step 4: Committing results..."
cd "$PIPELINE_DIR"
git add -A
git commit -m "Daily run: $TS" || echo "   (nothing to commit)"
git push origin main 2>/dev/null || echo "   (push skipped)"

echo ""
echo "✅ Pipeline complete — $TS"

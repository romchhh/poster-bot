#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck disable=SC1091
source ./myenv/bin/activate
nohup python main.py >> bot.log 2>&1 &
echo "Bot started (pid $!, log: bot.log)"

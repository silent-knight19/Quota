#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run tracker engine
python3 "$DIR/tracker.py"

# Open dashboard in browser unless --cli flag is passed
if [ "$1" != "--cli" ]; then
  echo "🌐 Launching dashboard in default browser..."
  open "$DIR/dashboard.html"
fi

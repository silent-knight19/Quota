#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Enforce PAT passed securely via environment variable (prevents shell history and process list leakage)
if [ -z "${VSCE_PAT:-}" ]; then
  echo "❌ Error: Missing Personal Access Token (PAT)." >&2
  echo "Please set the VSCE_PAT environment variable before running this script:" >&2
  echo "  export VSCE_PAT=\"<your_azure_devops_personal_access_token>\"" >&2
  echo "  ./publish_extension.sh" >&2
  echo "" >&2
  echo "To create a token:" >&2
  echo "  1. Sign in to https://dev.azure.com" >&2
  echo "  2. Go to User Settings (top right) -> Personal Access Tokens" >&2
  echo "  3. Create token with Organization='All accessible organizations' and Scope='Marketplace (Manage)'" >&2
  exit 1
fi

echo "🚀 Publishing Quota to the Visual Studio Marketplace..."
npx -y @vscode/vsce publish -p "$VSCE_PAT" --no-git-tag-version

echo ""
echo "🎉 SUCCESS! Quota has been published to the Visual Studio Marketplace!"
echo "View your live listing at: https://marketplace.visualstudio.com/items?itemName=$(node -p "require('./package.json').publisher + '.' + require('./package.json').name")"

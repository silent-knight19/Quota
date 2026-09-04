#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

TOKEN="$1"
if [ -z "$TOKEN" ]; then
  echo "❌ Error: Missing Personal Access Token (PAT)."
  echo "Usage: ./publish_extension.sh <AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN>"
  echo ""
  echo "To create a token:"
  echo "  1. Sign in to https://dev.azure.com"
  echo "  2. Go to User Settings (top right) -> Personal Access Tokens"
  echo "  3. Create token with Organization='All accessible organizations' and Scope='Marketplace (Manage)'"
  echo "  4. Run: ./publish_extension.sh <your_token>"
  exit 1
fi

echo "🚀 Publishing Quota to the Visual Studio Marketplace..."
npx -y @vscode/vsce publish -p "$TOKEN" --no-git-tag-version

echo ""
echo "🎉 SUCCESS! Quota has been published to the Visual Studio Marketplace!"
echo "View your live listing at: https://marketplace.visualstudio.com/items?itemName=$(node -p "require('./package.json').publisher + '.' + require('./package.json').name")"

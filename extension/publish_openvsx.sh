#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Enforce Open VSX PAT passed securely via environment variable
if [ -z "${OVSX_PAT:-}" ]; then
  echo "❌ Error: Missing Open VSX Access Token (OVSX_PAT)." >&2
  echo "Please set the OVSX_PAT environment variable before running this script:" >&2
  echo "  export OVSX_PAT=\"<your_open_vsx_access_token>\"" >&2
  echo "  ./publish_openvsx.sh" >&2
  echo "" >&2
  echo "To generate a token:" >&2
  echo "  1. Sign in to https://open-vsx.org" >&2
  echo "  2. Go to 'Access Tokens' in the left menu" >&2
  echo "  3. Click 'Generate New Token' and copy it" >&2
  exit 1
fi

VSIX_FILE=$(ls quota-tracker-*.vsix | sort -V | tail -n 1)

if [ -z "$VSIX_FILE" ]; then
  echo "📦 No .vsix found, packaging first..."
  ./package_extension.sh
  VSIX_FILE=$(ls quota-tracker-*.vsix | sort -V | tail -n 1)
fi

echo "🚀 Publishing $VSIX_FILE to the Open VSX Registry..."
npx -y ovsx publish "$VSIX_FILE" -p "$OVSX_PAT"

echo ""
echo "🎉 SUCCESS! Quota has been published to Open VSX!"
echo "View your listing at: https://open-vsx.org/extension/$(node -p "require('./package.json').publisher + '/' + require('./package.json').name")"

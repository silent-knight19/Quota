#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "📦 Packaging Quota Extension..."
rm -f *.vsix

# Synchronize backend assets
echo "  → Synchronizing engine assets..."
python3 tracker.py > /dev/null 2>&1 || true

# Package with vsce
npx -y @vscode/vsce package --no-git-tag-version

VSIX_FILE=$(ls *.vsix | head -n 1)
echo ""
echo "✅ Packaged successfully: $DIR/$VSIX_FILE"
echo "📊 Package size: $(ls -lh "$VSIX_FILE" | awk '{print $5}')"
echo ""
echo "Next steps to publish:"
echo "  • Web UI: Drag and drop '$VSIX_FILE' at https://marketplace.visualstudio.com/manage"
echo "  • CLI: Run './publish_extension.sh <YOUR_PERSONAL_ACCESS_TOKEN>'"

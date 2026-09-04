#!/bin/bash
# Quota Extension Local Installer & Linker
set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/extension" && pwd)"
EXT_NAME="SachinSingh.quota-tracker-1.2.0"
LEGACY_EXT="antigravity.antigravity-token-tracker-1.0.0"

echo "📦 Installing & Linking Quota VS Code Extension..."

# Target directories
TARGET_DIRS=(
  "$HOME/.antigravity-ide/extensions"
  "$HOME/.antigravity/extensions"
  "$HOME/.vscode/extensions"
)

for d in "${TARGET_DIRS[@]}"; do
  if [ -d "$d" ]; then
    echo "  → Cleaning obsolete links in $d"
    rm -rf "$d/$LEGACY_EXT"
    rm -rf "$d/$EXT_NAME"
    echo "  → Linking into $d/$EXT_NAME"
    ln -sfn "$SOURCE_DIR" "$d/$EXT_NAME"
  fi
done

echo "✅ Quota Extension installed and linked successfully!"
echo "🔄 Reload VS Code / Antigravity IDE window (Command+Shift+P -> 'Developer: Reload Window') to activate."

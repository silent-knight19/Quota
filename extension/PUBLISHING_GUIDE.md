# 🚀 Quota — Marketplace & Distribution Publishing Guide (VS Code & Google Antigravity)

This guide provides step-by-step instructions for publishing **Quota v1.2.1** to the **Visual Studio Code Marketplace** and deploying to **Google Antigravity IDE**.

---

## 📋 Release Summary (v1.2.1)

- **Package Artifact**: `quota-tracker-1.2.1.vsix` (~129 KB, 11 files)
- **Publisher ID**: `SachinSingh`
- **Extension Identifier**: `SachinSingh.quota-tracker`
- **Highlights in v1.2.1**:
  - ✨ **Pure Line Graph Timeline**: Redesigned Activity & Inference Timeline removing horizontal grid lines and bar blocks for a clean, unobstructed spline curve.
  - 🔒 **CSPRNG Nonce-based CSP**: Zero `unsafe-inline` scripts; nonces injected dynamically on every webview load.
  - 🛡️ **SQLite Concurrency & Authoritative Persistence**: Single-writer `InterProcessLock` with atomic `BEGIN IMMEDIATE` transactions and `ON CONFLICT(conv_id) DO UPDATE` UPSERTs.
  - 💰 **Financial Correctness**: Fixed context-window precedence (`o1-mini` at 128k prioritized before `o1`) and isolated `GPT-4` commercial rate tracking from `GPT-4o`.
  - 📦 **Sanitized CSV**: Native and fallback browser CSV exports hardened with formula neutralizing and quote escaping.

---

## 🛠️ Step 1: Package the VSIX Bundle

Before publishing, build the optimized and verified `.vsix` archive:

```bash
cd ~/Projects/antigravity-token-tracker/extension
./package_extension.sh
```

This compiles `quota-tracker-1.2.1.vsix` containing only runtime assets (`extension.js`, `tracker.py`, `dashboard.html`, `package.json`, `icon.png`), strictly excluding tests, databases, and telemetry.

---

## 🌐 Part A: Publishing to the Visual Studio Code Marketplace

### Option 1: Web Management Portal (Easiest — 30 Seconds)

1. Open the [Visual Studio Marketplace Management Portal](https://marketplace.visualstudio.com/manage).
2. Sign in with your Microsoft / GitHub account.
3. Locate **`SachinSingh`** (or your publisher handle).
4. Click on **`quota-tracker`** (or click **+ New extension** → **Visual Studio Code** if publishing under a new publisher).
5. Click **Update** (or upload button) and drag-and-drop:
   ```
   ~/Projects/antigravity-token-tracker/extension/quota-tracker-1.2.1.vsix
   ```
6. The marketplace will verify and publish the package automatically within 2–5 minutes.

---

### Option 2: Automated CLI Publish

1. Generate a Personal Access Token (PAT) in [Azure DevOps](https://dev.azure.com):
   - User Settings (⚙️ top right) → **Personal access tokens** → **+ New Token**.
   - Organization: Select **`All accessible organizations`** *(Required)*.
   - Scopes: Under **Marketplace**, check **`Manage`**.
2. Run the secure publishing script:

```bash
cd ~/Projects/antigravity-token-tracker/extension
export VSCE_PAT="<PASTE_YOUR_AZURE_DEVOPS_TOKEN_HERE>"
./publish_extension.sh
```

The script verifies that `VSCE_PAT` is set in the environment and executes:
```bash
npx -y @vscode/vsce publish -p "$VSCE_PAT" --no-git-tag-version
```
*(No tokens are passed as command-line arguments, preventing shell history or process list exposure).*

---

## 🪐 Part B: Deploying to Google Antigravity IDE

Google Antigravity IDE runs on the Code OSS / VS Code extension architecture. You can distribute Quota to Antigravity users through three pathways:

### Pathway 1: Via the Visual Studio Code Marketplace (Recommended)
Because Antigravity connects to the public extension ecosystem, publishing to the VS Code Marketplace (Part A above) automatically makes **Quota** searchable and installable directly inside Antigravity:
1. Open Antigravity IDE.
2. Press `Cmd + Shift + X` (Mac) or `Ctrl + Shift + X` (Windows/Linux) to open the Extensions panel.
3. Search for **`Quota`** and click **Install**.

---

### Pathway 2: Direct VSIX Sideloading (Offline & Instant)

For air-gapped workstations or immediate team distribution:

#### In the Antigravity UI:
1. Open Antigravity IDE.
2. Open the Extensions view (`Cmd+Shift+X` / `Ctrl+Shift+X`).
3. Click the `...` menu (Views and More Actions) at the top right of the Extensions panel.
4. Select **Install from VSIX...**
5. Choose `quota-tracker-1.2.1.vsix` located at:
   ```
   ~/Projects/antigravity-token-tracker/extension/quota-tracker-1.2.1.vsix
   ```

#### Via Antigravity CLI:
```bash
# If 'agy' or 'antigravity' is in your PATH:
agy --install-extension ~/Projects/antigravity-token-tracker/extension/quota-tracker-1.2.1.vsix

# Or using the standard code CLI:
code --install-extension ~/Projects/antigravity-token-tracker/extension/quota-tracker-1.2.1.vsix
```

---

### Pathway 3: Developer Live Link (Instant Local Development)

To link your live workspace code directly into Antigravity IDE without rebuilding `.vsix`:

```bash
cd ~/Projects/antigravity-token-tracker
./install_extension.sh
```

This script automatically creates clean symlinks in:
- `~/.antigravity-ide/extensions/SachinSingh.quota-tracker-1.2.1`
- `~/.antigravity/extensions/SachinSingh.quota-tracker-1.2.1`
- `~/.vscode/extensions/SachinSingh.quota-tracker-1.2.1`

Then press `Cmd + Shift + P` inside Antigravity IDE and run **`Developer: Reload Window`**.

---

### Pathway 4: Open VSX Registry (For Open-Source IDE Distributions)

If your team or community uses VSCodium, Gitpod, or custom Open VSX-configured Antigravity forks:

1. Create an account at [open-vsx.org](https://open-vsx.org) and generate an Access Token.
2. Publish with:
```bash
npx -y ovsx publish ~/Projects/antigravity-token-tracker/extension/quota-tracker-1.2.1.vsix -p "<YOUR_OVSX_TOKEN>"
```

---

## 🔍 Step 3: Verify Live Deployment

Once published, verify the installation:

| Platform | Verification Action | Expected State |
|---|---|---|
| **Marketplace** | Visit `https://marketplace.visualstudio.com/items?itemName=SachinSingh.quota-tracker` | Shows v1.2.1 with updated feature notes |
| **VS Code** | Search `Quota` in Extensions panel | Version `1.2.1` available for install/update |
| **Google Antigravity** | Run `Quota: Open Quota Dashboard` (`Cmd+Shift+P`) | Clean line-graph Activity Timeline loads with status bar pill |

---

## 🔄 Publishing Future Updates

1. Update `"version"` in `extension/package.json` (e.g. `1.2.2`).
2. Add release highlights to `CHANGELOG.md`.
3. Run `./extension/package_extension.sh`.
4. Run `export VSCE_PAT="<PAT>" && ./extension/publish_extension.sh`.

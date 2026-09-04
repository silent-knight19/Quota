# 🚀 Quota — VS Code Marketplace Publishing Guide

This handbook walks you through publishing **Quota** to the Visual Studio Code Marketplace and Open VSX Registry in under 3 minutes.

---

## 📋 Prerequisites
- A free **Microsoft** or **GitHub** account.
- The pre-built `.vsix` bundle: `quota-1.2.0.vsix` (already compiled and optimized at `~/Projects/antigravity-token-tracker/extension/quota-1.2.0.vsix`).

---

## 🛠️ Step 1: Create or Confirm Your Marketplace Publisher

1. Open the [Visual Studio Marketplace Management Portal](https://marketplace.visualstudio.com/manage).
2. Sign in with your GitHub or Microsoft account.
3. If you haven't created a publisher yet:
   - Click **Create publisher**.
   - **Publisher ID**: Enter your handle (e.g. `silent-knight19` or your preferred unique identifier).
   - **Display Name**: Enter your name or company name (e.g. `Sachin Kumar Singh` or `Quota Team`).
4. > [!NOTE]
   > If your Publisher ID on the portal is different from `silent-knight19`, open `package.json` in the `extension/` directory and update the `"publisher"` field to match your ID, then run `./package_extension.sh`.

---

## 🔑 Step 2: Generate an Azure DevOps Personal Access Token (PAT)

1. Navigate to [Azure DevOps](https://dev.azure.com).
2. Click your user avatar / settings icon in the top-right corner ⚙️ and select **Personal access tokens**.
3. Click **+ New Token**.
4. Configure the token fields:
   - **Name**: `VSCode Marketplace Quota`
   - **Organization**: Select **`All accessible organizations`** *(Critical: do NOT select a single org, or publish will fail)*.
   - **Expiration**: `90 days` (or your preference).
   - **Scopes**: Click **Show all scopes** at the bottom.
   - Scroll down to **Marketplace** and check **`Manage`**.
5. Click **Create** and **copy your token immediately** (it will not be shown again).

---

## 📦 Step 3: Publish to the Store (Choose Option A or B)

### Option A: Drag-and-Drop Web Upload (Easiest — 30 Seconds)

1. Open [marketplace.visualstudio.com/manage](https://marketplace.visualstudio.com/manage).
2. Click on your Publisher name.
3. Click **+ New extension** → **Visual Studio Code**.
4. Drag and drop the compiled **`quota-1.2.0.vsix`** file from:
   ```
   ~/Projects/antigravity-token-tracker/extension/quota-1.2.0.vsix
   ```
5. Marketplace verification will process the package within 2–3 minutes. Your extension is live!

---

### Option B: One-Command CLI Publish

Run the automated publishing script from your terminal:

```bash
cd ~/Projects/antigravity-token-tracker/extension
./publish_extension.sh <PASTE_YOUR_AZURE_DEVOPS_TOKEN_HERE>
```

The script will validate the package, authenticate with Microsoft, and deploy directly to the marketplace.

---

## 🌐 Step 4: Verify Your Live Listing

Once published, your extension will be accessible worldwide:
- **Web Marketplace URL**:
  `https://marketplace.visualstudio.com/items?itemName=<YOUR_PUBLISHER_ID>.quota`
- **Inside VS Code**:
  Open the Extensions panel (`Cmd + Shift + X` on Mac, `Ctrl + Shift + X` on Windows/Linux) and search for **`Quota`**.

---

## 🔄 Publishing Future Updates

Whenever you make improvements or bump the version:
1. Update `"version"` in `extension/package.json` (e.g. `1.2.1`).
2. Run `./package_extension.sh` to compile the new `.vsix`.
3. Run `./publish_extension.sh <TOKEN>` (or drag-and-drop the new `.vsix` on the management portal).

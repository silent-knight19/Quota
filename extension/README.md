# ⚡ Quota — Real-Time AI Token & Commercial Cost Intelligence

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/silent-knight19/quota/blob/HEAD/LICENSE)
[![VS Code](https://img.shields.io/badge/IDE-VS%20Code%20%7C%20Google%20Antigravity-orange.svg)](https://marketplace.visualstudio.com)
[![Privacy First](https://img.shields.io/badge/Privacy-100%25%20Local-green.svg)](#-privacy--security-architecture)

**Quota** is an enterprise-grade AI observability and cost governance platform designed specifically for **Google Antigravity IDE** and **VS Code**. It provides real-time telemetry, continuous spend analytics, and token auditing across all inbuilt and external models (Gemini Flash/Pro, Claude Sonnet/Opus) with zero external API keys required.

---

## ✨ Key Capabilities

### 1. Real-Time Status Bar Intelligence
- Live, dynamic status bar item in your editor footer: `✨ 18.0M Tokens | $1.94`.
- **Instant Scope Switcher**: Click to toggle between:
  - **Active Session**: Real-time token consumption of your current AI pairing chat.
  - **Current Workspace**: Cumulative consumption and costs for the open repository.
  - **Lifetime Total**: Global historical volume across all projects.
- Interactive **Quick Actions Menu** with 1-click ledger CSV export and markdown report generator.

### 2. Full Visual Cockpit
- **Hero KPI Strip**:
  - **Total Processed Volume** with Prompt Cache Hit ratio (e.g. `6.47B Tokens (99.9% Cache Hit)`).
  - **Standard Commercial Valuation**: True retail equivalent cost if each turn were billed statelessly.
  - **Prompt-Cached Real Cost**: Actual cost with Gemini/Anthropic prompt caching discounts applied.
  - **Autonomous Invocations**: Total AI turns, sessions, and workspaces tracked.
- **Continuous 30-Day Activity & Inference Timeline**:
  - Smooth Catmull-Rom cubic spline area curve with glowing neon gradient fill.
  - Slim column bars with interactive hover crosshairs and tooltips.
  - Filter by range (`14D`, `30D`, `All History`) and metric (`Commercial Cost ($)`, `Token Volume`, `Invocations`).
- **Token Distribution Layer**: Segmented visual breakdown of Prompt Cache, Fresh Ingestion, Model Output, Chain-of-Thought Thinking, and Tool Calls.
- **Provider & Model Matrix**: Telemetry across Gemini 3.5/3.6/3.7/3.8 Flash, Gemini 3.1 Pro, Claude Sonnet 4.6, and Claude Opus 4.6.
- **Autonomous Tool Consumption**: Telemetry for terminal commands (`run_command`), file modifications (`write_to_file`, `replace_file_content`), and file reads (`view_file`).

### 3. Slide-Over Trace Inspector & Context Compounding
- Click any chat row in the **Conversation Ledger** to slide open a dedicated trace inspector.
- View turn-by-turn hockey-stick context growth curves.
- Automatic anomaly tagging: `Deep Session (90+ turns)`, `Heavy File Reads`, `Intensive Terminal Use`.

### 4. Disaster Recovery & Update Survivability
- Backed by a dedicated **SQLite Persistent Ledger** stored outside the ephemeral extension directory in `~/.config/quota/persistent_ledger.sqlite`.
- **Zero Data Loss on Updates**: Extension updates and complete IDE reinstalls preserve 100% of your historical token history.
- Automatic redundant JSON snapshot mirroring.

---

## 🔒 Privacy & Security Architecture

Quota was engineered from the ground up to comply with strict enterprise security standards:

- **100% Local & Offline**: Zero external network calls. All charts, icons, and fonts are embedded locally with zero remote CDN dependencies.
- **Zero Content Retention**: Quota **never** reads, copies, or stores raw source code, proprietary algorithms, or user prompts. Only anonymous numerical counters (token quantities and costs) are retained.
- **Zero Shell Injection**: All process executions use strict `child_process.execFile` with isolated argument arrays. Subshell invocation (`/bin/sh` or `cmd.exe`) is completely eliminated.
- **Strict Content Security Policy (CSP)**: The visual cockpit operates under an explicit `Content-Security-Policy` prohibiting any external script or stylesheet injection.
- **Safe Database Concurrency**: SQLite runs with Write-Ahead Logging (`WAL` mode) and busy timeouts to prevent database locks across multiple concurrent windows.

---

## ⚙️ Extension Settings

Quota works automatically out-of-the-box with zero configuration. For advanced setups, customize via VS Code Settings (`Cmd + ,` or `Ctrl + ,`):

| Setting | Default | Description |
|---|---|---|
| `quota.pythonPath` | `""` | Custom path to Python 3 binary (e.g. `/usr/bin/python3`, `py`, or virtualenv). |
| `quota.statusBarMode` | `"session"` | Default status bar scope (`session`, `workspace`, or `total`). |
| `quota.dataDirectory` | `""` | Custom directory for the persistent SQLite ledger and backups (defaults to `~/.config/quota`). |

---

## 🚀 Quick Actions

Press `Cmd + Shift + P` (or `Ctrl + Shift + P`) and search for:
- `Quota: Open Quota Dashboard`: Opens the visual analytics cockpit.
- `Quota: Open Quota Quick Actions`: Opens the QuickPick command center.
- `Quota: Refresh Quota Data`: Immediately triggers an updated log scan.
- `Quota: Show Quota Summary`: Displays a quick notification card of your token consumption.

---

## 📄 License

MIT © [Sachin Kumar Singh](https://github.com/silent-knight19/quota/blob/HEAD/LICENSE)

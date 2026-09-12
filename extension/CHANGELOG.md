# Change Log

All notable changes to the "Quota" extension will be documented in this file.

## [1.2.1] - Production Hardening & UI Polish Release

### Changed & Improved
- **Clean Line Graph Timeline Redesign**:
  - Redesigned the **Activity & Inference Timeline** into an unobstructed, pure line graph.
  - Removed cluttering horizontal grid lines and bar blocks across all metric views.
  - Preserved the glowing monotone cubic spline curve, area gradient fill, interactive hover crosshairs, and live metric tooltips.
- **Enterprise Concurrency & SQLite Single-Writer Persistence**:
  - Implemented OS-safe file locking (`InterProcessLock`) on `~/.config/quota/.scan.lock`.
  - Enforced atomic `BEGIN IMMEDIATE` write transactions and `INSERT ... ON CONFLICT(conv_id) DO UPDATE` UPSERT semantics, completely preventing lost-update anomalies during concurrent multi-process scans.
  - Inactive session attribution now strictly verifies physical directory absence on disk before marking records inactive.
- **Strict Content Security Policy & Webview Hardening**:
  - Enforced strict CSP `script-src 'nonce-<TOKEN>'` with cryptographically random CSPRNG nonces generated on every webview load (`secrets.token_urlsafe(16)` in Python and `crypto.randomBytes(16)` in Node.js).
  - Completely eliminated `script-src 'unsafe-inline'` and removed all inline HTML event handler attributes (`onclick`, `onchange`, `oninput`, `onmouseenter`, `onmouseleave`) in favor of declarative DOM `addEventListener` bindings.
- **Financial & Model Intelligence Accuracy**:
  - Resolved model context-window precedence bug where `o1` shadowed `o1-mini`. Specific model prefixes (`o1-mini` at 128k, `o3-mini` at 200k) now evaluate before generic short tokens.
  - Disambiguated generic `gpt-4` from `gpt-4o`. `GPT-4` is now assigned dedicated canonical commercial rates ($30.00 / $60.00 per 1M tokens), preventing severe cost under-reporting.
- **Hardened CSV Export & Formula Injection Defense**:
  - Implemented RFC 4180-compliant formula neutralizing and quote-doubling escaping (`csvCell()`) across both native VS Code and browser fallback export pathways.
- **Publishing & Secret Security**:
  - Updated `publish_extension.sh` to enforce authentication strictly via `VSCE_PAT` environment variable; positional CLI arguments are rejected to prevent token leakage in process tables, shell history, and logs.
- **Architecture & Source Parity**:
  - Refactored background scanning in the extension host to single-flight Promise coalescing (`activeScanPromise`, `scanRequestedAgain`), ensuring at most one child process runs at any time.
  - Replaced 1,800-line embedded HTML string in `tracker.py` with canonical file-based template loading.
  - Enforced byte-for-byte parity between root and extension runtime files with automated SHA-256 integrity tests.

## [1.2.0] - Initial Public Release

### Added
- **Real-Time Status Bar**: Dynamic footer display showing token consumption and prompt-cached commercial spend with instant scope switching (Active Session ↔ Current Workspace ↔ Lifetime Total).
- **Interactive Visual Cockpit**:
  - Continuous 30-day activity & inference timeline with Catmull-Rom cubic spline curves and neon gradient fills.
  - Multi-layer segmented ingestion bar visualizing Prompt Cache, Fresh Prompt Ingestion, Model Output, Chain-of-Thought Reasoning, and Tool Call Arguments.
  - Provider share breakdown (Google Gemini vs Anthropic Claude).
  - Autonomous tool consumption matrix (`view_file`, `write_to_file`, `run_command`, `grep_search`).
  - Slide-over trace inspector with turn-by-turn hockey-stick context compounding curves.
- **Disaster Recovery & Privacy**:
  - SQLite persistent ledger in `~/.config/quota/persistent_ledger.sqlite` surviving complete IDE uninstalls and extension updates.
  - 100% local, offline telemetry with zero external network dependencies and zero raw code retention.
- **1-Click Accounting Exports**:
  - Formatted CSV export for client billing and expense allocation.
  - Markdown summary report copied directly to clipboard for PRs, Jira, and Slack.
- **Enterprise Security Hardening**:
  - Zero-shell process execution using isolated argument arrays (`execFile`).
  - Strict Content Security Policy (`CSP`) on visual dashboard webviews.
  - Full XSS input sanitization across all repository names, model IDs, and session keys.

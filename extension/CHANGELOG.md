# Change Log

All notable changes to the "Quota" extension will be documented in this file.

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

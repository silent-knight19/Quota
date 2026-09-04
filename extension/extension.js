const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFile } = require('child_process');

let statusBarItem;
let currentWebview = null;
let refreshTimer = null;
let pollInterval = null;
let isScanning = false;
let lastKnownMtime = 0;
let lastKnownSize = 0;
let lastUpdatedTimestamp = new Date();
let extensionContext = null;

// Resolve Paths dynamically (100% portable across macOS, Windows, Linux)
function getPaths(context) {
  const extDir = context ? context.extensionPath : __dirname;
  const config = vscode.workspace.getConfiguration('quota');
  const customDataDir = config.get('dataDirectory');

  let dataDir;
  if (customDataDir && typeof customDataDir === 'string' && customDataDir.trim().length > 0) {
    dataDir = path.resolve(customDataDir.trim());
  } else if (context && context.globalStorageUri) {
    dataDir = path.join(os.homedir(), '.config', 'quota');
  } else {
    dataDir = path.join(os.homedir(), '.config', 'quota');
  }

  try {
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
  } catch (err) {
    console.warn('Quota: Could not create data directory, fallback to temp:', err);
    dataDir = path.join(os.tmpdir(), 'quota_data');
    if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
  }

  // Look for tracker.py inside extension directory first, then fallback to parent (for development)
  let trackerScript = path.join(extDir, 'tracker.py');
  if (!fs.existsSync(trackerScript)) {
    const parentScript = path.join(extDir, '..', 'tracker.py');
    if (fs.existsSync(parentScript)) {
      trackerScript = parentScript;
    }
  }

  // Look for dashboard.html inside extension directory first, then fallback to parent
  let dashboardHtml = path.join(extDir, 'dashboard.html');
  if (!fs.existsSync(dashboardHtml)) {
    const parentHtml = path.join(extDir, '..', 'dashboard.html');
    if (fs.existsSync(parentHtml)) {
      dashboardHtml = parentHtml;
    }
  }

  const dataPath = path.join(dataDir, 'persistent_ledger.json');
  const brainDir = path.join(os.homedir(), '.gemini', 'antigravity-ide', 'brain');

  return { extDir, dataDir, trackerScript, dashboardHtml, dataPath, brainDir };
}

// Resolve Python executable dynamically
function getPythonExecutable() {
  const config = vscode.workspace.getConfiguration('quota');
  const customPython = config.get('pythonPath');
  if (customPython && typeof customPython === 'string' && customPython.trim().length > 0) {
    return customPython.trim();
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function formatCompact(num) {
  if (!num || isNaN(num)) return '0';
  if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
  if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
  if (num >= 1e3) return (num / 1e3).toFixed(1) + 'k';
  return num.toLocaleString();
}

function formatCurrency(val) {
  if (!val || isNaN(val)) return '$0.00';
  return '$' + Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function loadTokenData(context) {
  try {
    const { dataPath } = getPaths(context || extensionContext);
    if (fs.existsSync(dataPath)) {
      const raw = fs.readFileSync(dataPath, 'utf8');
      return JSON.parse(raw);
    }
  } catch (err) {
    console.error('Quota: Error reading token data:', err);
  }
  return null;
}

function getCurrentWorkspaceName() {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].name;
  }
  if (vscode.window.activeTextEditor) {
    const filePath = vscode.window.activeTextEditor.document.uri.fsPath;
    const homeDir = os.homedir();
    const homeBase = path.basename(homeDir);
    const ignored = new Set(['Users', 'home', homeBase, 'Desktop', 'Downloads', 'Documents', 'Projects', 'Projectss']);
    const parts = filePath.split(path.sep);
    for (let i = parts.length - 2; i >= 0; i--) {
      const p = parts[i];
      if (p && !ignored.has(p)) {
        return p;
      }
    }
  }
  return null;
}

function getProjectStats(data, projectName) {
  if (!projectName || !data || !data.projects) return null;
  if (data.projects[projectName]) return data.projects[projectName];

  const lower = projectName.toLowerCase();
  for (const [k, v] of Object.entries(data.projects)) {
    if (k.toLowerCase() === lower) return v;
  }
  for (const [k, v] of Object.entries(data.projects)) {
    if (k.toLowerCase().includes(lower) || lower.includes(k.toLowerCase())) return v;
  }
  return null;
}

function getDisplayMode(context) {
  const ctx = context || extensionContext;
  return (ctx && ctx.globalState ? ctx.globalState.get('statusBarMode', 'session') : 'session');
}

function setDisplayMode(context, mode) {
  const ctx = context || extensionContext;
  if (ctx && ctx.globalState) {
    ctx.globalState.update('statusBarMode', mode);
  }
  updateStatusBar(ctx);
}

function updateStatusBar(context) {
  if (!statusBarItem) return;
  const data = loadTokenData(context);
  if (!data || !data.summary) {
    statusBarItem.text = `$(sparkle) Initializing...`;
    statusBarItem.tooltip = 'Quota: Scanning token telemetry...';
    statusBarItem.show();
    return;
  }

  const s = data.summary;
  const act = data.active_session;
  const currentProject = getCurrentWorkspaceName();
  const projStats = getProjectStats(data, currentProject);
  const displayMode = getDisplayMode(context);

  let label = '';
  let detailDesc = '';

  if (displayMode === 'session' && act && act.total_tokens > 0) {
    label = `✨ ${formatCompact(act.total_tokens)} Tokens | ${formatCurrency(act.cost_cached_usd)}`;
    detailDesc = `[Active Chat Session] ${act.short_id || ''} (${act.primary_model || 'IDE AI'})\n• Fresh Prompt: ${formatCompact(act.fresh_input_tokens)}\n• Cached Context: ${formatCompact(act.cached_context_tokens)}\n• Model Completions: ${formatCompact(act.output_tokens)}\n• Standard API Value: ${formatCurrency(act.cost_uncached_usd)}`;
  } else if (displayMode === 'workspace' && projStats) {
    label = `✨ ${formatCompact(projStats.tokens)} Tokens | ${formatCurrency(projStats.cost_cached_usd)}`;
    detailDesc = `[Workspace: ${currentProject}]\n• Total Turns: ${projStats.invocations || 0}\n• Active Sessions: ${projStats.conversations || 0}\n• Standard API Value: ${formatCurrency(projStats.cost_uncached_usd)}`;
  } else {
    label = `✨ ${formatCompact(s.total_cumulative_tokens)} Tokens | ${formatCurrency(s.cost_cached_usd)}`;
    detailDesc = `[Lifetime Global Total]\n• Total Volume: ${formatCompact(s.total_cumulative_tokens)} (${(s.cache_hit_ratio_pct || 99.9)}% Cache Hit)\n• Standard Value: ${formatCurrency(s.cost_uncached_usd)}\n• Autonomous Turns: ${(s.total_invocations || 0).toLocaleString()}`;
  }

  statusBarItem.text = label;
  statusBarItem.tooltip = new vscode.MarkdownString(
    `### ⚡ Quota — AI Token & Cost Intelligence\n\n` +
    `**Display Mode**: \`${displayMode.toUpperCase()}\` *(Click status bar to switch)*\n\n` +
    `${detailDesc}\n\n` +
    `---\n` +
    `*Click to open Quota Dashboard or Quick Actions*`
  );
  statusBarItem.tooltip.isTrusted = true;
  statusBarItem.show();
}

// Secure Process Execution using execFile (Zero Shell Injection)
function runTrackerInBackground(callback) {
  if (isScanning) return;
  isScanning = true;

  const { trackerScript, dataDir } = getPaths(extensionContext);
  const pythonBin = getPythonExecutable();
  const args = [trackerScript, '--data-dir', dataDir];

  execFile(pythonBin, args, { timeout: 45000 }, (error, stdout, stderr) => {
    isScanning = false;
    if (error) {
      console.error('Quota execution error:', error.message, stderr);
      if (error.code === 'ENOENT') {
        vscode.window.showWarningMessage(
          `Quota: Python binary '${pythonBin}' was not found. Please ensure Python 3 is installed or set 'quota.pythonPath' in VS Code Settings.`,
          'Open Settings'
        ).then(choice => {
          if (choice === 'Open Settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'quota.pythonPath');
          }
        });
      }
    } else {
      if (extensionContext) {
        updateStatusBar(extensionContext);
      }
      if (currentWebview) {
        const freshData = loadTokenData(extensionContext);
        if (freshData) {
          currentWebview.webview.postMessage({
            command: 'updateData',
            data: freshData
          });
        }
      }
    }
    if (callback) callback(error);
  });
}

function checkForRealtimeLogChanges() {
  try {
    const { brainDir } = getPaths(extensionContext);
    if (!fs.existsSync(brainDir)) return;

    let latestMtime = 0;
    let latestSize = 0;

    const convDirs = fs.readdirSync(brainDir);
    for (const d of convDirs) {
      const transcriptPath = path.join(brainDir, d, '.system_generated', 'logs', 'transcript.jsonl');
      if (fs.existsSync(transcriptPath)) {
        const stat = fs.statSync(transcriptPath);
        if (stat.mtimeMs > latestMtime) {
          latestMtime = stat.mtimeMs;
          latestSize = stat.size;
        }
      }
    }

    if (latestMtime > lastKnownMtime || (latestMtime === lastKnownMtime && latestSize !== lastKnownSize)) {
      lastKnownMtime = latestMtime;
      lastKnownSize = latestSize;
      runTrackerInBackground();
    }
  } catch (err) {
    // Non-fatal background check
  }
}

function loadWebviewContent(panel) {
  try {
    const { dashboardHtml } = getPaths(extensionContext);
    if (fs.existsSync(dashboardHtml)) {
      let html = fs.readFileSync(dashboardHtml, 'utf8');
      panel.webview.html = html;
    } else {
      panel.webview.html = `<!DOCTYPE html><html><body style="background:#09090b;color:#f4f4f5;padding:24px;font-family:sans-serif;"><h2>Quota Cockpit Initializing...</h2><p>Please wait a moment while the first scan compiles.</p></body></html>`;
      runTrackerInBackground(() => {
        if (currentWebview && fs.existsSync(dashboardHtml)) {
          currentWebview.webview.html = fs.readFileSync(dashboardHtml, 'utf8');
        }
      });
    }
  } catch (err) {
    panel.webview.html = `<h1>Error loading Quota: ${err.message}</h1>`;
  }
}

function openDashboard(context) {
  if (currentWebview) {
    currentWebview.reveal(vscode.ViewColumn.One);
    return;
  }

  currentWebview = vscode.window.createWebviewPanel(
    'antigravityTokenDashboard',
    'Quota',
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true
    }
  );

  loadWebviewContent(currentWebview);

  currentWebview.webview.onDidReceiveMessage(
    message => {
      if (message.command === 'refresh') {
        runTrackerInBackground(() => {
          vscode.window.showInformationMessage('Quota: Telemetry refreshed successfully!');
        });
      } else if (message.command === 'exportCsv') {
        exportCsvFileQuick(context);
      }
    },
    undefined,
    context.subscriptions
  );

  currentWebview.onDidDispose(() => {
    currentWebview = null;
  });
}

function showQuickControlMenu(context) {
  const data = loadTokenData(context);
  const currentMode = getDisplayMode(context);

  const modeNames = {
    session: 'Active Chat Session',
    workspace: 'Current Workspace',
    total: 'Lifetime Global Total'
  };

  const items = [
    {
      label: '$(dashboard) Open Visual Cockpit',
      description: 'Full analytics, continuous timeline curve, trace inspector drawer',
      action: 'open_dashboard'
    },
    {
      label: '$(sync) Refresh Token Scan Now',
      description: 'Re-scan active brain logs and update persistent ledger immediately',
      action: 'refresh'
    },
    {
      label: `$(eye) Switch Status Bar Display: [${modeNames[currentMode] || currentMode}]`,
      description: 'Toggle between Active Session, Current Workspace, and Lifetime Total',
      action: 'toggle_mode'
    },
    {
      label: '$(cloud-download) Export Ledger to CSV',
      description: 'Save conversation ledger to spreadsheet for accounting/invoicing',
      action: 'export_csv'
    },
    {
      label: '$(clippy) Copy Summary to Clipboard',
      description: 'Copy formatted markdown summary for GitHub PR, Jira, or Slack',
      action: 'copy_summary'
    }
  ];

  vscode.window.showQuickPick(items, {
    placeHolder: 'Quota — Telemetry & Quick Actions'
  }).then(selection => {
    if (!selection) return;

    if (selection.action === 'open_dashboard') {
      openDashboard(context);
    } else if (selection.action === 'refresh') {
      vscode.commands.executeCommand('antigravity-tracker.refresh');
    } else if (selection.action === 'toggle_mode') {
      const nextMode = currentMode === 'session' ? 'workspace' : currentMode === 'workspace' ? 'total' : 'session';
      setDisplayMode(context, nextMode);
      vscode.window.showInformationMessage(`Quota: Status bar switched to ${modeNames[nextMode]}`);
    } else if (selection.action === 'export_csv') {
      exportCsvFileQuick(context);
    } else if (selection.action === 'copy_summary') {
      copyMarkdownSummaryQuick(data);
    }
  });
}

// Secure CSV Export using execFile
function exportCsvFileQuick(context) {
  const homeDir = os.homedir();
  const defaultPath = path.join(homeDir, 'Downloads', `quota_token_ledger_${new Date().toISOString().slice(0,10)}.csv`);

  vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(defaultPath),
    filters: { 'CSV Files': ['csv'] }
  }).then(uri => {
    if (!uri) return;
    const targetFile = uri.fsPath;
    const { trackerScript, dataDir } = getPaths(context || extensionContext);
    const pythonBin = getPythonExecutable();

    execFile(pythonBin, [trackerScript, '--data-dir', dataDir, '--export-csv', targetFile], (err) => {
      if (err) {
        vscode.window.showErrorMessage('Quota: CSV Export failed: ' + err.message);
      } else {
        vscode.window.showInformationMessage(`✅ Quota: Ledger CSV exported to ${path.basename(targetFile)}`, 'Open File').then(choice => {
          if (choice === 'Open File') {
            vscode.env.openExternal(vscode.Uri.file(targetFile));
          }
        });
      }
    });
  });
}

function copyMarkdownSummaryQuick(data) {
  if (!data || !data.summary) return;
  const s = data.summary;
  const md = `### 🚀 Quota — Token & Cost Intelligence Report
- **Total Processed Volume**: ${formatCompact(s.total_cumulative_tokens)} (${(s.cache_hit_ratio_pct || 99.9)}% Prompt Cache Hit)
- **Standard Commercial Valuation**: $${s.cost_uncached_usd.toFixed(2)} USD
- **Prompt-Cached Real Cost**: $${s.cost_cached_usd.toFixed(2)} USD (*Saved $${s.cache_savings_usd.toFixed(2)}*)
- **Autonomous AI Turns**: ${(s.total_invocations || 0).toLocaleString()} across ${s.total_conversations || 0} sessions
*Generated by Quota for VS Code & Antigravity IDE*`;

  vscode.env.clipboard.writeText(md).then(() => {
    vscode.window.showInformationMessage('📋 Quota summary report copied to clipboard!');
  });
}

function activate(context) {
  extensionContext = context;
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 999);
  statusBarItem.command = 'antigravity-tracker.quickMenu';
  context.subscriptions.push(statusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand('antigravity-tracker.quickMenu', () => showQuickControlMenu(context)),
    vscode.commands.registerCommand('antigravity-tracker.openDashboard', () => openDashboard(context)),
    vscode.commands.registerCommand('antigravity-tracker.refresh', () => {
      vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Quota: Scanning Antigravity IDE token logs...'
      }, async () => {
        return new Promise(resolve => {
          runTrackerInBackground(error => {
            if (!error) {
              vscode.window.showInformationMessage('Quota: Telemetry updated successfully!');
            }
            resolve();
          });
        });
      });
    }),
    vscode.commands.registerCommand('antigravity-tracker.showQuickSummary', () => {
      const data = loadTokenData(context);
      if (!data) return;
      const s = data.summary;
      const act = data.active_session;
      if (act) {
        vscode.window.showInformationMessage(
          `⚡ Active Session: ${formatCompact(act.total_tokens)} tokens ($${act.cost_uncached_usd.toFixed(2)}) | 🌐 Lifetime: ${formatCompact(s.total_cumulative_tokens)} ($${s.cost_uncached_usd.toFixed(2)})`
        );
      } else {
        vscode.window.showInformationMessage(
          `🪙 Total Tokens: ${formatCompact(s.total_cumulative_tokens)} | 💵 Value: $${s.cost_uncached_usd.toFixed(2)} USD`
        );
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(() => updateStatusBar(context)),
    vscode.window.onDidChangeActiveTextEditor(() => updateStatusBar(context))
  );

  // Initial update
  updateStatusBar(context);

  // Initial background scan
  runTrackerInBackground();

  // Polling interval from settings (default: 2.5s)
  const pollMs = 2500;
  pollInterval = setInterval(() => {
    checkForRealtimeLogChanges();
  }, pollMs);
  context.subscriptions.push({ dispose: () => clearInterval(pollInterval) });

  // Native fs.watch on brain directory with debouncing
  const { brainDir } = getPaths(context);
  if (fs.existsSync(brainDir)) {
    try {
      fs.watch(brainDir, { recursive: true }, (eventType, filename) => {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => {
          checkForRealtimeLogChanges();
        }, 1200);
      });
    } catch (e) {
      console.log('Quota: fs.watch fallback to poller:', e);
    }
  }
}

function deactivate() {
  if (statusBarItem) statusBarItem.dispose();
  if (pollInterval) clearInterval(pollInterval);
}

module.exports = { activate, deactivate };

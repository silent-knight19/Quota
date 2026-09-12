#!/usr/bin/env python3
"""
Antigravity Token & Cost Intelligence — Enterprise Governance & Observability Engine
Production-grade financial controls, context compounding profiling, and disaster recovery.
"""

import os
import sys
import glob
import json
import re
import csv
import io
import math
import calendar
import sqlite3
import shutil
import argparse
import time
import secrets
import hashlib
from datetime import datetime
from collections import defaultdict

try:
    import fcntl
except ImportError:
    fcntl = None

class InterProcessLock:
    """OS-level advisory file lock with timeout for cross-process synchronization."""
    def __init__(self, lock_path=None, timeout=30.0):
        self.lock_path = lock_path or os.path.join(DATA_DIR, ".scan.lock")
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.lock_path)), exist_ok=True)
        self.fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        start_time = time.time()
        while True:
            try:
                if fcntl and hasattr(fcntl, "flock"):
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (BlockingIOError, OSError):
                if time.time() - start_time >= self.timeout:
                    raise TimeoutError(f"Timed out waiting for scan lock: {self.lock_path}")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                if fcntl and hasattr(fcntl, "flock"):
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.platform == "win32":
    default_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "quota")
else:
    default_dir = os.path.expanduser("~/.config/quota")
DEFAULT_DATA_DIR = os.environ.get("QUOTA_DATA_DIR") or default_dir
DATA_DIR = DEFAULT_DATA_DIR
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-ide/brain")
DB_PATH = os.path.join(DATA_DIR, "persistent_ledger.sqlite")
LEDGER_JSON = os.path.join(DATA_DIR, "persistent_ledger.json")
TOKEN_DATA_JSON = os.path.join(DATA_DIR, "token_data.json")
BACKUP_DIR_LOCAL = os.path.join(DATA_DIR, "backups")
BUDGET_FILE = os.path.join(DATA_DIR, "budget_config.json")
ICLOUD_BACKUP_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AntigravityTokenBackups")

def atomic_write_json(target_path: str, data, mode=0o600):
    """Write JSON atomically using PID-specific temp file and os.replace()."""
    target = os.path.abspath(target_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass
    os.replace(tmp, target)

def safe_csv_cell(value):
    """Neutralize spreadsheet formula injection characters (=, +, -, @, \\t, \\r)."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text

def set_active_data_dir(custom_dir):
    global DATA_DIR, DB_PATH, LEDGER_JSON, TOKEN_DATA_JSON, BACKUP_DIR_LOCAL, BUDGET_FILE
    DATA_DIR = os.path.abspath(os.path.expanduser(custom_dir))
    os.makedirs(DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(DATA_DIR, "persistent_ledger.sqlite")
    LEDGER_JSON = os.path.join(DATA_DIR, "persistent_ledger.json")
    TOKEN_DATA_JSON = os.path.join(DATA_DIR, "token_data.json")
    BACKUP_DIR_LOCAL = os.path.join(DATA_DIR, "backups")
    BUDGET_FILE = os.path.join(DATA_DIR, "budget_config.json")

def ensure_data_migration():
    os.makedirs(DATA_DIR, exist_ok=True)
    legacy_db = os.path.join(BASE_DIR, "persistent_ledger.sqlite")
    if os.path.exists(legacy_db) and not os.path.exists(DB_PATH) and os.path.abspath(legacy_db) != os.path.abspath(DB_PATH):
        try:
            shutil.copy2(legacy_db, DB_PATH)
            legacy_json = os.path.join(BASE_DIR, "persistent_ledger.json")
            if os.path.exists(legacy_json) and not os.path.exists(LEDGER_JSON):
                shutil.copy2(legacy_json, LEDGER_JSON)
            print(f"📦 Successfully migrated historical ledger to: {DB_PATH}")
        except Exception as e:
            print(f"⚠️  Legacy migration notice: {e}")

ensure_data_migration()

# Enterprise Model Pricing Table ($ per Million Tokens)
PRICING_TABLE = {
    "Claude Opus 4.6 (Thinking)": {
        "family": "Anthropic",
        "input_uncached": 15.00,
        "input_cached_read": 1.50,
        "output": 75.00,
        "thinking": 75.00,
    },
    "Claude Sonnet 4.6 (Thinking)": {
        "family": "Anthropic",
        "input_uncached": 3.00,
        "input_cached_read": 0.30,
        "output": 15.00,
        "thinking": 15.00,
    },
    "Claude 3.5 Sonnet": {
        "family": "Anthropic",
        "input_uncached": 3.00,
        "input_cached_read": 0.30,
        "output": 15.00,
        "thinking": 15.00,
    },
    "Claude 3.5 Haiku": {
        "family": "Anthropic",
        "input_uncached": 0.80,
        "input_cached_read": 0.08,
        "output": 4.00,
        "thinking": 4.00,
    },
    "Gemini 3.1 Pro (High)": {
        "family": "Google",
        "input_uncached": 1.25,
        "input_cached_read": 0.3125,
        "output": 5.00,
        "thinking": 5.00,
    },
    "Gemini 2.0 Flash": {
        "family": "Google",
        "input_uncached": 0.10,
        "input_cached_read": 0.025,
        "output": 0.40,
        "thinking": 0.40,
    },
    "Gemini 1.5 Pro": {
        "family": "Google",
        "input_uncached": 1.25,
        "input_cached_read": 0.3125,
        "output": 5.00,
        "thinking": 5.00,
    },
    "Gemini 1.5 Flash": {
        "family": "Google",
        "input_uncached": 0.075,
        "input_cached_read": 0.01875,
        "output": 0.30,
        "thinking": 0.30,
    },
    "GPT-4": {
        "family": "OpenAI",
        "input_uncached": 30.00,
        "input_cached_read": 15.00,
        "output": 60.00,
        "thinking": 60.00,
    },
    "GPT-4o": {
        "family": "OpenAI",
        "input_uncached": 2.50,
        "input_cached_read": 1.25,
        "output": 10.00,
        "thinking": 10.00,
    },
    "GPT-4o-mini": {
        "family": "OpenAI",
        "input_uncached": 0.15,
        "input_cached_read": 0.075,
        "output": 0.60,
        "thinking": 0.60,
    },
    "o1": {
        "family": "OpenAI",
        "input_uncached": 15.00,
        "input_cached_read": 7.50,
        "output": 60.00,
        "thinking": 60.00,
    },
    "o1-mini": {
        "family": "OpenAI",
        "input_uncached": 3.00,
        "input_cached_read": 1.50,
        "output": 12.00,
        "thinking": 12.00,
    },
    "o3": {
        "family": "OpenAI",
        "input_uncached": 15.00,
        "input_cached_read": 7.50,
        "output": 60.00,
        "thinking": 60.00,
    },
    "o3-mini": {
        "family": "OpenAI",
        "input_uncached": 1.10,
        "input_cached_read": 0.55,
        "output": 4.40,
        "thinking": 4.40,
    },
    "Gemini 3.8 Flash (High)": {
        "family": "Google",
        "input_uncached": 0.10,
        "input_cached_read": 0.025,
        "output": 0.40,
        "thinking": 0.40,
    },
    "Gemini 3.8 Flash (Medium)": {
        "family": "Google",
        "input_uncached": 0.10,
        "input_cached_read": 0.025,
        "output": 0.40,
        "thinking": 0.40,
    },
    "Gemini 3.8 Flash (Low)": {
        "family": "Google",
        "input_uncached": 0.10,
        "input_cached_read": 0.025,
        "output": 0.40,
        "thinking": 0.40,
    },
    "Gemini 3.7 Flash (High)": {
        "family": "Google",
        "input_uncached": 0.10,
        "input_cached_read": 0.025,
        "output": 0.40,
        "thinking": 0.40,
    },
    "Gemini 3.7 Flash (Medium)": {
        "family": "Google",
        "input_uncached": 0.10,
        "input_cached_read": 0.025,
        "output": 0.40,
        "thinking": 0.40,
    },
    "Gemini 3.6 Flash (High)": {
        "family": "Google",
        "input_uncached": 0.075,
        "input_cached_read": 0.01875,
        "output": 0.30,
        "thinking": 0.30,
    },
    "Gemini 3.6 Flash (Medium)": {
        "family": "Google",
        "input_uncached": 0.075,
        "input_cached_read": 0.01875,
        "output": 0.30,
        "thinking": 0.30,
    },
    "Gemini 3.6 Flash (Low)": {
        "family": "Google",
        "input_uncached": 0.075,
        "input_cached_read": 0.01875,
        "output": 0.30,
        "thinking": 0.30,
    },
    "Gemini 3.5 Flash (High)": {
        "family": "Google",
        "input_uncached": 0.075,
        "input_cached_read": 0.01875,
        "output": 0.30,
        "thinking": 0.30,
    },
    "Gemini 3.5 Flash (Low)": {
        "family": "Google",
        "input_uncached": 0.075,
        "input_cached_read": 0.01875,
        "output": 0.30,
        "thinking": 0.30,
    },
    "Default": {
        "family": "Google",
        "input_uncached": 0.20,
        "input_cached_read": 0.05,
        "output": 1.00,
        "thinking": 1.00,
    }
}

# Physical Context Window Limits per Model Family
CONTEXT_WINDOW_LIMITS = {
    "Claude": 200_000,
    "Gemini": 200_000,
    "GPT-4o": 128_000,
    "GPT-4": 128_000,
    "o1": 200_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    "o1-mini": 128_000,
    "Default": 200_000,
}
DEFAULT_CONTEXT_WINDOW = CONTEXT_WINDOW_LIMITS["Default"]

def calculate_turn_cost(model_name: str, fresh_in: int, cached_in: int, out_tok: int, tool_tok: int = 0, thk_tok: int = 0) -> tuple:
    """Calculate standard (uncached) and prompt-cached commercial cost for a single turn."""
    pricing = get_pricing(model_name)
    total_in = fresh_in + cached_in
    billed_out = out_tok + tool_tok
    cost_uncached = (
        (total_in / 1_000_000.0) * pricing["input_uncached"] +
        (billed_out / 1_000_000.0) * pricing["output"] +
        (thk_tok / 1_000_000.0) * pricing["thinking"]
    )
    cost_cached = (
        (fresh_in / 1_000_000.0) * pricing["input_uncached"] +
        (cached_in / 1_000_000.0) * pricing["input_cached_read"] +
        (billed_out / 1_000_000.0) * pricing["output"] +
        (thk_tok / 1_000_000.0) * pricing["thinking"]
    )
    return cost_uncached, cost_cached

def get_model_context_limit(model_name: str) -> int:
    if not model_name:
        return CONTEXT_WINDOW_LIMITS["Default"]
    name_low = model_name.strip().lower()
    norm = normalize_model_str(model_name)

    # Sub-tier tokens checked first to prevent shadowing (e.g. o1-mini before o1)
    if "o1 mini" in norm or "o1-mini" in name_low:
        return CONTEXT_WINDOW_LIMITS["o1-mini"]
    if "o3 mini" in norm or "o3-mini" in name_low:
        return CONTEXT_WINDOW_LIMITS["o3-mini"]
    if "gpt 4o mini" in norm or "gpt-4o-mini" in name_low:
        return CONTEXT_WINDOW_LIMITS["GPT-4o"]
    if "gpt 4o" in norm or "gpt-4o" in name_low:
        return CONTEXT_WINDOW_LIMITS["GPT-4o"]
    if "gpt 4" in norm or "gpt-4" in name_low:
        return CONTEXT_WINDOW_LIMITS["GPT-4"]
    if "o1" in norm.split() or name_low.startswith("o1"):
        return CONTEXT_WINDOW_LIMITS["o1"]
    if "o3" in norm.split() or name_low.startswith("o3"):
        return CONTEXT_WINDOW_LIMITS["o3"]
    if "claude" in norm:
        return CONTEXT_WINDOW_LIMITS["Claude"]
    if "gemini" in norm:
        return CONTEXT_WINDOW_LIMITS["Gemini"]

    # Fallback to longest-key-first match
    candidates = sorted(
        [(k, v) for k, v in CONTEXT_WINDOW_LIMITS.items() if k != "Default"],
        key=lambda item: len(item[0]),
        reverse=True
    )
    for prefix, limit in candidates:
        p_low = prefix.lower()
        if p_low in name_low or normalize_model_str(prefix) in norm:
            return limit

    return CONTEXT_WINDOW_LIMITS["Default"]

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))

def normalize_model_str(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

PRICING_ALIASES = {
    "gpt 4": "GPT-4",
    "gpt 4 0314": "GPT-4",
    "gpt 4 0613": "GPT-4",
    "gpt 4 32k": "GPT-4",
    "gpt 4o": "GPT-4o",
    "gpt 4o mini": "GPT-4o-mini",
    "o1": "o1",
    "o1 mini": "o1-mini",
    "o1 preview": "o1",
    "o3": "o3",
    "o3 mini": "o3-mini",
    "claude 3 5 sonnet": "Claude 3.5 Sonnet",
    "claude 3 7 sonnet": "Claude Sonnet 4.6 (Thinking)",
    "claude 3 5 haiku": "Claude 3.5 Haiku",
    "claude 3 opus": "Claude Opus 4.6 (Thinking)",
    "claude opus 4 6": "Claude Opus 4.6 (Thinking)",
    "claude sonnet 4 6": "Claude Sonnet 4.6 (Thinking)",
    "gemini 1 5 pro": "Gemini 1.5 Pro",
    "gemini 1 5 flash": "Gemini 1.5 Flash",
    "gemini 2 0 flash": "Gemini 2.0 Flash",
    "gemini 3 1 pro": "Gemini 3.1 Pro (High)",
    "gemini 3 8 flash": "Gemini 3.8 Flash (High)",
    "gemini 3 7 flash": "Gemini 3.7 Flash (High)",
    "gemini 3 6 flash": "Gemini 3.6 Flash (High)",
    "gemini 3 5 flash": "Gemini 3.5 Flash (High)",
}

def get_pricing(model_name: str) -> dict:
    if not model_name:
        return PRICING_TABLE["Default"]
    if model_name in PRICING_TABLE:
        return PRICING_TABLE[model_name]

    name_low = model_name.strip().lower()
    for k, v in PRICING_TABLE.items():
        if k.lower() == name_low:
            return v

    norm = normalize_model_str(model_name)
    for k, v in PRICING_TABLE.items():
        if normalize_model_str(k) == norm:
            return v

    if norm in PRICING_ALIASES:
        return PRICING_TABLE[PRICING_ALIASES[norm]]

    # Specific sub-tier tokens checked FIRST to prevent parent shadowing
    if "o1 mini" in norm or "o1-mini" in name_low:
        return PRICING_TABLE["o1-mini"]
    if "o3 mini" in norm or "o3-mini" in name_low:
        return PRICING_TABLE["o3-mini"]
    if "gpt 4o mini" in norm or "gpt-4o-mini" in name_low:
        return PRICING_TABLE["GPT-4o-mini"]
    if "gpt 4o" in norm or "gpt-4o" in name_low:
        return PRICING_TABLE["GPT-4o"]
    if "gpt 4" in norm or "gpt-4" in name_low:
        return PRICING_TABLE["GPT-4"]
    if "haiku" in norm:
        return PRICING_TABLE["Claude 3.5 Haiku"]
    if "flash" in norm:
        if "1 5" in norm:
            return PRICING_TABLE["Gemini 1.5 Flash"]
        if "2 0" in norm:
            return PRICING_TABLE["Gemini 2.0 Flash"]
        if "3 5" in norm:
            return PRICING_TABLE["Gemini 3.5 Flash (High)"]
        if "3 6" in norm:
            return PRICING_TABLE["Gemini 3.6 Flash (High)"]
        if "3 7" in norm:
            return PRICING_TABLE["Gemini 3.7 Flash (High)"]
        return PRICING_TABLE["Gemini 3.8 Flash (High)"]
    if "opus" in norm:
        return PRICING_TABLE["Claude Opus 4.6 (Thinking)"]
    if "sonnet" in norm:
        if "3 5" in norm:
            return PRICING_TABLE["Claude 3.5 Sonnet"]
        return PRICING_TABLE["Claude Sonnet 4.6 (Thinking)"]
    if "o1" in norm.split():
        return PRICING_TABLE["o1"]
    if "o3" in norm.split():
        return PRICING_TABLE["o3"]
    if "pro" in norm and ("gemini" in norm or "google" in norm):
        if "1 5" in norm:
            return PRICING_TABLE["Gemini 1.5 Pro"]
        return PRICING_TABLE["Gemini 3.1 Pro (High)"]
    if "claude" in norm:
        return PRICING_TABLE["Claude Sonnet 4.6 (Thinking)"]
    if "gemini" in norm:
        return PRICING_TABLE["Gemini 3.8 Flash (High)"]

    return PRICING_TABLE["Default"]

def clean_project_name(path_or_str: str) -> str:
    if not path_or_str:
        return "General"
    raw = str(path_or_str).strip()
    if "->" in raw:
        raw = raw.split("->")[0].strip()
    raw = raw.strip("[]'\" \t")
    if raw.startswith("file://"):
        raw = raw[7:]
    raw = raw.rstrip("/\\").strip("[]'\" \t")
    parts = [p.strip("[]'\" \t") for p in re.split(r"[\\/]", raw) if p]
    home_user = os.path.basename(os.path.expanduser("~"))
    ignored = {
        ".gemini", ".vscode", ".local", "Library", "Applications",
        "Users", "home", home_user, "tempmediaStorage",
        "Projects", "Projectss", "Documents", "Desktop", "Downloads",
        ".config", "AppData", "Local", "Roaming",
        "src", "lib", "dist", "build", "tests", "test", "scripts", "node_modules"
    }
    # Any folder immediately following 'Users' or 'home' is a username folder
    for i, p in enumerate(parts):
        if i > 0 and parts[i - 1].lower() in ("users", "home"):
            ignored.add(p)

    filtered = []
    for p in parts:
        if re.match(r"^[A-Za-z]:$", p):
            continue
        if p in ignored:
            continue
        filtered.append(p)
    if not filtered:
        return "General"

    if len(filtered) > 1 and re.search(r"\.(md|py|js|ts|json|html|css|txt|csv|jsx|tsx|go|rs|c|cpp|h|rb|php|java)$", filtered[-1], re.IGNORECASE):
        return filtered[-2]

    return filtered[-1]

def load_budget() -> dict:
    os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)
    default_budget = {"daily_usd": 5.00, "monthly_usd": 50.00}
    if os.path.exists(BUDGET_FILE):
        try:
            with open(BUDGET_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                return {
                    "daily_usd": float(d.get("daily_usd", 5.00)),
                    "monthly_usd": float(d.get("monthly_usd", 50.00))
                }
        except Exception:
            pass
    return default_budget

def save_budget(daily: float, monthly: float) -> dict:
    d_val = float(daily)
    m_val = float(monthly)
    if not math.isfinite(d_val) or d_val < 0.10:
        raise ValueError("Daily budget must be a positive finite number >= 0.10")
    if not math.isfinite(m_val) or m_val < 1.00:
        raise ValueError("Monthly budget must be a positive finite number >= 1.00")
    os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)
    d = {"daily_usd": round(d_val, 2), "monthly_usd": round(m_val, 2)}
    atomic_write_json(BUDGET_FILE, d)
    return d

def get_db_connection(db_path=None):
    target_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except:
        pass
    return conn

def init_database(db_path=None):
    target_path = db_path or DB_PATH
    conn = get_db_connection(target_path)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS conversations_ledger (
        conv_id TEXT PRIMARY KEY,
        date TEXT,
        project TEXT,
        primary_model TEXT,
        models_json TEXT,
        fresh_input_tokens INTEGER DEFAULT 0,
        cached_context_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        thinking_tokens INTEGER DEFAULT 0,
        tool_call_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        cost_uncached_usd REAL DEFAULT 0.0,
        cost_cached_usd REAL DEFAULT 0.0,
        invocations INTEGER DEFAULT 0,
        first_seen_at TEXT,
        last_updated_at TEXT,
        is_active INTEGER DEFAULT 1,
        tools_json TEXT DEFAULT '{}',
        trace_json TEXT DEFAULT '[]',
        anomaly_json TEXT DEFAULT '[]',
        daily_breakdown_json TEXT DEFAULT '{}',
        first_date TEXT DEFAULT ''
    )''')
    
    # Check if extra columns exist (schema migration)
    cur.execute("PRAGMA table_info(conversations_ledger)")
    cols = [row[1] for row in cur.fetchall()]
    if "tools_json" not in cols:
        cur.execute("ALTER TABLE conversations_ledger ADD COLUMN tools_json TEXT DEFAULT '{}'")
    if "trace_json" not in cols:
        cur.execute("ALTER TABLE conversations_ledger ADD COLUMN trace_json TEXT DEFAULT '[]'")
    if "anomaly_json" not in cols:
        cur.execute("ALTER TABLE conversations_ledger ADD COLUMN anomaly_json TEXT DEFAULT '[]'")
    if "daily_breakdown_json" not in cols:
        cur.execute("ALTER TABLE conversations_ledger ADD COLUMN daily_breakdown_json TEXT DEFAULT '{}'")
    if "first_date" not in cols:
        cur.execute("ALTER TABLE conversations_ledger ADD COLUMN first_date TEXT DEFAULT ''")
        
    cur.execute('''CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

def load_ledger_from_db(db_path=None) -> dict:
    target_path = db_path or DB_PATH
    if not os.path.exists(target_path):
        init_database(target_path)
    conn = get_db_connection(target_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute('SELECT * FROM conversations_ledger')
        rows = cur.fetchall()
        
        ledger = {}
        for r in rows:
            conv = dict(r)
            try:
                conv["models"] = json.loads(conv.get("models_json") or "[]")
            except:
                conv["models"] = [conv.get("primary_model")]
            try:
                conv["tools"] = json.loads(conv.get("tools_json") or "{}")
            except:
                conv["tools"] = {}
            try:
                conv["trace"] = json.loads(conv.get("trace_json") or "[]")
            except:
                conv["trace"] = []
            try:
                conv["anomalies"] = json.loads(conv.get("anomaly_json") or "[]")
            except:
                conv["anomalies"] = []
            try:
                conv["daily_breakdown"] = json.loads(conv.get("daily_breakdown_json") or "{}")
            except:
                conv["daily_breakdown"] = {}

            conv["first_date"] = conv.get("first_date") or (conv.get("first_seen_at", "")[:10] if conv.get("first_seen_at") else conv.get("date", "Unknown"))
            conv["id"] = conv["conv_id"]
            conv["short_id"] = conv["conv_id"][:8]
            ledger[conv["conv_id"]] = conv
        return ledger
    finally:
        conn.close()

def save_conversations_to_ledger(conversations_list, db_path=None):
    target_path = db_path or DB_PATH
    init_database(target_path)
    conn = get_db_connection(target_path)
    now_str = datetime.utcnow().isoformat() + "Z"
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        for c in conversations_list:
            models_json = json.dumps(c.get("models") or [c.get("primary_model")])
            tools_json = json.dumps(c.get("tools") or {})
            trace_json = json.dumps(c.get("trace") or [])
            anomaly_json = json.dumps(c.get("anomalies") or [])
            daily_breakdown_json = json.dumps(c.get("daily_breakdown") or {})
            first_date = str(c.get("first_date") or c.get("date") or "")
            first_seen = c.get("first_seen_at") or now_str
            
            cur.execute('''INSERT INTO conversations_ledger (
                conv_id, date, project, primary_model, models_json,
                fresh_input_tokens, cached_context_tokens, output_tokens, thinking_tokens, tool_call_tokens,
                total_tokens, cost_uncached_usd, cost_cached_usd, invocations,
                first_seen_at, last_updated_at, is_active, tools_json, trace_json, anomaly_json,
                daily_breakdown_json, first_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conv_id) DO UPDATE SET
                date = excluded.date,
                project = excluded.project,
                primary_model = excluded.primary_model,
                models_json = excluded.models_json,
                fresh_input_tokens = excluded.fresh_input_tokens,
                cached_context_tokens = excluded.cached_context_tokens,
                output_tokens = excluded.output_tokens,
                thinking_tokens = excluded.thinking_tokens,
                tool_call_tokens = excluded.tool_call_tokens,
                total_tokens = excluded.total_tokens,
                cost_uncached_usd = excluded.cost_uncached_usd,
                cost_cached_usd = excluded.cost_cached_usd,
                invocations = excluded.invocations,
                last_updated_at = excluded.last_updated_at,
                is_active = excluded.is_active,
                tools_json = excluded.tools_json,
                trace_json = excluded.trace_json,
                anomaly_json = excluded.anomaly_json,
                daily_breakdown_json = excluded.daily_breakdown_json,
                first_date = excluded.first_date
            ''', (
                c["id"], c["date"], c["project"], c["primary_model"], models_json,
                c.get("fresh_input_tokens", 0), c.get("cached_context_tokens", 0),
                c.get("output_tokens", 0), c.get("thinking_tokens", 0), c.get("tool_call_tokens", 0),
                c.get("total_tokens", 0), c.get("cost_uncached_usd", 0.0), c.get("cost_cached_usd", 0.0),
                c.get("invocations", 0), first_seen, now_str, c.get("is_active", 1),
                tools_json, trace_json, anomaly_json, daily_breakdown_json, first_date
            ))
        
        cur.execute('''INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_sync', ?)''', (now_str,))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def format_local_date(created_at_str: str) -> str:
    if not created_at_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        clean = created_at_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean).astimezone()
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return created_at_str[:10] if len(created_at_str) >= 10 else datetime.now().strftime("%Y-%m-%d")

def scan_live_brain(brain_path=None) -> tuple:
    target_brain = brain_path or BRAIN_DIR
    if not os.path.exists(target_brain):
        return [], {}

    session_files = {}
    for p in glob.glob(os.path.join(target_brain, "*", ".system_generated", "logs", "transcript*.jsonl")):
        cid = p.split(os.sep)[-4]
        if cid not in session_files or p.endswith("transcript_full.jsonl"):
            session_files[cid] = p
    files = sorted(session_files.values())
        
    model_regex = re.compile(
        r"The user changed setting `Model Selection` from ([^`]+?) to ([^`]+?)\.\s*No need to comment",
        re.IGNORECASE
    )
    workspace_regex = re.compile(r"\[URI\] -> \[CorpusName\]:\s*\n([^\n]+)", re.MULTILINE)
    home_user_esc = re.escape(os.path.basename(os.path.expanduser("~")))
    path_regex = re.compile(
        rf"(?:(?:[A-Za-z]:)?[\\/](?:Users|home)[\\/]{home_user_esc}[\\/])([^\\/\r\n\"\'`]+)(?:[\\/]([^\\/\r\n\"\'`]+))?",
        re.IGNORECASE
    )
    ignored_path_roots = {
        '.gemini', '.vscode', '.local', 'Library', 'Applications', 'Users', 'home',
        home_user_esc, 'tempmediaStorage', 'Projects', 'Projectss', 'Documents', 'Desktop', 'Downloads',
        '.config', 'AppData', 'Local', 'Roaming', 'src', 'lib', 'dist', 'build', 'tests', 'test', 'scripts', 'node_modules'
    }
    
    scanned_convs = []
    global_tool_metrics = defaultdict(lambda: {"invocations": 0, "argument_tokens": 0})

    for file_path in files:
        conv_id = file_path.split(os.sep)[-4]
        current_model = "Gemini 3.6 Flash (High)"
        detected_project = None
        first_date = None
        latest_date = None
        conv_daily_stats = defaultdict(lambda: {
            "tokens": 0, "fresh_input_tokens": 0, "cached_context_tokens": 0,
            "output_tokens": 0, "tool_call_tokens": 0, "thinking_tokens": 0,
            "cost_uncached_usd": 0.0, "cost_cached_usd": 0.0, "invocations": 0
        })
        
        accumulated_history_tokens = 0
        fresh_turn_input_tokens = 0
        
        conv_fresh_in = 0
        conv_cached_in = 0
        conv_out = 0
        conv_thinking = 0
        conv_tools = 0
        conv_cost_uncached = 0.0
        conv_cost_cached = 0.0
        conv_invocations = 0
        models_in_conv = set()
        conv_tools_count = defaultdict(int)
        raw_steps_profile = []
        anomalies = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, 1):
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        step = json.loads(line_str)
                    except Exception:
                        if len(anomalies) < 5:
                            anomalies.append(f"Malformed JSON at line {line_no}")
                        continue
                    
                    if not isinstance(step, dict):
                        if len(anomalies) < 5:
                            anomalies.append(f"Invalid step structure at line {line_no}")
                        continue

                    try:
                        stype = step.get("type", "")
                        content = step.get("content") or ""
                        if not isinstance(content, str):
                            content = json.dumps(content) if content else ""
                        thinking = step.get("thinking") or ""
                        if not isinstance(thinking, str):
                            thinking = json.dumps(thinking) if thinking else ""
                        tool_calls = step.get("tool_calls") or []
                        if not isinstance(tool_calls, list):
                            tool_calls = []
                        created_at = step.get("created_at")
                        step_date = format_local_date(created_at) if created_at else (latest_date or datetime.now().strftime("%Y-%m-%d"))
                        if created_at and not first_date:
                            first_date = step_date
                        if created_at:
                            latest_date = step_date
                        
                        if "Model Selection" in content:
                            for m_from, m_to in model_regex.findall(content):
                                m_to = m_to.strip()
                                if m_to and m_to != "None":
                                    current_model = m_to
                        
                        models_in_conv.add(current_model)
                        pricing = get_pricing(current_model)
                        model_limit = get_model_context_limit(current_model)
                        
                        if not detected_project:
                            w_match = workspace_regex.search(content)
                            if w_match:
                                detected_project = clean_project_name(w_match.group(1))
                            else:
                                for p1, p2 in path_regex.findall(content):
                                    candidate = p2 if (p1 in ignored_path_roots and p2) else p1
                                    if candidate and candidate not in ignored_path_roots:
                                        detected_project = clean_project_name(candidate)
                                        break

                        # Detect Antigravity compaction / checkpoint events
                        is_compaction = (
                            stype == "CHECKPOINT" or
                            "Resuming from a compaction" in content or
                            content.strip().startswith("{{ CHECKPOINT") or
                            "The earlier parts of this conversation have been truncated" in content
                        )
                        if is_compaction:
                            summary_tokens = estimate_tokens(content)
                            accumulated_history_tokens = min(model_limit, max(8_000, summary_tokens))
                            fresh_turn_input_tokens = 0
                            continue

                        # Filter out error messages from backend overload/rate-limiting retries
                        if stype == "ERROR_MESSAGE" and ("overloaded" in content.lower() or "rate limit" in content.lower() or "model output error" in content.lower()):
                            continue
                        
                        # Track tools
                        step_tools = []
                        tool_tok = 0
                        if tool_calls:
                            tool_tok = estimate_tokens(json.dumps(tool_calls))
                            for tc in tool_calls:
                                if isinstance(tc, dict):
                                    t_name = tc.get("name") or tc.get("function", {}).get("name") or "tool"
                                else:
                                    t_name = "tool"
                                conv_tools_count[t_name] += 1
                                step_tools.append(t_name)
                                global_tool_metrics[t_name]["invocations"] += 1
                                global_tool_metrics[t_name]["argument_tokens"] += int(tool_tok / max(1, len(tool_calls)))

                        if stype == "PLANNER_RESPONSE":
                            out_tok = estimate_tokens(content)
                            thk_tok = estimate_tokens(thinking)
                            billed_step_out = out_tok + tool_tok

                            # Skip empty failed turns (0 out, 0 tools, 0 thinking - aborted or overloaded API response)
                            if billed_step_out == 0 and thk_tok == 0 and not content.strip():
                                continue

                            conv_invocations += 1
                            
                            # Context window is physically bounded by model limits
                            step_fresh_in = min(fresh_turn_input_tokens, model_limit)
                            step_cached_in = min(accumulated_history_tokens, max(0, model_limit - step_fresh_in))
                            step_total_in = step_fresh_in + step_cached_in
                            
                            cost_step_uncached = (
                                (step_total_in / 1_000_000.0) * pricing["input_uncached"] +
                                (billed_step_out / 1_000_000.0) * pricing["output"] +
                                (thk_tok / 1_000_000.0) * pricing["thinking"]
                            )
                            
                            cost_step_cached = (
                                (step_fresh_in / 1_000_000.0) * pricing["input_uncached"] +
                                (step_cached_in / 1_000_000.0) * pricing["input_cached_read"] +
                                (billed_step_out / 1_000_000.0) * pricing["output"] +
                                (thk_tok / 1_000_000.0) * pricing["thinking"]
                            )
                            
                            conv_fresh_in += step_fresh_in
                            conv_cached_in += step_cached_in
                            conv_out += out_tok
                            conv_tools += tool_tok
                            conv_thinking += thk_tok
                            conv_cost_uncached += cost_step_uncached
                            conv_cost_cached += cost_step_cached

                            step_total_tok = step_fresh_in + step_cached_in + out_tok + tool_tok + thk_tok
                            conv_daily_stats[step_date]["tokens"] += step_total_tok
                            conv_daily_stats[step_date]["fresh_input_tokens"] += step_fresh_in
                            conv_daily_stats[step_date]["cached_context_tokens"] += step_cached_in
                            conv_daily_stats[step_date]["output_tokens"] += out_tok
                            conv_daily_stats[step_date]["tool_call_tokens"] += tool_tok
                            conv_daily_stats[step_date]["thinking_tokens"] += thk_tok
                            conv_daily_stats[step_date]["cost_uncached_usd"] += cost_step_uncached
                            conv_daily_stats[step_date]["cost_cached_usd"] += cost_step_cached
                            conv_daily_stats[step_date]["invocations"] += 1
                            
                            raw_steps_profile.append({
                                "turn": conv_invocations,
                                "date": step_date,
                                "context": step_cached_in,
                                "out": billed_step_out,
                                "thk": thk_tok,
                                "tools": step_tools,
                                "cost": round(cost_step_cached, 4)
                            })

                            accumulated_history_tokens = min(
                                model_limit,
                                accumulated_history_tokens + step_fresh_in + billed_step_out + thk_tok
                            )
                            fresh_turn_input_tokens = 0
                        else:
                            step_tokens = estimate_tokens(content)
                            fresh_turn_input_tokens += step_tokens
                    except Exception as step_err:
                        anomalies.append(f"Turn {conv_invocations+1} processing error: {type(step_err).__name__}")
                        continue
        except Exception as file_err:
            print(f"⚠️  Quota: warning reading {file_path}: {file_err}", file=sys.stderr)
            if conv_invocations > 0:
                anomalies.append(f"Partial scan (file error: {type(file_err).__name__})")
            else:
                continue
        
        project_name = detected_project or "General"
        conv_total_tokens = conv_fresh_in + conv_cached_in + conv_out + conv_tools + conv_thinking
        
        # Downsample trace if long to keep payload ultra-fast (<35 points)
        downsampled_trace = []
        total_steps = len(raw_steps_profile)
        if total_steps <= 35:
            downsampled_trace = raw_steps_profile
        else:
            step_size = total_steps / 34.0
            downsampled_trace.append(raw_steps_profile[0])
            for i in range(1, 34):
                idx = min(int(round(i * step_size)), total_steps - 1)
                downsampled_trace.append(raw_steps_profile[idx])
            downsampled_trace.append(raw_steps_profile[-1])

        # Anomaly / Runaway tagging
        if conv_invocations >= 75:
            anomalies.append(f"Deep Session ({conv_invocations} turns)")
        if accumulated_history_tokens >= 120_000:
            anomalies.append(f"High Context Compounding ({accumulated_history_tokens//1000}k context)")
        if conv_cost_uncached >= 10.0:
            anomalies.append(f"High Value (${conv_cost_uncached:.2f})")
        if conv_tools_count.get("run_command", 0) >= 25:
            anomalies.append(f"Heavy Terminal Use ({conv_tools_count['run_command']} bash runs)")
        if conv_tools_count.get("view_file", 0) >= 30:
            anomalies.append(f"Heavy File Reads ({conv_tools_count['view_file']} files)")

        scanned_convs.append({
            "id": conv_id,
            "short_id": conv_id[:8],
            "date": latest_date or first_date or datetime.now().strftime("%Y-%m-%d"),
            "first_date": first_date or "Unknown",
            "daily_breakdown": {k: dict(v) for k, v in conv_daily_stats.items()},
            "project": project_name,
            "primary_model": current_model,
            "models": list(models_in_conv),
            "total_tokens": conv_total_tokens,
            "fresh_input_tokens": conv_fresh_in,
            "cached_context_tokens": conv_cached_in,
            "output_tokens": conv_out,
            "thinking_tokens": conv_thinking,
            "tool_call_tokens": conv_tools,
            "invocations": conv_invocations,
            "cost_uncached_usd": round(conv_cost_uncached, 3),
            "cost_cached_usd": round(conv_cost_cached, 3),
            "is_active": 1,
            "tools": dict(conv_tools_count),
            "trace": downsampled_trace,
            "anomalies": anomalies
        })
        
    return scanned_convs, dict(global_tool_metrics)

def merge_ledger_and_live(brain_path=None, db_path=None, rebuild=False) -> dict:
    target_brain = brain_path or BRAIN_DIR
    target_db = db_path or DB_PATH
    lock_file = os.path.join(os.path.dirname(os.path.abspath(target_db)), ".scan.lock")

    # Step 1: Scan filesystem OUTSIDE database lock for maximum performance
    live_convs, global_tools = scan_live_brain(target_brain)

    # Step 2: SQLite transactional UPSERT under InterProcessLock
    with InterProcessLock(lock_file):
        init_database(target_db)
        conn = get_db_connection(target_db)
        now_str = datetime.utcnow().isoformat() + "Z"
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()

            if rebuild:
                cur.execute("DELETE FROM conversations_ledger")

            for c in live_convs:
                models_json = json.dumps(c.get("models") or [c.get("primary_model")])
                tools_json = json.dumps(c.get("tools") or {})
                trace_json = json.dumps(c.get("trace") or [])
                anomaly_json = json.dumps(c.get("anomalies") or [])
                daily_breakdown_json = json.dumps(c.get("daily_breakdown") or {})
                first_date = str(c.get("first_date") or c.get("date") or "")
                first_seen = c.get("first_seen_at") or now_str

                cur.execute('''INSERT INTO conversations_ledger (
                    conv_id, date, project, primary_model, models_json,
                    fresh_input_tokens, cached_context_tokens, output_tokens, thinking_tokens, tool_call_tokens,
                    total_tokens, cost_uncached_usd, cost_cached_usd, invocations,
                    first_seen_at, last_updated_at, is_active, tools_json, trace_json, anomaly_json,
                    daily_breakdown_json, first_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conv_id) DO UPDATE SET
                    date = excluded.date,
                    project = excluded.project,
                    primary_model = excluded.primary_model,
                    models_json = excluded.models_json,
                    fresh_input_tokens = excluded.fresh_input_tokens,
                    cached_context_tokens = excluded.cached_context_tokens,
                    output_tokens = excluded.output_tokens,
                    thinking_tokens = excluded.thinking_tokens,
                    tool_call_tokens = excluded.tool_call_tokens,
                    total_tokens = excluded.total_tokens,
                    cost_uncached_usd = excluded.cost_uncached_usd,
                    cost_cached_usd = excluded.cost_cached_usd,
                    invocations = excluded.invocations,
                    last_updated_at = excluded.last_updated_at,
                    is_active = 1,
                    tools_json = excluded.tools_json,
                    trace_json = excluded.trace_json,
                    anomaly_json = excluded.anomaly_json,
                    daily_breakdown_json = excluded.daily_breakdown_json,
                    first_date = excluded.first_date
                ''', (
                    c["id"], c["date"], c["project"], c["primary_model"], models_json,
                    c.get("fresh_input_tokens", 0), c.get("cached_context_tokens", 0),
                    c.get("output_tokens", 0), c.get("thinking_tokens", 0), c.get("tool_call_tokens", 0),
                    c.get("total_tokens", 0), c.get("cost_uncached_usd", 0.0), c.get("cost_cached_usd", 0.0),
                    c.get("invocations", 0), first_seen, now_str, 1,
                    tools_json, trace_json, anomaly_json, daily_breakdown_json, first_date
                ))

            # Inactive check: Only mark is_active = 0 if session directory is proven absent on disk
            if os.path.exists(target_brain):
                cur.execute("SELECT conv_id FROM conversations_ledger WHERE is_active = 1")
                for (cid,) in cur.fetchall():
                    session_dir = os.path.join(target_brain, cid)
                    if not os.path.exists(session_dir):
                        cur.execute("UPDATE conversations_ledger SET is_active = 0 WHERE conv_id = ?", (cid,))

            cur.execute('''INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_sync', ?)''', (now_str,))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

        # Step 3: Read authoritative DB state
        existing_ledger = load_ledger_from_db(target_db)
        all_merged_convs = list(existing_ledger.values())
    
    overall = {
        "total_conversations": len(all_merged_convs),
        "active_conversations": sum(1 for c in all_merged_convs if c.get("is_active", 1) == 1),
        "archived_conversations": sum(1 for c in all_merged_convs if c.get("is_active", 1) == 0),
        "total_invocations": sum(c.get("invocations", 0) for c in all_merged_convs),
        "total_cumulative_tokens": sum(c.get("total_tokens", 0) for c in all_merged_convs),
        "fresh_input_tokens": sum(c.get("fresh_input_tokens", 0) for c in all_merged_convs),
        "cached_context_tokens": sum(c.get("cached_context_tokens", 0) for c in all_merged_convs),
        "total_input_tokens": sum(c.get("fresh_input_tokens", 0) + c.get("cached_context_tokens", 0) for c in all_merged_convs),
        "output_tokens": sum(c.get("output_tokens", 0) for c in all_merged_convs),
        "thinking_tokens": sum(c.get("thinking_tokens", 0) for c in all_merged_convs),
        "tool_call_tokens": sum(c.get("tool_call_tokens", 0) for c in all_merged_convs),
        "cost_uncached_usd": round(sum(c.get("cost_uncached_usd", 0.0) for c in all_merged_convs), 2),
        "cost_cached_usd": round(sum(c.get("cost_cached_usd", 0.0) for c in all_merged_convs), 2),
        "scanned_at": datetime.utcnow().isoformat() + "Z"
    }
    overall["cache_savings_usd"] = round(overall["cost_uncached_usd"] - overall["cost_cached_usd"], 2)
    overall["unique_content_tokens"] = overall["fresh_input_tokens"] + overall["output_tokens"] + overall["tool_call_tokens"] + overall["thinking_tokens"]
    
    if overall["total_input_tokens"] > 0:
        overall["cache_hit_ratio_pct"] = round(
            (overall["cached_context_tokens"] / overall["total_input_tokens"]) * 100, 1
        )
    else:
        overall["cache_hit_ratio_pct"] = 0.0

    model_stats = defaultdict(lambda: {
        "family": "Google",
        "total_tokens": 0,
        "fresh_input_tokens": 0,
        "cached_context_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "tool_call_tokens": 0,
        "invocations": 0,
        "cost_uncached_usd": 0.0,
        "cost_cached_usd": 0.0
    })
    
    project_stats = defaultdict(lambda: {
        "tokens": 0,
        "fresh_input_tokens": 0,
        "cached_context_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cost_uncached_usd": 0.0,
        "cost_cached_usd": 0.0,
        "conversations": 0,
        "invocations": 0,
        "models": set()
    })
    
    daily_stats = defaultdict(lambda: {
        "tokens": 0,
        "fresh_input_tokens": 0,
        "cached_context_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cost_uncached_usd": 0.0,
        "cost_cached_usd": 0.0,
        "invocations": 0
    })

    family_summary = defaultdict(lambda: {"tokens": 0, "cost_uncached": 0.0, "cost_cached": 0.0, "invocations": 0})
    family_summary["Google"] = {"tokens": 0, "cost_uncached": 0.0, "cost_cached": 0.0, "invocations": 0}
    family_summary["Anthropic"] = {"tokens": 0, "cost_uncached": 0.0, "cost_cached": 0.0, "invocations": 0}
    family_summary["OpenAI"] = {"tokens": 0, "cost_uncached": 0.0, "cost_cached": 0.0, "invocations": 0}

    for c in all_merged_convs:
        p_name = c.get("project", "General")
        m_name = c.get("primary_model", "Gemini 3.6 Flash (High)")
        fam = get_pricing(m_name).get("family", "Other")
        
        m = model_stats[m_name]
        m["family"] = fam
        m["total_tokens"] += c.get("total_tokens", 0)
        m["fresh_input_tokens"] += c.get("fresh_input_tokens", 0)
        m["cached_context_tokens"] += c.get("cached_context_tokens", 0)
        m["output_tokens"] += c.get("output_tokens", 0)
        m["thinking_tokens"] += c.get("thinking_tokens", 0)
        m["tool_call_tokens"] += c.get("tool_call_tokens", 0)
        m["invocations"] += c.get("invocations", 0)
        m["cost_uncached_usd"] += c.get("cost_uncached_usd", 0.0)
        m["cost_cached_usd"] += c.get("cost_cached_usd", 0.0)
        
        family_summary[fam]["tokens"] += c.get("total_tokens", 0)
        family_summary[fam]["cost_uncached"] += c.get("cost_uncached_usd", 0.0)
        family_summary[fam]["cost_cached"] += c.get("cost_cached_usd", 0.0)
        family_summary[fam]["invocations"] += c.get("invocations", 0)
            
        p = project_stats[p_name]
        p["tokens"] += c.get("total_tokens", 0)
        p["fresh_input_tokens"] += c.get("fresh_input_tokens", 0)
        p["cached_context_tokens"] += c.get("cached_context_tokens", 0)
        p["output_tokens"] += c.get("output_tokens", 0)
        p["thinking_tokens"] += c.get("thinking_tokens", 0)
        p["cost_uncached_usd"] += c.get("cost_uncached_usd", 0.0)
        p["cost_cached_usd"] += c.get("cost_cached_usd", 0.0)
        p["conversations"] += 1
        p["invocations"] += c.get("invocations", 0)
        p["models"].update(c.get("models") or [m_name])
        
        daily_bd = c.get("daily_breakdown")
        if daily_bd:
            for d_str, v in daily_bd.items():
                ds = daily_stats[d_str]
                ds["tokens"] += v.get("tokens", 0)
                ds["fresh_input_tokens"] += v.get("fresh_input_tokens", 0)
                ds["cached_context_tokens"] += v.get("cached_context_tokens", 0)
                ds["output_tokens"] += v.get("output_tokens", 0)
                ds["thinking_tokens"] += v.get("thinking_tokens", 0)
                ds["cost_uncached_usd"] += v.get("cost_uncached_usd", 0.0)
                ds["cost_cached_usd"] += v.get("cost_cached_usd", 0.0)
                ds["invocations"] += v.get("invocations", 0)
        else:
            d = c.get("date", "Unknown")
            if d != "Unknown":
                ds = daily_stats[d]
                ds["tokens"] += c.get("total_tokens", 0)
                ds["fresh_input_tokens"] += c.get("fresh_input_tokens", 0)
                ds["cached_context_tokens"] += c.get("cached_context_tokens", 0)
                ds["output_tokens"] += c.get("output_tokens", 0)
                ds["thinking_tokens"] += c.get("thinking_tokens", 0)
                ds["cost_uncached_usd"] += c.get("cost_uncached_usd", 0.0)
                ds["cost_cached_usd"] += c.get("cost_cached_usd", 0.0)
                ds["invocations"] += c.get("invocations", 0)

    for fam in list(family_summary.keys()):
        family_summary[fam]["cost_uncached"] = round(family_summary[fam]["cost_uncached"], 2)
        family_summary[fam]["cost_cached"] = round(family_summary[fam]["cost_cached"], 2)
    family_summary = dict(family_summary)

    model_serialized = {}
    for k, v in model_stats.items():
        v["cost_uncached_usd"] = round(v["cost_uncached_usd"], 2)
        v["cost_cached_usd"] = round(v["cost_cached_usd"], 2)
        v["total_input_tokens"] = v["fresh_input_tokens"] + v["cached_context_tokens"]
        model_serialized[k] = v

    project_serialized = {}
    for k, v in project_stats.items():
        v["cost_uncached_usd"] = round(v["cost_uncached_usd"], 2)
        v["cost_cached_usd"] = round(v["cost_cached_usd"], 2)
        v["models"] = list(v["models"])
        project_serialized[k] = v

    daily_timeline = [
        {
            "date": d,
            "tokens": v["tokens"],
            "fresh_input_tokens": v["fresh_input_tokens"],
            "cached_context_tokens": v["cached_context_tokens"],
            "output_tokens": v["output_tokens"],
            "thinking_tokens": v["thinking_tokens"],
            "cost_uncached_usd": round(v["cost_uncached_usd"], 2),
            "cost_cached_usd": round(v["cost_cached_usd"], 2),
            "invocations": v["invocations"]
        }
        for d, v in sorted(daily_stats.items())
    ]

    # Calculate Budget & Spend Pacing
    budget_cfg = load_budget()
    today_local = datetime.now().strftime("%Y-%m-%d")
    today_utc = datetime.utcnow().strftime("%Y-%m-%d")
    month_prefix = datetime.now().strftime("%Y-%m")

    # Match today's spend from local date first, then UTC
    today_data = daily_stats.get(today_local) or daily_stats.get(today_utc) or {"cost_cached_usd": 0.0, "cost_uncached_usd": 0.0, "tokens": 0}
    today_cost = round(today_data["cost_cached_usd"], 2)
    today_uncached = round(today_data["cost_uncached_usd"], 2)

    month_cost = round(sum(v["cost_cached_usd"] for d, v in daily_stats.items() if d.startswith(month_prefix)), 2)
    day_of_month = max(1, datetime.now().day)
    days_in_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
    projected_month = round((month_cost / day_of_month) * days_in_month, 2)
    
    daily_target = budget_cfg["daily_usd"]
    monthly_target = budget_cfg["monthly_usd"]
    daily_pct = round((today_cost / max(0.01, daily_target)) * 100, 1)
    monthly_pct = round((month_cost / max(0.01, monthly_target)) * 100, 1)
    
    budget_status = "normal"
    if daily_pct >= 100 or monthly_pct >= 100:
        budget_status = "exceeded"
    elif daily_pct >= 80 or monthly_pct >= 80:
        budget_status = "warning"

    budget_report = {
        "daily_target_usd": daily_target,
        "monthly_target_usd": monthly_target,
        "today_cost_cached": today_cost,
        "today_cost_uncached": today_uncached,
        "today_tokens": today_data["tokens"],
        "today_percent_used": daily_pct,
        "month_cost_cached": month_cost,
        "month_percent_used": monthly_pct,
        "projected_month_cost": projected_month,
        "status": budget_status
    }

    # Detect active chat session
    active_session_data = None
    latest_cid = None
    latest_mt = 0
    if os.path.exists(target_brain):
        for entry in os.scandir(target_brain):
            if entry.is_dir() and entry.name != 'tempmediaStorage':
                for cand_name in ["transcript_full.jsonl", "transcript.jsonl"]:
                    tf = os.path.join(entry.path, ".system_generated", "logs", cand_name)
                    if os.path.exists(tf):
                        mt = os.path.getmtime(tf)
                        if mt > latest_mt:
                            latest_mt = mt
                            latest_cid = entry.name
    if latest_cid and latest_cid in existing_ledger:
        active_session_data = existing_ledger[latest_cid]
    elif all_merged_convs:
        active_session_data = all_merged_convs[0]

    result = {
        "active_session": active_session_data,
        "budget": budget_report,
        "summary": overall,
        "families": family_summary,
        "models": model_serialized,
        "projects": project_serialized,
        "tools": global_tools,
        "timeline": daily_timeline,
        "conversations": sorted(all_merged_convs, key=lambda x: x.get("date", ""), reverse=True),
        "pricing_table": PRICING_TABLE
    }
    
    atomic_write_json(LEDGER_JSON, result)
    atomic_write_json(TOKEN_DATA_JSON, result)
        
    mirror_backups(result)
    return result

def mirror_backups(data):
    try:
        os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)
        local_target = os.path.join(BACKUP_DIR_LOCAL, "ledger_backup.json")
        atomic_write_json(local_target, data)
    except Exception:
        pass

    icloud_parent = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
    if os.path.exists(icloud_parent):
        try:
            os.makedirs(ICLOUD_BACKUP_DIR, exist_ok=True)
            icloud_target = os.path.join(ICLOUD_BACKUP_DIR, "antigravity_token_ledger_backup.json")
            atomic_write_json(icloud_target, data)
        except Exception:
            pass

def export_csv_file(data: dict, target_file_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(target_file_path)), exist_ok=True)
    with open(target_file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Date", "Conversation_ID", "Workspace_Project", "Primary_Model",
            "Invocations", "Fresh_Input_Tokens", "Cached_Context_Tokens",
            "Output_Tokens", "Thinking_Tokens", "Tool_Tokens", "Total_Tokens",
            "Standard_Cost_USD", "Prompt_Cached_Cost_USD", "Cache_Savings_USD", "Status", "Anomalies"
        ])
        for c in data.get("conversations", []):
            uncached = c.get("cost_uncached_usd", 0.0)
            cached = c.get("cost_cached_usd", 0.0)
            savings = round(uncached - cached, 2)
            anom_str = "; ".join(c.get("anomalies", []))
            writer.writerow([
                safe_csv_cell(c.get("date", "Unknown")),
                safe_csv_cell(c.get("id", "")),
                safe_csv_cell(c.get("project", "General")),
                safe_csv_cell(c.get("primary_model", "")),
                c.get("invocations", 0),
                c.get("fresh_input_tokens", 0),
                c.get("cached_context_tokens", 0),
                c.get("output_tokens", 0),
                c.get("thinking_tokens", 0),
                c.get("tool_call_tokens", 0),
                c.get("total_tokens", 0),
                f"{uncached:.2f}",
                f"{cached:.2f}",
                f"{savings:.2f}",
                "Active" if c.get("is_active", 1) else "Archived",
                safe_csv_cell(anom_str)
            ])
    print(f"✅ Full token ledger CSV exported to: {target_file_path}")

def export_backup_file(target_file_path):
    data = merge_ledger_and_live()
    os.makedirs(os.path.dirname(os.path.abspath(target_file_path)), exist_ok=True)
    with open(target_file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Full token ledger JSON backup exported to: {target_file_path}")

def import_backup_file(backup_file_path, db_path=DB_PATH):
    if not os.path.exists(backup_file_path):
        print(f"❌ File not found: {backup_file_path}", file=sys.stderr)
        return False
    with open(backup_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    convs = data.get("conversations", [])
    if not convs:
        print("❌ Invalid backup file: no conversations found.", file=sys.stderr)
        return False
    save_conversations_to_ledger(convs, db_path)
    print(f"✅ Successfully restored {len(convs)} conversations into persistent ledger!")
    return True

def print_cli_report(data):
    s = data["summary"]
    b = data.get("budget", {})
    print("\n" + "=" * 76)
    print(" 🚀 ANTIGRAVITY IDE — ENTERPRISE AI TOKEN & COST GOVERNANCE")
    print("=" * 76)
    print(f" 📂 Conversations In Ledger   : {s['total_conversations']} ({s.get('active_conversations', s['total_conversations'])} active, {s.get('archived_conversations', 0)} preserved)")
    print(f" ⚡ Total Model Invocations   : {s['total_invocations']:,}")
    print(f" 🪙 Total Cumulative Tokens   : {s['total_cumulative_tokens']:,}")
    print(f"    ├─ Fresh Input (New)      : {s['fresh_input_tokens']:,}")
    print(f"    ├─ Prompt Cache / Context : {s['cached_context_tokens']:,} (Hit Ratio: {s['cache_hit_ratio_pct']}%)")
    print(f"    ├─ Generated Output       : {s['output_tokens']:,}")
    print(f"    ├─ Reasoning / Thinking   : {s['thinking_tokens']:,}")
    print(f"    └─ Tool Arguments         : {s['tool_call_tokens']:,}")
    print(f" 📄 Unique Stored Content     : {s['unique_content_tokens']:,} tokens")
    print("-" * 76)
    print(f" 💵 COMMERCIAL COST (STANDARD) : ${s['cost_uncached_usd']:,.2f} USD")
    print(f" 🏷️  COMMERCIAL COST (CACHED)   : ${s['cost_cached_usd']:,.2f} USD (Prompt Cache Savings: ${s['cache_savings_usd']:,.2f})")
    print("-" * 76)
    print(f" 🎯 BUDGET & SPEND PACING     : ${b.get('today_cost_cached', 0):.2f} / ${b.get('daily_target_usd', 5):.2f} today ({b.get('today_percent_used', 0)}% consumed)")
    print(f"    ├─ Month-To-Date Spend    : ${b.get('month_cost_cached', 0):.2f} / ${b.get('monthly_target_usd', 50):.2f} ({b.get('month_percent_used', 0)}%)")
    print(f"    └─ Projected Month Cost   : ${b.get('projected_month_cost', 0):.2f} USD (Status: {b.get('status', 'normal').upper()})")
    print("=" * 76)
    
    print("\n🏢 PROVIDER BREAKDOWN:")
    print("-" * 76)
    for fam, f_data in data["families"].items():
        pct = (f_data["tokens"] / s["total_cumulative_tokens"] * 100) if s["total_cumulative_tokens"] else 0
        print(f" {fam:12s} : {f_data['tokens']:14,d} tok ({pct:5.1f}%) | ${f_data['cost_uncached']:9.2f} (Standard) | ${f_data['cost_cached']:9.2f} (Cached)")
        
    print("\n🤖 TOP CONSUMED MODELS:")
    print("-" * 76)
    sorted_models = sorted(data["models"].items(), key=lambda x: x[1]["total_tokens"], reverse=True)
    for m_name, m in sorted_models[:8]:
        print(f" {m_name:30s} : {m['total_tokens']:12,d} tok | Out: {m['output_tokens']:8,d} | Thk: {m['thinking_tokens']:7,d} | ${m['cost_uncached_usd']:8.2f}")

    print("\n📁 TOP WORKSPACES:")
    print("-" * 76)
    sorted_projects = sorted(data["projects"].items(), key=lambda x: x[1]["tokens"], reverse=True)
    for p_name, p in sorted_projects[:8]:
        print(f" {p_name:25s} : {p['tokens']:12,d} tok | ${p['cost_uncached_usd']:8.2f} ({p['conversations']} chats, {p['invocations']:,} calls)")
    print("=" * 76 + "\n")

# Complete Enterprise Dashboard HTML Template
def get_dashboard_template() -> str:
    """Load the canonical dashboard HTML template from disk."""
    candidates = [
        os.path.join(BASE_DIR, "extension", "dashboard.html"),
        os.path.join(BASE_DIR, "dashboard.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "extension", "dashboard.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError("Canonical dashboard template (dashboard.html) not found.")

class _TemplateProxy:
    """Proxy object preserving backward compatibility for ENTERPRISE_HTML_TEMPLATE access."""
    def __str__(self):
        return get_dashboard_template()
    def __repr__(self):
        return repr(get_dashboard_template())
    def splitlines(self, *args, **kwargs):
        return get_dashboard_template().splitlines(*args, **kwargs)
    def replace(self, *args, **kwargs):
        return get_dashboard_template().replace(*args, **kwargs)
    def __contains__(self, item):
        return item in get_dashboard_template()

ENTERPRISE_HTML_TEMPLATE = _TemplateProxy()

def get_logo_base64():
    candidates = [
        os.path.join(BASE_DIR, "icon.png"),
        os.path.join(BASE_DIR, "logo_256.png"),
        os.path.join(BASE_DIR, "logo.png"),
        os.path.join(BASE_DIR, "extension", "icon.png"),
        os.path.join(BASE_DIR, "extension", "logo_256.png"),
        os.path.join(BASE_DIR, "extension", "logo.png"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                import base64
                with open(p, "rb") as f:
                    return "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
    return ""

def generate_dashboard_html(data, out_dir=None):
    if out_dir is None:
        out_dir = DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, "dashboard.html")
    template = get_dashboard_template()
    nonce = secrets.token_urlsafe(24)
    data_json = json.dumps(data).replace('</', '<\/')
    logo_b64 = get_logo_base64()
    html_content = template.replace("__DATA_PLACEHOLDER__", data_json)
    html_content = html_content.replace("__LOGO_PLACEHOLDER__", logo_b64)
    html_content = html_content.replace("__NONCE__", nonce)
    tmp_path = html_path + f".tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    try:
        os.chmod(tmp_path, 0o644)
    except:
        pass
    os.replace(tmp_path, html_path)
    return html_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quota — Enterprise AI Token & Cost Intelligence")
    parser.add_argument("--data-dir", metavar="DIR", help="Custom persistent ledger directory")
    parser.add_argument("--json", action="store_true", help="Output JSON metrics")
    parser.add_argument("--export-csv", metavar="FILE", help="Export full conversation ledger to CSV")
    parser.add_argument("--set-budget", nargs=2, type=float, metavar=("DAILY", "MONTHLY"), help="Set budget guardrails in USD")
    parser.add_argument("--export-backup", metavar="FILE", help="Export full ledger backup to JSON")
    parser.add_argument("--import-backup", metavar="FILE", help="Restore ledger from JSON backup")
    parser.add_argument("--simulate-wipe", action="store_true", help="Simulate ~/.gemini deletion (tests disaster persistence)")
    parser.add_argument("--rebuild", action="store_true", help="Force recalculate and rebuild ledger from raw transcripts")
    args = parser.parse_args()
    if args.data_dir:
        set_active_data_dir(args.data_dir)
        ensure_data_migration()

    if args.set_budget:
        daily, monthly = args.set_budget
        import math
        if not math.isfinite(daily) or daily < 0.10:
            print("❌ Error: Daily budget must be a finite number >= 0.10", file=sys.stderr)
            sys.exit(1)
        if not math.isfinite(monthly) or monthly < 1.00:
            print("❌ Error: Monthly budget must be a finite number >= 1.00", file=sys.stderr)
            sys.exit(1)
        save_budget(daily, monthly)
        print(f"✅ Budget guardrails updated: ${daily:.2f}/day, ${monthly:.2f}/month")
        sys.exit(0)

    if args.export_backup:
        export_backup_file(args.export_backup)
        sys.exit(0)

    if args.import_backup:
        success = import_backup_file(args.import_backup)
        sys.exit(0 if success else 1)

    brain_to_use = BRAIN_DIR
    if args.simulate_wipe:
        brain_to_use = "/tmp/mock_empty_brain_non_existent"
        print("⚠️  SIMULATION: Testing 100% disaster recovery with deleted ~/.gemini directory...")

    results = merge_ledger_and_live(brain_path=brain_to_use, rebuild=args.rebuild)
    dash_path = generate_dashboard_html(results, DATA_DIR)

    if args.export_csv:
        export_csv_file(results, args.export_csv)
        sys.exit(0)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_cli_report(results)
        print(f"🛡️  Persistent SQLite Ledger: {DB_PATH}")
        print(f"🔒 Local Backup Snapshot    : {LEDGER_JSON}")
        if os.path.exists(BACKUP_DIR_LOCAL):
            print(f"📁 Redundant Backup Mirror : {os.path.join(BACKUP_DIR_LOCAL, 'ledger_backup.json')}")
        if os.path.exists(ICLOUD_BACKUP_DIR):
            print(f"☁️  iCloud Backup Mirror    : {os.path.join(ICLOUD_BACKUP_DIR, 'antigravity_token_ledger_backup.json')}")
        print(f"📊 Interactive Dashboard   : {dash_path}")

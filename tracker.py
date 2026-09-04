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
import sqlite3
import argparse
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.environ.get("QUOTA_DATA_DIR") or os.path.expanduser("~/.config/quota")
DATA_DIR = DEFAULT_DATA_DIR
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-ide/brain")
DB_PATH = os.path.join(DATA_DIR, "persistent_ledger.sqlite")
LEDGER_JSON = os.path.join(DATA_DIR, "persistent_ledger.json")
TOKEN_DATA_JSON = os.path.join(DATA_DIR, "token_data.json")
BACKUP_DIR_LOCAL = os.path.expanduser("~/.config/quota/backups")
BUDGET_FILE = os.path.join(DATA_DIR, "budget_config.json")
ICLOUD_BACKUP_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AntigravityTokenBackups")

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
    "Gemini 3.1 Pro (High)": {
        "family": "Google",
        "input_uncached": 1.25,
        "input_cached_read": 0.3125,
        "output": 5.00,
        "thinking": 5.00,
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

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))

def get_pricing(model_name: str) -> dict:
    if model_name in PRICING_TABLE:
        return PRICING_TABLE[model_name]
    for k in PRICING_TABLE:
        if k in model_name:
            return PRICING_TABLE[k]
    return PRICING_TABLE["Default"]

def clean_project_name(path_or_str: str) -> str:
    if not path_or_str:
        return "General"
    path_or_str = path_or_str.strip().rstrip('/')
    parts = path_or_str.split('/')
    home_user = os.path.basename(os.path.expanduser('~'))
    ignored = {'.gemini', '.vscode', '.local', 'Library', 'Applications', 'Users', 'home', home_user, 'tempmediaStorage'}
    filtered = [p for p in parts if p and p not in ignored]
    if not filtered:
        return "General"
    if filtered[0] == 'Downloads' and len(filtered) > 1:
        return filtered[1]
    return filtered[0]

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
    os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)
    d = {"daily_usd": float(daily), "monthly_usd": float(monthly)}
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
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
        anomaly_json TEXT DEFAULT '[]'
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
        
    cur.execute('''CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

def load_ledger_from_db(db_path=DB_PATH) -> dict:
    if not os.path.exists(db_path):
        init_database(db_path)
    conn = get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
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
            
        conv["id"] = conv["conv_id"]
        conv["short_id"] = conv["conv_id"][:8]
        ledger[conv["conv_id"]] = conv
    conn.close()
    return ledger

def save_conversations_to_ledger(conversations_list, db_path=DB_PATH):
    init_database(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    
    for c in conversations_list:
        models_json = json.dumps(c.get("models") or [c.get("primary_model")])
        tools_json = json.dumps(c.get("tools") or {})
        trace_json = json.dumps(c.get("trace") or [])
        anomaly_json = json.dumps(c.get("anomalies") or [])
        
        cur.execute('''INSERT INTO conversations_ledger (
            conv_id, date, project, primary_model, models_json,
            fresh_input_tokens, cached_context_tokens, output_tokens, thinking_tokens, tool_call_tokens,
            total_tokens, cost_uncached_usd, cost_cached_usd, invocations,
            first_seen_at, last_updated_at, is_active, tools_json, trace_json, anomaly_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(conv_id) DO UPDATE SET
            date = excluded.date,
            project = excluded.project,
            primary_model = excluded.primary_model,
            models_json = excluded.models_json,
            fresh_input_tokens = MAX(conversations_ledger.fresh_input_tokens, excluded.fresh_input_tokens),
            cached_context_tokens = MAX(conversations_ledger.cached_context_tokens, excluded.cached_context_tokens),
            output_tokens = MAX(conversations_ledger.output_tokens, excluded.output_tokens),
            thinking_tokens = MAX(conversations_ledger.thinking_tokens, excluded.thinking_tokens),
            tool_call_tokens = MAX(conversations_ledger.tool_call_tokens, excluded.tool_call_tokens),
            total_tokens = MAX(conversations_ledger.total_tokens, excluded.total_tokens),
            cost_uncached_usd = MAX(conversations_ledger.cost_uncached_usd, excluded.cost_uncached_usd),
            cost_cached_usd = MAX(conversations_ledger.cost_cached_usd, excluded.cost_cached_usd),
            invocations = MAX(conversations_ledger.invocations, excluded.invocations),
            last_updated_at = excluded.last_updated_at,
            is_active = excluded.is_active,
            tools_json = excluded.tools_json,
            trace_json = excluded.trace_json,
            anomaly_json = excluded.anomaly_json
        ''', (
            c["id"], c["date"], c["project"], c["primary_model"], models_json,
            c["fresh_input_tokens"], c["cached_context_tokens"], c["output_tokens"], c["thinking_tokens"], c["tool_call_tokens"],
            c["total_tokens"], c["cost_uncached_usd"], c["cost_cached_usd"], c["invocations"],
            now_str, now_str, c.get("is_active", 1), tools_json, trace_json, anomaly_json
        ))
    
    cur.execute('''INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_sync', ?)''', (now_str,))
    conn.commit()
    conn.close()

def scan_live_brain(brain_path=BRAIN_DIR) -> tuple:
    if not os.path.exists(brain_path):
        return [], {}

    full_pattern = os.path.join(brain_path, "*", ".system_generated", "logs", "transcript_full.jsonl")
    fallback_pattern = os.path.join(brain_path, "*", ".system_generated", "logs", "transcript.jsonl")
    
    files = glob.glob(full_pattern)
    if not files:
        files = glob.glob(fallback_pattern)
        
    model_regex = re.compile(
        r"The user changed setting `Model Selection` from ([^`]+?) to ([^`]+?)\.\s*No need to comment",
        re.IGNORECASE
    )
    workspace_regex = re.compile(r"\[URI\] -> \[CorpusName\]:\s*\n([^\n]+)", re.MULTILINE)
    home_user_esc = re.escape(os.path.basename(os.path.expanduser("~")))
    path_regex = re.compile(rf"/(?:Users|home)/{home_user_esc}/([a-zA-Z0-9_\-\.]+)(?:/([a-zA-Z0-9_\-\.]+))?")
    
    scanned_convs = []
    global_tool_metrics = defaultdict(lambda: {"invocations": 0, "argument_tokens": 0})

    for file_path in sorted(files):
        conv_id = file_path.split(os.sep)[-4]
        current_model = "Gemini 3.6 Flash (High)"
        detected_project = None
        created_date = None
        
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

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        step = json.loads(line_str)
                    except:
                        continue
                    
                    stype = step.get("type", "")
                    content = step.get("content") or ""
                    thinking = step.get("thinking") or ""
                    tool_calls = step.get("tool_calls") or []
                    created_at = step.get("created_at")
                    
                    if created_at and not created_date:
                        created_date = created_at[:10]
                    
                    if "Model Selection" in content:
                        for m_from, m_to in model_regex.findall(content):
                            m_to = m_to.strip()
                            if m_to and m_to != "None":
                                current_model = m_to
                    
                    models_in_conv.add(current_model)
                    pricing = get_pricing(current_model)
                    
                    if not detected_project:
                        w_match = workspace_regex.search(content)
                        if w_match:
                            detected_project = clean_project_name(w_match.group(1))
                        else:
                            for p1, p2 in path_regex.findall(content):
                                if p1 not in ('.gemini', '.vscode', '.local', 'Library', 'Applications'):
                                    detected_project = p2 if p1 == 'Downloads' and p2 else p1
                                    break
                    
                    # Track tools
                    step_tools = []
                    tool_tok = 0
                    if tool_calls:
                        tool_tok = estimate_tokens(json.dumps(tool_calls))
                        for tc in tool_calls:
                            t_name = tc.get("name") or tc.get("function", {}).get("name") or "tool"
                            conv_tools_count[t_name] += 1
                            step_tools.append(t_name)
                            global_tool_metrics[t_name]["invocations"] += 1
                            global_tool_metrics[t_name]["argument_tokens"] += int(tool_tok / len(tool_calls))

                    if stype == "PLANNER_RESPONSE":
                        conv_invocations += 1
                        out_tok = estimate_tokens(content)
                        total_step_out = out_tok + tool_tok
                        thk_tok = estimate_tokens(thinking)
                        
                        step_fresh_in = fresh_turn_input_tokens
                        step_cached_in = accumulated_history_tokens
                        step_total_in = step_fresh_in + step_cached_in
                        
                        cost_step_uncached = (
                            (step_total_in / 1_000_000.0) * pricing["input_uncached"] +
                            (total_step_out / 1_000_000.0) * pricing["output"] +
                            (thk_tok / 1_000_000.0) * pricing["thinking"]
                        )
                        
                        cost_step_cached = (
                            (step_fresh_in / 1_000_000.0) * pricing["input_uncached"] +
                            (step_cached_in / 1_000_000.0) * pricing["input_cached_read"] +
                            (total_step_out / 1_000_000.0) * pricing["output"] +
                            (thk_tok / 1_000_000.0) * pricing["thinking"]
                        )
                        
                        conv_fresh_in += step_fresh_in
                        conv_cached_in += step_cached_in
                        conv_out += total_step_out
                        conv_thinking += thk_tok
                        conv_tools += tool_tok
                        conv_cost_uncached += cost_step_uncached
                        conv_cost_cached += cost_step_cached
                        
                        raw_steps_profile.append({
                            "turn": conv_invocations,
                            "context": accumulated_history_tokens,
                            "out": total_step_out,
                            "thk": thk_tok,
                            "tools": step_tools,
                            "cost": round(cost_step_cached, 4)
                        })

                        accumulated_history_tokens += (step_fresh_in + total_step_out + thk_tok)
                        fresh_turn_input_tokens = 0
                    else:
                        step_tokens = estimate_tokens(content)
                        fresh_turn_input_tokens += step_tokens
        except Exception:
            continue
        
        project_name = detected_project or "General"
        conv_total_tokens = conv_fresh_in + conv_cached_in + conv_out + conv_thinking
        
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
        anomalies = []
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
            "date": created_date or "Unknown",
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

def merge_ledger_and_live(brain_path=BRAIN_DIR, db_path=DB_PATH) -> dict:
    existing_ledger = load_ledger_from_db(db_path)
    live_convs, global_tools = scan_live_brain(brain_path)
    live_map = {c["id"]: c for c in live_convs}
    
    for conv_id, live_c in live_map.items():
        if conv_id in existing_ledger:
            past = existing_ledger[conv_id]
            if live_c["total_tokens"] >= past.get("total_tokens", 0):
                existing_ledger[conv_id] = live_c
            existing_ledger[conv_id]["is_active"] = 1
        else:
            existing_ledger[conv_id] = live_c
            existing_ledger[conv_id]["is_active"] = 1

    for conv_id, past in existing_ledger.items():
        if conv_id not in live_map:
            past["is_active"] = 0

    all_merged_convs = list(existing_ledger.values())
    save_conversations_to_ledger(all_merged_convs, db_path)
    
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
    overall["unique_content_tokens"] = overall["fresh_input_tokens"] + overall["output_tokens"] + overall["thinking_tokens"]
    
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

    family_summary = {
        "Google": {"tokens": 0, "cost_uncached": 0.0, "cost_cached": 0.0, "invocations": 0},
        "Anthropic": {"tokens": 0, "cost_uncached": 0.0, "cost_cached": 0.0, "invocations": 0}
    }

    for c in all_merged_convs:
        p_name = c.get("project", "General")
        m_name = c.get("primary_model", "Gemini 3.6 Flash (High)")
        fam = get_pricing(m_name)["family"]
        
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
        
        if fam in family_summary:
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

    for fam in family_summary:
        family_summary[fam]["cost_uncached"] = round(family_summary[fam]["cost_uncached"], 2)
        family_summary[fam]["cost_cached"] = round(family_summary[fam]["cost_cached"], 2)

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
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    month_prefix = datetime.utcnow().strftime("%Y-%m")
    
    today_data = daily_stats.get(today_str, {"cost_cached_usd": 0.0, "cost_uncached_usd": 0.0, "tokens": 0})
    today_cost = round(today_data["cost_cached_usd"], 2)
    today_uncached = round(today_data["cost_uncached_usd"], 2)
    
    month_cost = round(sum(v["cost_cached_usd"] for d, v in daily_stats.items() if d.startswith(month_prefix)), 2)
    day_of_month = max(1, datetime.utcnow().day)
    projected_month = round((month_cost / day_of_month) * 30, 2)
    
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
    if os.path.exists(brain_path):
        for entry in os.scandir(brain_path):
            if entry.is_dir() and entry.name != 'tempmediaStorage':
                tf = os.path.join(entry.path, ".system_generated", "logs", "transcript.jsonl")
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
    
    with open(LEDGER_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    try:
        os.chmod(LEDGER_JSON, 0o600)
    except:
        pass
        
    mirror_backups(result)
    return result

def mirror_backups(data):
    try:
        os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)
        local_target = os.path.join(BACKUP_DIR_LOCAL, "ledger_backup.json")
        with open(local_target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.chmod(local_target, 0o600)
    except Exception:
        pass

    icloud_parent = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
    if os.path.exists(icloud_parent):
        try:
            os.makedirs(ICLOUD_BACKUP_DIR, exist_ok=True)
            icloud_target = os.path.join(ICLOUD_BACKUP_DIR, "antigravity_token_ledger_backup.json")
            with open(icloud_target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
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
                c.get("date", "Unknown"),
                c.get("id", ""),
                c.get("project", "General"),
                c.get("primary_model", ""),
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
                anom_str
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
ENTERPRISE_HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: https: vscode-resource:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data: https:;">
  <title>Quota</title>
  <style>
    :root {
      --bg: #09090b;
      --card-bg: #121316;
      --card-surface: #18191f;
      --border: #222329;
      --border-hover: #32343d;
      --border-subtle: rgba(255, 255, 255, 0.05);
      
      --text-primary: #f4f4f5;
      --text-secondary: #a1a1aa;
      --text-tertiary: #71717a;
      
      --accent-blue: #3b82f6;
      --accent-blue-subtle: rgba(59, 130, 246, 0.12);
      --accent-purple: #8b5cf6;
      --accent-purple-subtle: rgba(139, 92, 246, 0.12);
      --accent-emerald: #10b981;
      --accent-emerald-subtle: rgba(16, 185, 129, 0.12);
      --accent-amber: #f59e0b;
      --accent-amber-subtle: rgba(245, 158, 11, 0.12);
      --accent-rose: #f43f5e;
      --accent-rose-subtle: rgba(244, 63, 94, 0.12);
      
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
      line-height: 1.5;
      padding: 24px 32px;
      -webkit-font-smoothing: antialiased;
    }

    .container { max-width: 1400px; margin: 0 auto; }

    /* Top Navigation Header */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    .brand-section { display: flex; align-items: center; gap: 14px; }
    .brand-logo-img {
      width: 44px;
      height: 44px;
      border-radius: 11px;
      object-fit: cover;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
      display: block;
    }
    .brand-title {
      font-size: 25px; /* Increased 20%+ from 20px */
      font-weight: 750;
      letter-spacing: -0.03em;
      color: var(--text-primary);
    }
    .brand-icon svg { width: 20px; height: 20px; fill: white; }
    .brand-titles h1 { font-size: 18px; font-weight: 650; letter-spacing: -0.02em; color: var(--text-primary); }
    .breadcrumb { font-size: 12px; color: var(--text-tertiary); display: flex; gap: 6px; align-items: center; }

    .header-actions { display: flex; align-items: center; gap: 10px; }
    .sync-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      color: #34d399;
      background: var(--accent-emerald-subtle);
      border: 1px solid rgba(16, 185, 129, 0.2);
      padding: 5px 10px;
      border-radius: 9999px;
      font-weight: 500;
    }
    .pulse-dot { width: 6px; height: 6px; border-radius: 50%; background-color: #34d399; animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }

    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 6px 12px;
      border-radius: 7px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .btn:hover { background: var(--card-surface); border-color: var(--border-hover); }
    .btn-primary { background: #2563eb; border-color: #3b82f6; color: white; }
    .btn-primary:hover { background: #1d4ed8; }

    /* KPI Metrics Hero Strip */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .metric-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px 20px;
      position: relative;
      transition: border-color 0.15s;
    }
    .metric-card:hover { border-color: var(--border-hover); }
    .metric-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .metric-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); }
    .metric-value { font-size: 28px; font-weight: 700; letter-spacing: -0.03em; color: var(--text-primary); font-variant-numeric: tabular-nums; }
    .metric-sub { font-size: 11px; color: var(--text-secondary); margin-top: 6px; display: flex; align-items: center; gap: 6px; }

    .badge-pill {
      font-size: 10px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 9999px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .badge-green { background: var(--accent-emerald-subtle); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
    .badge-blue { background: var(--accent-blue-subtle); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.2); }
    .badge-amber { background: var(--accent-amber-subtle); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.2); }
    .badge-rose { background: var(--accent-rose-subtle); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.2); }

    /* Interactive Timeline Section */
    .timeline-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 24px;
    }
    .timeline-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .timeline-title { font-size: 13px; font-weight: 650; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
    .toggle-group {
      display: inline-flex;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 7px;
      padding: 2px;
      gap: 2px;
    }
    .toggle-btn {
      background: transparent;
      border: none;
      color: var(--text-tertiary);
      font-size: 11px;
      font-weight: 500;
      padding: 4px 10px;
      border-radius: 5px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .toggle-btn.active {
      background: var(--card-surface);
      color: var(--text-primary);
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }

    .chart-container {
      width: 100%;
      height: 170px;
      position: relative;
    }
    .chart-svg {
      width: 100%;
      height: 100%;
      overflow: visible;
    }
    .bar-rect {
      transition: opacity 0.15s, fill 0.15s;
      cursor: pointer;
    }
    .bar-rect:hover { opacity: 0.85; filter: drop-shadow(0 0 6px rgba(59, 130, 246, 0.4)); }

    /* Floating Tooltip */
    #chart-tooltip {
      position: absolute;
      display: none;
      background: #1e1f26;
      border: 1px solid #32343d;
      border-radius: 7px;
      padding: 8px 12px;
      font-size: 11px;
      color: var(--text-primary);
      box-shadow: 0 6px 20px rgba(0,0,0,0.5);
      pointer-events: none;
      z-index: 100;
      transform: translate(-50%, -120%);
    }

    /* Tabbed Navigation */
    .tabs-nav {
      display: flex;
      gap: 4px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-tertiary);
      font-size: 12px;
      font-weight: 500;
      padding: 8px 14px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: color 0.15s, border-color 0.15s;
    }
    .tab-btn:hover { color: var(--text-secondary); }
    .tab-btn.active { color: var(--text-primary); border-bottom-color: var(--accent-blue); font-weight: 600; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* Segmented Progress Bar */
    .segmented-bar-container {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 24px;
    }
    .segmented-bar-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .segmented-bar-title h3 { font-size: 13px; font-weight: 650; }
    .segmented-bar-track {
      display: flex;
      height: 12px;
      border-radius: 6px;
      overflow: hidden;
      background: #1a1b22;
      margin-bottom: 16px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .segment-fill { height: 100%; transition: width 0.3s ease; }
    .seg-cache { background: linear-gradient(90deg, #7c3aed, #a855f7); }
    .seg-fresh { background: #3b82f6; }
    .seg-output { background: #10b981; }
    .seg-thinking { background: #f43f5e; }
    .seg-tools { background: #f59e0b; }

    .segment-legend-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 12px;
    }
    .legend-item {
      background: var(--card-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px;
    }
    .legend-top { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); margin-bottom: 4px; }
    .legend-dot { width: 8px; height: 8px; border-radius: 50%; }
    .legend-val { font-size: 16px; font-weight: 700; font-variant-numeric: tabular-nums; }
    .legend-desc { font-size: 10px; color: var(--text-tertiary); margin-top: 2px; }

    /* Dual Grid Panels */
    .dual-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }
    .panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
    }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .panel-title { font-size: 13px; font-weight: 650; }

    /* Workspaces List */
    .dense-list { display: flex; flex-direction: column; gap: 10px; }
    .dense-item {
      background: var(--card-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px 14px;
    }
    .dense-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .dense-name { font-weight: 600; font-size: 12px; }
    .dense-val { font-family: var(--font-mono); font-size: 12px; color: var(--text-primary); }
    .dense-track { height: 4px; border-radius: 2px; background: #262730; overflow: hidden; }
    .dense-fill { height: 100%; border-radius: 2px; background: #3b82f6; }

    /* Tables */
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }
    .table-controls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-box {
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      width: 240px;
      outline: none;
    }
    .search-box:focus { border-color: var(--accent-blue); }
    .filter-select {
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text-secondary);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
      outline: none;
    }

    table { width: 100%; border-collapse: collapse; text-align: left; }
    th {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 10px 16px;
      border-bottom: 1px solid var(--border);
      background: rgba(0,0,0,0.15);
    }
    td {
      font-size: 12px;
      padding: 10px 16px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-secondary);
    }
    tr.clickable-row { cursor: pointer; transition: background 0.15s; }
    tr.clickable-row:hover { background: rgba(255,255,255,0.03); }
    .mono { font-family: var(--font-mono); font-size: 11px; }

    /* Slide-Over Detail Drawer */
    .drawer-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(3px);
      z-index: 200;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.25s ease;
    }
    .drawer-overlay.open { opacity: 1; pointer-events: auto; }

    .trace-drawer {
      position: fixed;
      top: 0; right: 0; bottom: 0;
      width: 620px;
      max-width: 90vw;
      background: #111216;
      border-left: 1px solid var(--border);
      box-shadow: -10px 0 30px rgba(0, 0, 0, 0.7);
      z-index: 201;
      transform: translateX(100%);
      transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .trace-drawer.open { transform: translateX(0); }

    .drawer-header {
      padding: 18px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #14161c;
    }
    .drawer-header h2 { font-size: 15px; font-weight: 650; }
    .drawer-close-btn {
      background: transparent;
      border: none;
      color: var(--text-tertiary);
      font-size: 18px;
      cursor: pointer;
      padding: 4px;
    }
    .drawer-close-btn:hover { color: var(--text-primary); }

    .drawer-body {
      padding: 24px;
      overflow-y: auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .drawer-section-title {
      font-size: 11px;
      font-weight: 650;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-tertiary);
      margin-bottom: 10px;
    }

    .curve-container {
      background: var(--card-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 16px;
      height: 150px;
      position: relative;
    }

    .tool-pills { display: flex; flex-wrap: wrap; gap: 6px; }
    .tool-pill {
      background: #1e1f28;
      border: 1px solid #2e303d;
      padding: 4px 9px;
      border-radius: 6px;
      font-size: 11px;
      font-family: var(--font-mono);
      color: #93c5fd;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .tool-pill span { color: #f4f4f5; font-weight: 600; }

    /* Modal for Budget Config */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.7);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 300;
    }
    .modal-overlay.open { display: flex; }
    .modal-card {
      background: #14161c;
      border: 1px solid var(--border);
      border-radius: 12px;
      width: 400px;
      padding: 24px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.8);
    }
    .modal-card h3 { font-size: 15px; margin-bottom: 14px; }
    .form-group { margin-bottom: 16px; }
    .form-group label { display: block; font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; text-transform: uppercase; }
    .form-group input {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 13px;
      outline: none;
    }
    .modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header class="header">
      <div class="brand-section">
        <img src="__LOGO_PLACEHOLDER__" alt="Quota Logo" class="brand-logo-img" />
        <div class="brand-titles">
          <h1 class="brand-title">Quota</h1>
        </div>
      </div>

      <div class="header-actions">
        <button class="btn" onclick="exportLedgerCsv()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Export CSV
        </button>
        <button class="btn" onclick="copyMarkdownSummary()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy Report
        </button>
      </div>
    </header>

    <!-- KPI Metric Cards Strip -->
    <div class="metric-grid">
      <!-- Total Volume -->
      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">Total Processed Volume</span>
          <span class="badge-pill badge-blue" id="kpi-cache-hit">99.9% Cache Hit</span>
        </div>
        <div class="metric-value" id="kpi-volume">6.40B</div>
        <div class="metric-sub">
          <span id="kpi-unique-tok">12.5M unique content</span>
          <span>&bull;</span>
          <span>Multi-turn context</span>
        </div>
      </div>

      <!-- Standard Valuation -->
      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">Standard API Valuation</span>
          <span style="color: var(--text-tertiary);">&#36;</span>
        </div>
        <div class="metric-value" id="kpi-std-cost">&#36;4,394.24</div>
        <div class="metric-sub">Stateless commercial rate equivalent</div>
      </div>

      <!-- Prompt Cached Real Cost -->
      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">Prompt-Cached Cost</span>
          <span class="badge-pill badge-green" id="kpi-savings">-$3,810 (86.7%)</span>
        </div>
        <div class="metric-value" style="color: #60a5fa;" id="kpi-cached-cost">&#36;584.07</div>
        <div class="metric-sub">Automatic context cache discount</div>
      </div>

      <!-- Autonomous Invocations -->
      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">Autonomous Invocations</span>
          <span class="badge-pill badge-blue" id="kpi-sessions-badge">40 Sessions</span>
        </div>
        <div class="metric-value" id="kpi-invocations">10,409</div>
        <div class="metric-sub">
          <span id="kpi-workspaces-count">8 workspaces</span>
          <span>&bull;</span>
          <span id="kpi-turns-per-chat">Avg 260 turns / session</span>
        </div>
      </div>
    </div>

    <!-- Activity & Inference Timeline Card -->
    <div class="timeline-card">
      <div class="timeline-header">
        <div>
          <div class="timeline-title">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            <span>Activity & Inference Timeline</span>
          </div>
          <div class="timeline-summary-stats" id="timeline-summary-stats" style="font-size: 11px; color: var(--text-tertiary); margin-top: 4px;"></div>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <div class="toggle-group" id="range-toggle-group">
            <button id="range-14d" class="toggle-btn" onclick="setTimelineRange('14d')">14D</button>
            <button id="range-30d" class="toggle-btn active" onclick="setTimelineRange('30d')">30D</button>
            <button id="range-all" class="toggle-btn" onclick="setTimelineRange('all')">All History</button>
          </div>
          <div class="toggle-group" id="metric-toggle-group">
            <button id="toggle-cost" class="toggle-btn active" onclick="setTimelineMetric('cost')">Commercial Cost ($)</button>
            <button id="toggle-tokens" class="toggle-btn" onclick="setTimelineMetric('tokens')">Token Volume</button>
            <button id="toggle-invs" class="toggle-btn" onclick="setTimelineMetric('invs')">Invocations</button>
          </div>
        </div>
      </div>
      <div class="chart-container" id="timeline-container" style="height: 220px; position: relative;">
        <svg class="chart-svg" id="timeline-svg" viewBox="0 0 1000 220" preserveAspectRatio="none"></svg>
        <div id="chart-tooltip"></div>
      </div>
    </div>

    <!-- Tabbed Navigation Bar -->
    <nav class="tabs-nav">
      <button class="tab-btn active" data-tab="overview" onclick="switchTab('overview', this)">Overview</button>
      <button class="tab-btn" data-tab="models" onclick="switchTab('models', this)">Model Intelligence & Pricing</button>
      <button class="tab-btn" data-tab="tools" onclick="switchTab('tools', this)">Tool Consumption</button>
      <button class="tab-btn" data-tab="projects" onclick="switchTab('projects', this)">Workspace Allocation</button>
      <button class="tab-btn" data-tab="ledger" onclick="switchTab('ledger', this)">Conversation Ledger</button>
    </nav>

    <!-- Tab 1: Overview Pane -->
    <div id="tab-overview" class="tab-pane active">
      <!-- Segmented Ingestion Bar -->
      <div class="segmented-bar-container">
        <div class="segmented-bar-title">
          <h3>Token Distribution Across Ingestion & Generation Layers</h3>
          <span class="badge-pill badge-green">99.9% Context Hit Ratio</span>
        </div>
        <div class="segmented-bar-track" id="segmented-track"></div>
        <div class="segment-legend-grid" id="segmented-legend"></div>
      </div>

      <!-- Dual Grid: Providers & Workspaces -->
      <div class="dual-grid">
        <!-- Provider Donut -->
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">Provider Share (Google vs Anthropic)</h3>
            <span style="font-size: 11px; color: var(--text-tertiary);">By volume</span>
          </div>
          <div style="display: flex; align-items: center; gap: 24px;">
            <div style="position: relative; width: 110px; height: 110px; flex-shrink: 0;">
              <svg width="110" height="110" viewBox="0 0 36 36">
                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#2563eb" stroke-width="3.6" stroke-dasharray="91.5, 100" />
                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#f59e0b" stroke-width="3.6" stroke-dasharray="8.5, 100" stroke-dashoffset="-91.5" />
              </svg>
              <div style="position: absolute; top:0; left:0; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center;">
                <span style="font-size: 15px; font-weight: 700;">92%</span>
                <span style="font-size: 9px; color: var(--text-tertiary);">Google</span>
              </div>
            </div>
            <div style="flex: 1;" class="dense-list" id="provider-list"></div>
          </div>
        </div>

        <!-- Top Workspaces -->
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">Top Workspaces by Consumption</h3>
            <span style="font-size: 11px; color: var(--text-tertiary);">Cumulative</span>
          </div>
          <div class="dense-list" id="top-projects-list"></div>
        </div>
      </div>
    </div>

    <!-- Tab 2: Models Pane -->
    <div id="tab-models" class="tab-pane">
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Model Name</th>
              <th>Provider</th>
              <th>Total Volume</th>
              <th>Generated Out</th>
              <th>Reasoning</th>
              <th>Tool Args</th>
              <th>Standard Cost</th>
              <th>Prompt-Cached Cost</th>
            </tr>
          </thead>
          <tbody id="models-table-body"></tbody>
        </table>
      </div>
    </div>

    <!-- Tab 3: Tool Consumption Pane -->
    <div id="tab-tools" class="tab-pane">
      <div class="panel" style="margin-bottom: 20px;">
        <h3 class="panel-title" style="margin-bottom: 6px;">Autonomous Agent Tool Execution Profile</h3>
        <p style="font-size: 12px; color: var(--text-secondary);">Breakdown of tokens consumed and invocations made across tool commands (bash commands, file reading, code editing, web search).</p>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Tool Name</th>
              <th>Invocations</th>
              <th>Estimated Tokens</th>
              <th>Share of Tool Usage</th>
            </tr>
          </thead>
          <tbody id="tools-table-body"></tbody>
        </table>
      </div>
    </div>

    <!-- Tab 4: Workspace Allocation Pane -->
    <div id="tab-projects" class="tab-pane">
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Workspace / Project</th>
              <th>Chats</th>
              <th>Invocations</th>
              <th>Total Tokens</th>
              <th>Standard Cost</th>
              <th>Cached Cost</th>
              <th>Primary Models</th>
            </tr>
          </thead>
          <tbody id="projects-table-body"></tbody>
        </table>
      </div>
    </div>

    <!-- Tab 5: Conversation Ledger Pane -->
    <div id="tab-ledger" class="tab-pane">
      <div class="table-container">
        <div class="table-controls">
          <input type="text" id="chat-search" class="search-box" placeholder="Filter by project or ID..." oninput="filterChats()" />
          <select id="chat-model-filter" class="filter-select" onchange="filterChats()"><option value="">All Models</option></select>
          <select id="chat-project-filter" class="filter-select" onchange="filterChats()"><option value="">All Workspaces</option></select>
          <select id="chat-status-filter" class="filter-select" onchange="filterChats()">
            <option value="">All Statuses</option>
            <option value="active">Active Sessions</option>
            <option value="archived">Preserved / Archived</option>
          </select>
        </div>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Workspace</th>
              <th>Primary Model</th>
              <th>Turns</th>
              <th>Context Compounded</th>
              <th>Output</th>
              <th>Reasoning</th>
              <th>Standard Cost</th>
              <th>Cached Cost</th>
              <th>Anomalies / Tags</th>
            </tr>
          </thead>
          <tbody id="chats-table-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Slide-Over Trace Inspector Drawer -->
  <div id="drawer-overlay" class="drawer-overlay" onclick="closeDrawer()"></div>
  <aside id="trace-drawer" class="trace-drawer">
    <div class="drawer-header">
      <div>
        <h2 id="drawer-title">Session Trace Inspector</h2>
        <div style="font-size: 11px; color: var(--text-tertiary); margin-top: 2px;" id="drawer-subtitle">cbea9de5 &bull; Projectss</div>
      </div>
      <button class="drawer-close-btn" onclick="closeDrawer()">&times;</button>
    </div>
    <div class="drawer-body">
      <!-- Section 1: Context Compounding Curve -->
      <div>
        <div class="drawer-section-title">Context Compounding Curve (Tokens / Turn)</div>
        <div class="curve-container">
          <svg id="drawer-curve-svg" style="width: 100%; height: 100%;" viewBox="0 0 500 120" preserveAspectRatio="none"></svg>
        </div>
      </div>

      <!-- Section 2: Token Anatomy Cards -->
      <div>
        <div class="drawer-section-title">Token Ingestion & Generation Breakdown</div>
        <div class="segment-legend-grid" style="grid-template-columns: repeat(2, 1fr);" id="drawer-tokens-grid"></div>
      </div>

      <!-- Section 3: Tool Execution Matrix -->
      <div>
        <div class="drawer-section-title">Agent Tools Executed</div>
        <div class="tool-pills" id="drawer-tools-pills"></div>
      </div>

      <!-- Section 4: Turn-by-Turn Stepper Table -->
      <div>
        <div class="drawer-section-title">Turn Progression Timeline</div>
        <div class="table-container" style="max-height: 240px; overflow-y: auto;">
          <table>
            <thead>
              <tr>
                <th>Turn</th>
                <th>Context</th>
                <th>Output</th>
                <th>Tools</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody id="drawer-steps-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  </aside>



  <script>
    let DATA = __DATA_PLACEHOLDER__;

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }
    let activeDrawerConvId = null;
    let currentTab = "overview";
    let timelineMode = 'cost';

    function formatNumber(num) {
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

    // Init Metrics
    function initMetrics() {
      const s = DATA.summary;
      document.getElementById('kpi-volume').innerText = formatNumber(s.total_cumulative_tokens);
      document.getElementById('kpi-cache-hit').innerText = (s.cache_hit_ratio_pct || 99.9) + '% Cache Hit';
      document.getElementById('kpi-unique-tok').innerText = formatNumber(s.unique_content_tokens) + ' unique stored';
      document.getElementById('kpi-std-cost').innerText = formatCurrency(s.cost_uncached_usd);
      document.getElementById('kpi-cached-cost').innerText = formatCurrency(s.cost_cached_usd);
      document.getElementById('kpi-savings').innerText = `-${formatCurrency(s.cache_savings_usd)} (${((s.cache_savings_usd/s.cost_uncached_usd)*100).toFixed(1)}%)`;

      // Card 4: Autonomous Invocations
      document.getElementById('kpi-invocations').innerText = (s.total_invocations || 0).toLocaleString();
      document.getElementById('kpi-sessions-badge').innerText = `${s.total_conversations || 0} Sessions`;
      const numProjects = Object.keys(DATA.projects || {}).length;
      document.getElementById('kpi-workspaces-count').innerText = `${numProjects} workspaces`;
      const avgTurns = s.total_conversations ? Math.round(s.total_invocations / s.total_conversations) : 0;
      document.getElementById('kpi-turns-per-chat').innerText = `Avg ${avgTurns} turns / session`;
    }
    initMetrics();

    // State-of-the-Art Continuous Timeline & Area Curve
    let timelineRange = '30d';
    let timelineMetric = 'cost';

    function setTimelineRange(range) {
      timelineRange = range;
      ['14d', '30d', 'all'].forEach(r => {
        const btn = document.getElementById('range-' + r);
        if (btn) btn.className = 'toggle-btn ' + (r === range ? 'active' : '');
      });
      renderTimeline();
    }

    function setTimelineMetric(metric) {
      timelineMetric = metric;
      document.getElementById('toggle-cost').className = 'toggle-btn ' + (metric === 'cost' ? 'active' : '');
      document.getElementById('toggle-tokens').className = 'toggle-btn ' + (metric === 'tokens' ? 'active' : '');
      document.getElementById('toggle-invs').className = 'toggle-btn ' + (metric === 'invs' ? 'active' : '');
      renderTimeline();
    }

    function getContinuousTimelineData(range) {
      const raw = DATA.timeline || [];
      if (!raw.length) return [];
      
      const map = {};
      raw.forEach(d => { map[d.date] = d; });
      
      if (range === 'all') {
        return raw;
      }
      
      const numDays = range === '14d' ? 14 : 30;
      const latestDateStr = raw[raw.length - 1].date;
      const endDt = new Date(latestDateStr + 'T00:00:00Z');
      
      const result = [];
      for (let i = numDays - 1; i >= 0; i--) {
        const dt = new Date(endDt.getTime() - i * 86400000);
        const dtStr = dt.toISOString().slice(0, 10);
        if (map[dtStr]) {
          result.push(map[dtStr]);
        } else {
          result.push({
            date: dtStr,
            tokens: 0,
            cost_uncached_usd: 0,
            cost_cached_usd: 0,
            invocations: 0,
            fresh_input_tokens: 0,
            cached_context_tokens: 0,
            output_tokens: 0,
            thinking_tokens: 0
          });
        }
      }
      return result;
    }

    function renderTimeline() {
      const svg = document.getElementById('timeline-svg');
      const statsEl = document.getElementById('timeline-summary-stats');
      const data = getContinuousTimelineData(timelineRange);
      if (!data.length) return;

      const W = 1000, H = 220;
      const padLeft = 65, padRight = 30, padTop = 30, padBottom = 35;
      const chartW = W - padLeft - padRight;
      const chartH = H - padTop - padBottom;
      const baselineY = padTop + chartH;

      const values = data.map(d => {
        if (timelineMetric === 'cost') return d.cost_cached_usd || 0;
        if (timelineMetric === 'tokens') return d.tokens || 0;
        return d.invocations || 0;
      });

      const maxVal = Math.max(...values, timelineMetric === 'cost' ? 1.0 : (timelineMetric === 'tokens' ? 100000 : 10));
      const totalPeriod = values.reduce((a, b) => a + b, 0);
      const avgPeriod = totalPeriod / data.length;
      const peakIdx = values.indexOf(Math.max(...values));
      const peakDate = data[peakIdx] ? data[peakIdx].date : '';
      const peakVal = values[peakIdx] || 0;
      const activeDaysCount = data.filter(d => (d.tokens || 0) > 0).length;

      if (statsEl) {
        const totalFmt = timelineMetric === 'cost' ? formatCurrency(totalPeriod) : (timelineMetric === 'tokens' ? formatNumber(totalPeriod) + ' tokens' : totalPeriod.toLocaleString() + ' turns');
        const peakFmt = timelineMetric === 'cost' ? formatCurrency(peakVal) : (timelineMetric === 'tokens' ? formatNumber(peakVal) : peakVal.toLocaleString());
        statsEl.innerHTML = `
          <span>Period Total: <strong style="color:#f4f4f5;">${totalFmt}</strong></span>
          <span style="margin: 0 6px;">&bull;</span>
          <span>Daily Avg: <strong style="color:#a1a1aa;">${timelineMetric === 'cost' ? formatCurrency(avgPeriod) : formatNumber(avgPeriod)}</strong></span>
          <span style="margin: 0 6px;">&bull;</span>
          <span>Peak: <strong style="color:#34d399;">${peakFmt}</strong> on ${peakDate}</span>
          <span style="margin: 0 6px;">&bull;</span>
          <span>Active Days: <strong style="color:#60a5fa;">${activeDaysCount} / ${data.length}</strong></span>
        `;
      }

      const points = [];
      const barWidth = Math.max(8, Math.min(22, (chartW / data.length) * 0.65));

      data.forEach((d, i) => {
        const val = values[i];
        const x = padLeft + (i / (data.length - 1)) * chartW;
        const y = baselineY - ((val / maxVal) * chartH);
        points.push({ x, y, val, d });
      });

      let splinePath = '';
      if (points.length === 1) {
        splinePath = `M ${points[0].x},${points[0].y}`;
      } else {
        splinePath = `M ${points[0].x},${points[0].y}`;
        for (let i = 0; i < points.length - 1; i++) {
          const p0 = i > 0 ? points[i - 1] : points[i];
          const p1 = points[i];
          const p2 = points[i + 1];
          const p3 = i < points.length - 2 ? points[i + 2] : p2;
          const cp1x = p1.x + (p2.x - p0.x) / 6;
          const cp1y = p1.y + (p2.y - p0.y) / 6;
          const cp2x = p2.x - (p3.x - p1.x) / 6;
          const cp2y = p2.y - (p3.y - p1.y) / 6;
          splinePath += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
        }
      }

      const areaPath = splinePath + ` L ${points[points.length - 1].x},${baselineY} L ${points[0].x},${baselineY} Z`;

      const strokeColor = timelineMetric === 'cost' ? '#10b981' : (timelineMetric === 'tokens' ? '#3b82f6' : '#8b5cf6');
      const gradStop1 = timelineMetric === 'cost' ? 'rgba(16, 185, 129, 0.28)' : (timelineMetric === 'tokens' ? 'rgba(59, 130, 246, 0.28)' : 'rgba(139, 92, 246, 0.28)');
      const barColor = timelineMetric === 'cost' ? 'rgba(16, 185, 129, 0.45)' : (timelineMetric === 'tokens' ? 'rgba(59, 130, 246, 0.45)' : 'rgba(139, 92, 246, 0.45)');

      let gridHtml = '';
      const gridTicks = [0, 0.25, 0.5, 0.75, 1.0];
      gridTicks.forEach(tick => {
        const y = baselineY - tick * chartH;
        const tickVal = tick * maxVal;
        const label = timelineMetric === 'cost' ? '$' + Math.round(tickVal) : (timelineMetric === 'tokens' ? formatNumber(tickVal) : Math.round(tickVal).toLocaleString());
        gridHtml += `
          <line x1="${padLeft}" y1="${y}" x2="${padLeft + chartW}" y2="${y}" stroke="#222329" stroke-dasharray="3 3" />
          <text x="${padLeft - 10}" y="${y + 4}" fill="#71717a" font-size="10" text-anchor="end" font-family="var(--font-mono)">${label}</text>
        `;
      });

      let barsHtml = '';
      let hitboxesHtml = '';
      let xLabelsHtml = '';
      const labelInterval = Math.max(1, Math.ceil(data.length / 8));

      points.forEach((p, i) => {
        const barH = baselineY - p.y;
        if (p.val > 0) {
          barsHtml += `
            <rect id="bar-${i}" class="timeline-bar" x="${p.x - barWidth / 2}" y="${p.y}" width="${barWidth}" height="${barH}" rx="3" fill="${barColor}" style="transition: all 0.2s;" />
          `;
        }

        hitboxesHtml += `
          <rect class="hitbox" x="${p.x - (chartW / data.length) / 2}" y="${padTop}" width="${chartW / data.length}" height="${chartH + 10}" fill="transparent" style="cursor: crosshair;"
            onmouseenter="onChartHover(event, ${i})" onmousemove="onChartHover(event, ${i})" onmouseleave="onChartLeave()" />
        `;

        if (i % labelInterval === 0 || i === data.length - 1) {
          const dtStr = p.d.date ? p.d.date.slice(5) : '';
          xLabelsHtml += `
            <text x="${p.x}" y="${baselineY + 18}" fill="#71717a" font-size="10" text-anchor="middle" font-family="var(--font-mono)">${dtStr}</text>
          `;
        }
      });

      svg.innerHTML = `
        <defs>
          <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${gradStop1}" />
            <stop offset="100%" stop-color="rgba(0,0,0,0)" />
          </linearGradient>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        ${gridHtml}
        ${barsHtml}
        <path d="${areaPath}" fill="url(#areaGradient)" />
        <path d="${splinePath}" fill="none" stroke="${strokeColor}" stroke-width="2.5" filter="url(#glow)" />
        ${xLabelsHtml}
        <g id="crosshair-group" style="display: none;">
          <line id="crosshair-line" x1="0" y1="${padTop}" x2="0" y2="${baselineY}" stroke="#52525b" stroke-width="1.5" stroke-dasharray="2 2" />
          <circle id="crosshair-dot" cx="0" cy="0" r="5" fill="${strokeColor}" stroke="#ffffff" stroke-width="2" />
        </g>
        ${hitboxesHtml}
      `;
    }

    function onChartHover(e, idx) {
      const data = getContinuousTimelineData(timelineRange);
      const d = data[idx];
      if (!d) return;

      const container = document.getElementById('timeline-container');
      const tooltip = document.getElementById('chart-tooltip');
      const group = document.getElementById('crosshair-group');
      const line = document.getElementById('crosshair-line');
      const dot = document.getElementById('crosshair-dot');
      const bar = document.getElementById('bar-' + idx);

      const W = 1000, H = 220;
      const padLeft = 65, padRight = 30, padTop = 30, padBottom = 35;
      const chartW = W - padLeft - padRight;
      const chartH = H - padTop - padBottom;
      const baselineY = padTop + chartH;

      const values = data.map(item => {
        if (timelineMetric === 'cost') return item.cost_cached_usd || 0;
        if (timelineMetric === 'tokens') return item.tokens || 0;
        return item.invocations || 0;
      });
      const maxVal = Math.max(...values, timelineMetric === 'cost' ? 1.0 : (timelineMetric === 'tokens' ? 100000 : 10));

      const val = values[idx];
      const x = padLeft + (idx / (data.length - 1)) * chartW;
      const y = baselineY - ((val / maxVal) * chartH);

      if (group && line && dot) {
        group.style.display = 'block';
        line.setAttribute('x1', x);
        line.setAttribute('x2', x);
        dot.setAttribute('cx', x);
        dot.setAttribute('cy', y);
      }

      if (bar) {
        bar.style.opacity = '1';
        bar.style.filter = 'drop-shadow(0 0 8px rgba(59, 130, 246, 0.6))';
      }

      tooltip.innerHTML = `
        <div style="font-weight: 700; color: #f4f4f5; margin-bottom: 4px; font-size: 12px;">${d.date}</div>
        <div style="display:flex; justify-content:space-between; gap:16px; margin-bottom:2px;">
          <span style="color:#a1a1aa;">Commercial Cost:</span>
          <span style="color:#34d399; font-weight:600; font-family:var(--font-mono);">$${(d.cost_cached_usd || 0).toFixed(2)} USD</span>
        </div>
        <div style="display:flex; justify-content:space-between; gap:16px; margin-bottom:2px;">
          <span style="color:#a1a1aa;">Token Volume:</span>
          <span style="color:#60a5fa; font-family:var(--font-mono);">${formatNumber(d.tokens || 0)}</span>
        </div>
        <div style="display:flex; justify-content:space-between; gap:16px; margin-bottom:2px;">
          <span style="color:#a1a1aa;">AI Model Turns:</span>
          <span style="color:#f4f4f5; font-family:var(--font-mono);">${d.invocations || 0}</span>
        </div>
        ${d.fresh_input_tokens ? `
        <div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.08); font-size:10px; color:#71717a;">
          Fresh Ingestion: ${formatNumber(d.fresh_input_tokens)} &bull; Cached: ${formatNumber(d.cached_context_tokens)}
        </div>` : ''}
      `;

      const rect = container.getBoundingClientRect();
      const pctX = x / W;
      const tooltipX = pctX * rect.width;
      const tooltipY = (y / H) * rect.height;

      tooltip.style.left = tooltipX + 'px';
      tooltip.style.top = Math.max(10, tooltipY - 20) + 'px';
      tooltip.style.display = 'block';
    }

    function onChartLeave() {
      const tooltip = document.getElementById('chart-tooltip');
      const group = document.getElementById('crosshair-group');
      if (tooltip) tooltip.style.display = 'none';
      if (group) group.style.display = 'none';
      document.querySelectorAll('.timeline-bar').forEach(b => {
        b.style.opacity = '0.7';
        b.style.filter = 'none';
      });
    }

    renderTimeline();

    // Segmented Ingestion Bar
    function renderSegmentedBar() {
      const s = DATA.summary;
      const total = s.total_cumulative_tokens || 1;
      const pCache = ((s.cached_context_tokens || 0) / total) * 100;
      const pFresh = ((s.fresh_input_tokens || 0) / total) * 100;
      const pOut = ((s.output_tokens || 0) / total) * 100;
      const pThk = ((s.thinking_tokens || 0) / total) * 100;
      const pTools = ((s.tool_call_tokens || 0) / total) * 100;

      document.getElementById('segmented-track').innerHTML = `
        <div class="segment-fill seg-cache" style="width: ${pCache}%;"></div>
        <div class="segment-fill seg-fresh" style="width: ${Math.max(0.5, pFresh)}%;"></div>
        <div class="segment-fill seg-output" style="width: ${Math.max(0.5, pOut)}%;"></div>
        <div class="segment-fill seg-thinking" style="width: ${Math.max(0.5, pThk)}%;"></div>
        <div class="segment-fill seg-tools" style="width: ${Math.max(0.5, pTools)}%;"></div>
      `;

      const items = [
        { label: 'Prompt Cache / Context', color: '#a855f7', val: s.cached_context_tokens, pct: pCache, desc: 'Reused context across agent steps' },
        { label: 'Fresh Prompt Ingestion', color: '#3b82f6', val: s.fresh_input_tokens, pct: pFresh, desc: 'New user requests and file contents' },
        { label: 'Model Completions', color: '#10b981', val: s.output_tokens, pct: pOut, desc: 'Code, analysis, and text outputs' },
        { label: 'Extended Thinking', color: '#f43f5e', val: s.thinking_tokens, pct: pThk, desc: 'Inner chain-of-thought reasoning' },
        { label: 'Tool Arguments', color: '#f59e0b', val: s.tool_call_tokens, pct: pTools, desc: 'Terminal command & search args' },
      ];

      document.getElementById('segmented-legend').innerHTML = items.map(i => `
        <div class="legend-item">
          <div class="legend-top">
            <span class="legend-dot" style="background: ${i.color};"></span>
            <span>${i.label}</span>
          </div>
          <div class="legend-val">${formatNumber(i.val)} <span style="font-size: 11px; color: var(--text-tertiary);">(${i.pct.toFixed(2)}%)</span></div>
          <div class="legend-desc">${i.desc}</div>
        </div>
      `).join('');
    }
    renderSegmentedBar();

    // Provider & Workspace Lists
    function renderOverviewLists() {
      const pList = document.getElementById('provider-list');
      pList.innerHTML = Object.entries(DATA.families || {}).map(([fam, d]) => `
        <div class="dense-item">
          <div class="dense-top">
            <span class="dense-name" style="display:flex; align-items:center; gap:6px;">
              <span class="legend-dot" style="background: ${fam === 'Google' ? '#3b82f6' : '#f59e0b'};"></span>
              ${fam === 'Google' ? 'Google Gemini' : 'Anthropic Claude'}
            </span>
            <span class="dense-val">${formatNumber(d.tokens)}</span>
          </div>
          <div style="font-size: 11px; color: var(--text-secondary); display:flex; justify-content:space-between;">
            <span>Standard: $${d.cost_uncached.toFixed(2)}</span>
            <span style="color:#34d399;">Cached: $${d.cost_cached.toFixed(2)}</span>
          </div>
        </div>
      `).join('');

      const wList = document.getElementById('top-projects-list');
      const sortedW = Object.entries(DATA.projects || {}).sort((a,b) => b[1].tokens - a[1].tokens).slice(0, 5);
      const maxWTok = sortedW.length ? sortedW[0][1].tokens : 1;
      wList.innerHTML = sortedW.map(([name, d]) => `
        <div class="dense-item">
          <div class="dense-top">
            <span class="dense-name">${escapeHtml(name)} <span style="font-size:10px; color:var(--text-tertiary); font-weight:normal;">(${d.conversations} chats)</span></span>
            <span class="dense-val">${formatNumber(d.tokens)} &bull; $${d.cost_uncached_usd.toFixed(2)}</span>
          </div>
          <div class="dense-track">
            <div class="dense-fill" style="width: ${(d.tokens / maxWTok) * 100}%;"></div>
          </div>
        </div>
      `).join('');
    }
    renderOverviewLists();

    // Render Models Table
    function renderModelsTable() {
      const tbody = document.getElementById('models-table-body');
      tbody.innerHTML = Object.entries(DATA.models || {})
        .sort((a,b) => b[1].total_tokens - a[1].total_tokens)
        .map(([name, m]) => `
          <tr>
            <td style="font-weight: 600; color: var(--text-primary);">${name}</td>
            <td><span class="badge-pill ${m.family === 'Google' ? 'badge-blue' : 'badge-amber'}">${m.family}</span></td>
            <td class="mono">${formatNumber(m.total_tokens)}</td>
            <td class="mono">${(m.output_tokens || 0).toLocaleString()}</td>
            <td class="mono">${(m.thinking_tokens || 0).toLocaleString()}</td>
            <td class="mono">${(m.tool_call_tokens || 0).toLocaleString()}</td>
            <td class="mono" style="color: #34d399; font-weight:600;">$${m.cost_uncached_usd.toFixed(2)}</td>
            <td class="mono" style="color: #60a5fa;">$${m.cost_cached_usd.toFixed(2)}</td>
          </tr>
        `).join('');
    }
    renderModelsTable();

    // Render Tools Table
    function renderToolsTable() {
      const tbody = document.getElementById('tools-table-body');
      const tools = Object.entries(DATA.tools || {}).sort((a,b) => b[1].invocations - a[1].invocations);
      const totalInvs = tools.reduce((acc, curr) => acc + curr[1].invocations, 0) || 1;
      tbody.innerHTML = tools.map(([tName, d]) => `
        <tr>
          <td style="font-family: var(--font-mono); font-weight: 600; color: #93c5fd;">${tName}</td>
          <td class="mono">${d.invocations.toLocaleString()}</td>
          <td class="mono">${formatNumber(d.argument_tokens)}</td>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <div style="flex:1; height:4px; background:#222329; border-radius:2px; overflow:hidden;">
                <div style="height:100%; width:${((d.invocations/totalInvs)*100).toFixed(1)}%; background:#3b82f6;"></div>
              </div>
              <span class="mono">${((d.invocations/totalInvs)*100).toFixed(1)}%</span>
            </div>
          </td>
        </tr>
      `).join('');
    }
    renderToolsTable();

    // Render Workspaces Table
    function renderWorkspacesTable() {
      const tbody = document.getElementById('projects-table-body');
      tbody.innerHTML = Object.entries(DATA.projects || {})
        .sort((a,b) => b[1].tokens - a[1].tokens)
        .map(([pName, p]) => `
          <tr>
            <td style="font-weight: 600; color: var(--text-primary);">${pName}</td>
            <td class="mono">${p.conversations}</td>
            <td class="mono">${(p.invocations || 0).toLocaleString()}</td>
            <td class="mono">${formatNumber(p.tokens)}</td>
            <td class="mono" style="color: #34d399; font-weight:600;">$${p.cost_uncached_usd.toFixed(2)}</td>
            <td class="mono" style="color: #60a5fa;">$${p.cost_cached_usd.toFixed(2)}</td>
            <td style="font-size:11px; color:var(--text-tertiary);">${(p.models || []).slice(0, 2).join(', ')}</td>
          </tr>
        `).join('');
    }
    renderWorkspacesTable();

    // Render Conversation Ledger
    function renderChats(chats) {
      const tbody = document.getElementById('chats-table-body');
      tbody.innerHTML = chats.map(c => `
        <tr class="clickable-row" onclick="openDrawer('${c.id}')">
          <td class="mono" style="color: var(--text-tertiary);">${c.date || 'Unknown'}</td>
          <td style="font-weight: 500; color: var(--text-primary);">${c.project || 'General'}</td>
          <td><span class="badge-pill ${c.primary_model && c.primary_model.includes('Claude') ? 'badge-amber' : 'badge-blue'}">${c.primary_model || 'Unknown'}</span></td>
          <td class="mono">${c.invocations || 0}</td>
          <td class="mono">${formatNumber((c.fresh_input_tokens || 0) + (c.cached_context_tokens || 0))}</td>
          <td class="mono">${(c.output_tokens || 0).toLocaleString()}</td>
          <td class="mono">${(c.thinking_tokens || 0).toLocaleString()}</td>
          <td class="mono" style="color: #34d399; font-weight: 600;">$${(c.cost_uncached_usd || 0).toFixed(2)}</td>
          <td class="mono" style="color: #60a5fa;">$${(c.cost_cached_usd || 0).toFixed(2)}</td>
          <td>
            ${(c.anomalies || []).map(a => `<span class="badge-pill badge-rose" style="margin-right:4px;">${a}</span>`).join('') || '<span style="color:var(--text-tertiary); font-size:10px;">Normal</span>'}
          </td>
        </tr>
      `).join('');
    }
    renderChats(DATA.conversations || []);

    // Filter Logic
    function filterChats() {
      const qElem = document.getElementById('chat-search');
      const q = (qElem && qElem.value ? qElem.value : '').toLowerCase();
      const mElem = document.getElementById('chat-model-filter');
      const m = mElem && mElem.value ? mElem.value : '';
      const pElem = document.getElementById('chat-project-filter');
      const p = pElem && pElem.value ? pElem.value : '';
      const sElem = document.getElementById('chat-status-filter');
      const s = sElem && sElem.value ? sElem.value : '';

      const filtered = (DATA.conversations || []).filter(c => {
        const matchQ = !q || (c.project && c.project.toLowerCase().includes(q)) || (c.id && c.id.toLowerCase().includes(q));
        const matchM = !m || c.primary_model === m || (c.models && c.models.includes(m));
        const matchP = !p || c.project === p;
        const matchS = !s || (s === 'active' && c.is_active !== 0) || (s === 'archived' && c.is_active === 0);
        return matchQ && matchM && matchP && matchS;
      });
      renderChats(filtered);
    }

    // Populate Filter Selects
    function populateFilters() {
      const mSel = document.getElementById('chat-model-filter');
      const pSel = document.getElementById('chat-project-filter');
      Object.keys(DATA.models || {}).forEach(m => mSel.innerHTML += `<option value="${m}">${m}</option>`);
      Object.keys(DATA.projects || {}).forEach(p => pSel.innerHTML += `<option value="${p}">${p}</option>`);
    }
    populateFilters();

    // Persistent Tab Switcher
    function switchTab(tabId, el) {
      currentTab = tabId;
      try {
        localStorage.setItem('antigravity_active_tab', tabId);
        if (vscode) {
          const s = vscode.getState() || {};
          vscode.setState({ ...s, activeTab: tabId });
        }
      } catch(e) {}

      document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
      });
      document.querySelectorAll('.tab-pane').forEach(p => {
        p.classList.toggle('active', p.id === 'tab-' + tabId);
      });
    }

    // Slide-Over Detail Drawer
    function openDrawer(convId) {
      const conv = (DATA.conversations || []).find(c => c.id === convId);
      if (!conv) return;

      document.getElementById('drawer-title').innerText = `${conv.project || 'General'} (${conv.date || 'Unknown'})`;
      document.getElementById('drawer-subtitle').innerText = `${conv.id} • ${conv.primary_model}`;

      // Render Context Compounding Curve
      const curveSvg = document.getElementById('drawer-curve-svg');
      const trace = conv.trace || [];
      if (trace.length > 1) {
        const maxCtx = Math.max(...trace.map(t => t.context), 1000);
        const pts = trace.map((t, i) => {
          const x = (i / (trace.length - 1)) * 480 + 10;
          const y = 110 - ((t.context / maxCtx) * 95);
          return `${x},${y}`;
        }).join(' ');

        const areaPts = `10,115 ${pts} 490,115`;
        curveSvg.innerHTML = `
          <defs>
            <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.35" />
              <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.0" />
            </linearGradient>
          </defs>
          <polygon points="${areaPts}" fill="url(#curveGrad)" />
          <polyline points="${pts}" fill="none" stroke="#3b82f6" stroke-width="2.5" />
        `;
      } else {
        curveSvg.innerHTML = `<text x="250" y="65" fill="#71717a" text-anchor="middle" font-size="12">Single-turn session (no compounding)</text>`;
      }

      // Render Token Anatomy
      document.getElementById('drawer-tokens-grid').innerHTML = `
        <div class="legend-item"><div class="legend-top">Fresh Input</div><div class="legend-val">${formatNumber(conv.fresh_input_tokens || 0)}</div></div>
        <div class="legend-item"><div class="legend-top">Cached Context</div><div class="legend-val">${formatNumber(conv.cached_context_tokens || 0)}</div></div>
        <div class="legend-item"><div class="legend-top">Generated Output</div><div class="legend-val">${(conv.output_tokens || 0).toLocaleString()}</div></div>
        <div class="legend-item"><div class="legend-top">Reasoning / Thinking</div><div class="legend-val">${(conv.thinking_tokens || 0).toLocaleString()}</div></div>
      `;

      // Render Tool Pills
      const toolEntries = Object.entries(conv.tools || {});
      document.getElementById('drawer-tools-pills').innerHTML = toolEntries.length
        ? toolEntries.map(([t, count]) => `<div class="tool-pill">${t} <span>${count}x</span></div>`).join('')
        : '<span style="color:var(--text-tertiary); font-size:11px;">No tool executions in this conversation</span>';

      // Render Stepper Table
      const sBody = document.getElementById('drawer-steps-body');
      sBody.innerHTML = trace.map(t => `
        <tr>
          <td class="mono">#${t.turn}</td>
          <td class="mono">${formatNumber(t.context)}</td>
          <td class="mono">${t.out}</td>
          <td style="font-size:10px; color:#93c5fd;">${(t.tools || []).join(', ') || '-'}</td>
          <td class="mono" style="color:#34d399;">$${(t.cost || 0).toFixed(3)}</td>
        </tr>
      `).join('');

      document.getElementById('drawer-overlay').classList.add('open');
      document.getElementById('trace-drawer').classList.add('open');
    }

    function closeDrawer() {
      document.getElementById('drawer-overlay').classList.remove('open');
      document.getElementById('trace-drawer').classList.remove('open');
    }

    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });



    // CSV Export
    function exportLedgerCsv() {
      const convs = DATA.conversations || [];
      const headers = ['Date', 'Conversation_ID', 'Project', 'Model', 'Turns', 'Fresh_Input', 'Cached_Context', 'Output', 'Thinking', 'Total_Tokens', 'Standard_Cost_USD', 'Cached_Cost_USD'];
      let csv = headers.join(',') + '\n';
      convs.forEach(c => {
        csv += [
          c.date, c.id, `"${c.project}"`, `"${c.primary_model}"`,
          c.invocations, c.fresh_input_tokens, c.cached_context_tokens,
          c.output_tokens, c.thinking_tokens, c.total_tokens,
          c.cost_uncached_usd, c.cost_cached_usd
        ].join(',') + '\n';
      });

      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `antigravity_token_ledger_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
    }

    // Markdown Copy
    function copyMarkdownSummary() {
      const s = DATA.summary;
      const b = DATA.budget || {};
      const md = `### 🚀 Antigravity IDE — Token & Cost Summary Report
- **Total Processed Volume**: ${formatNumber(s.total_cumulative_tokens)} (${(s.cache_hit_ratio_pct || 99.9)}% Prompt Cache Hit)
- **Standard Commercial Valuation**: $${s.cost_uncached_usd.toFixed(2)} USD
- **Prompt-Cached Real Cost**: $${s.cost_cached_usd.toFixed(2)} USD (*Saved $${s.cache_savings_usd.toFixed(2)}*)
- **Total Autonomous Turns**: ${s.total_invocations.toLocaleString()} across ${s.total_conversations} sessions
- **Today's Spend & Pacing**: $${(b.today_cost_cached || 0).toFixed(2)} / $${b.daily_target_usd || 5}.00 (${b.today_percent_used || 0}% cap)
*Generated by Quota*`;

      navigator.clipboard.writeText(md);
      alert('Markdown report copied to clipboard!');
    }

    function handleRefresh() {
      const btn = document.getElementById('refresh-btn');
      if (btn) {
        btn.innerText = 'Scanning...';
        btn.disabled = true;
      }
      if (vscode) {
        vscode.postMessage({ command: 'refresh' });
      } else {
        window.location.reload();
      }
    }


    function updateUI() {
      initMetrics();
      renderTimeline();
      renderSegmentedBar();
      renderOverviewLists();
      renderModelsTable();
      renderToolsTable();
      renderWorkspacesTable();
      filterChats();
      if (activeDrawerConvId) {
        renderDrawerContent(activeDrawerConvId);
      }
    }

    // Restore saved tab
    (function restoreActiveTab() {
      let savedTab = 'overview';
      try {
        if (vscode && vscode.getState() && vscode.getState().activeTab) {
          savedTab = vscode.getState().activeTab;
        } else if (localStorage.getItem('antigravity_active_tab')) {
          savedTab = localStorage.getItem('antigravity_active_tab');
        }
      } catch(e) {}

      if (savedTab) {
        const targetBtn = document.querySelector(".tab-btn[data-tab='" + savedTab + "']");
        if (targetBtn) {
          switchTab(savedTab, targetBtn);
        }
      }
    })();

    window.addEventListener('message', event => {
      const message = event.data;
      if (message.command === 'updateData' && message.data) {
        DATA = message.data;
        updateUI();
      }
    });
  </script>
</body>
</html>
'''

def get_logo_base64():
    candidates = [
        os.path.join(BASE_DIR, "icon.png"),
        os.path.join(BASE_DIR, "logo_256.png"),
        os.path.join(BASE_DIR, "logo.png"),
        os.path.expanduser("~/Projects/antigravity-token-tracker/icon.png"),
        os.path.expanduser("~/Projects/antigravity-token-tracker/logo_256.png"),
        os.path.expanduser("~/Projects/antigravity-token-tracker/logo.png")
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

def generate_dashboard_html(data, out_dir=BASE_DIR):
    html_path = os.path.join(out_dir, "dashboard.html")
    data_json = json.dumps(data)
    logo_b64 = get_logo_base64()
    html_content = ENTERPRISE_HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json)
    html_content = html_content.replace("__LOGO_PLACEHOLDER__", logo_b64)
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
    args = parser.parse_args()
    if args.data_dir:
        set_active_data_dir(args.data_dir)
        ensure_data_migration()

    if args.set_budget:
        daily, monthly = args.set_budget
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

    results = merge_ledger_and_live(brain_path=brain_to_use)
    dash_path = generate_dashboard_html(results)

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

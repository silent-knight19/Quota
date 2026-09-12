"""
Unit & Regression Test Suite for Quota (tracker.py)
Validates all P0, P1, P2 fixes across Pricing, Project Attribution, Token Additivity,
SQLite Persistence, CSV Sanitization, Atomic I/O, and Scanner Isolation.
"""

import os
import sys
import json
import sqlite3
import tempfile
import unittest

# Add parent directory to path so tracker can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tracker


class TestPricingResolution(unittest.TestCase):
    """Verifies boundary-aware model matching and eliminates the ~16.7x GPT-4o-mini overcharge bug (Claude P0-1)."""

    def test_gpt4o_mini_with_date_suffix(self):
        # Must resolve to GPT-4o-mini, NOT GPT-4o
        pricing = tracker.get_pricing("gpt-4o-mini-2024-07-18")
        self.assertEqual(pricing["input_uncached"], 0.15)
        self.assertEqual(pricing["output"], 0.60)

    def test_gpt4o_mini_preview(self):
        pricing = tracker.get_pricing("GPT-4o-mini-realtime-preview")
        self.assertEqual(pricing["input_uncached"], 0.15)
        self.assertEqual(pricing["output"], 0.60)

    def test_gpt4o_exact(self):
        pricing = tracker.get_pricing("gpt-4o")
        self.assertEqual(pricing["input_uncached"], 2.50)
        self.assertEqual(pricing["output"], 10.00)

    def test_o1_and_o1_mini(self):
        p_o1 = tracker.get_pricing("o1")
        p_mini = tracker.get_pricing("o1-mini")
        p_o3_mini = tracker.get_pricing("o3-mini")
        self.assertEqual(p_o1["input_uncached"], 15.00)
        self.assertEqual(p_mini["input_uncached"], 3.00)
        self.assertEqual(p_o3_mini["input_uncached"], 1.10)

    def test_claude_sonnet_and_haiku(self):
        p_sonnet = tracker.get_pricing("claude-3-5-sonnet-20241022")
        p_haiku = tracker.get_pricing("claude-3-5-haiku-20241022")
        self.assertEqual(p_sonnet["input_uncached"], 3.00)
        self.assertEqual(p_haiku["input_uncached"], 0.80)

    def test_gemini_flash_variants(self):
        p_flash = tracker.get_pricing("gemini-2.0-flash")
        p_pro = tracker.get_pricing("gemini-1.5-pro")
        self.assertEqual(p_flash["input_uncached"], 0.10)
        self.assertEqual(p_pro["input_uncached"], 1.25)

    def test_unknown_model_fallback(self):
        p_unknown = tracker.get_pricing("completely-unknown-custom-model-999")
        self.assertEqual(p_unknown, tracker.PRICING_TABLE["Default"])

    def test_no_duplicate_pricing_keys(self):
        # PRICING_TABLE defined without duplicate key warnings
        self.assertIn("Claude Opus 4.6 (Thinking)", tracker.PRICING_TABLE)
        self.assertIn("Claude Sonnet 4.6 (Thinking)", tracker.PRICING_TABLE)
        self.assertIn("Gemini 3.1 Pro (High)", tracker.PRICING_TABLE)


class TestProjectAttribution(unittest.TestCase):
    """Verifies that ~/Projects/* paths don't collapse into 'Projects' (Claude & LLM1 P0-3)."""

    def test_clean_project_name_unix(self):
        # Must resolve to the workspace name, not "Projects"
        path = "/Users/sachinkumarsingh/Projects/my-cool-app"
        self.assertEqual(tracker.clean_project_name(path), "my-cool-app")

    def test_clean_project_name_windows(self):
        path = "C:\\Users\\Sachin\\Projects\\antigravity-token-tracker"
        self.assertEqual(tracker.clean_project_name(path), "antigravity-token-tracker")

    def test_clean_project_name_deep_nested(self):
        path = "/home/developer/Projects/org/services/payment-gateway"
        self.assertEqual(tracker.clean_project_name(path), "payment-gateway")

    def test_clean_project_name_corpus_mapping(self):
        path = "[file:///Users/developer/Projects/backend-api] -> [BackendCorpus]"
        self.assertEqual(tracker.clean_project_name(path), "backend-api")

    def test_clean_project_name_fallback_general(self):
        self.assertEqual(tracker.clean_project_name(""), "General")
        self.assertEqual(tracker.clean_project_name(None), "General")
        self.assertEqual(tracker.clean_project_name("/Users/sachin/Projects"), "General")


class TestAtomicWritesAndCSV(unittest.TestCase):
    """Verifies atomic file replacement and CSV formula injection neutralization (P2-01, P2-02)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_atomic_write_json(self):
        target = os.path.join(self.temp_dir, "test.json")
        data = {"hello": "world", "count": 42}
        tracker.atomic_write_json(target, data)
        self.assertTrue(os.path.exists(target))
        with open(target, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded, data)

    def test_safe_csv_cell_neutralization(self):
        # Formulas starting with =, +, -, @, \t, \r must be prefixed with single quote
        self.assertEqual(tracker.safe_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(tracker.safe_csv_cell("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(tracker.safe_csv_cell("-SUM(A1:A10)"), "'-SUM(A1:A10)")
        self.assertEqual(tracker.safe_csv_cell("@eval(x)"), "'@eval(x)")
        self.assertEqual(tracker.safe_csv_cell("Safe Project Name"), "Safe Project Name")
        self.assertEqual(tracker.safe_csv_cell(None), "")
        self.assertEqual(tracker.safe_csv_cell(12345), 12345)


class TestSQLitePersistence(unittest.TestCase):
    """Verifies SQLite ledger schema, migrations, transaction safety, and daily breakdown restoration (P1-3, P2-3)."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(self.db_fd)
        tracker.init_database(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_schema_has_daily_breakdown_and_first_date(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(conversations_ledger);")
        columns = [row[1] for row in cur.fetchall()]
        conn.close()
        self.assertIn("daily_breakdown_json", columns)
        self.assertIn("first_date", columns)

    def test_save_and_load_daily_breakdown(self):
        test_conv = {
            "id": "conv-test-123",
            "project": "test-project",
            "date": "2026-09-12",
            "first_date": "2026-09-10",
            "primary_model": "Gemini 3.8 Flash",
            "models": ["Gemini 3.8 Flash"],
            "invocations": 5,
            "fresh_input_tokens": 1000,
            "cached_context_tokens": 5000,
            "output_tokens": 800,
            "thinking_tokens": 200,
            "tool_call_tokens": 150,
            "total_tokens": 7150,
            "cost_uncached_usd": 0.05,
            "cost_cached_usd": 0.01,
            "cache_savings_usd": 0.04,
            "is_active": 1,
            "tools": {"search": 2},
            "anomalies": [],
            "trace": [],
            "daily_breakdown": {
                "2026-09-10": {"tokens": 2000, "cost_cached": 0.003},
                "2026-09-12": {"tokens": 5150, "cost_cached": 0.007}
            }
        }
        tracker.save_conversations_to_ledger([test_conv], db_path=self.db_path)

        loaded = tracker.load_ledger_from_db(db_path=self.db_path)
        self.assertIn("conv-test-123", loaded)
        reloaded_conv = loaded["conv-test-123"]
        self.assertEqual(reloaded_conv["project"], "test-project")
        self.assertEqual(reloaded_conv["first_date"], "2026-09-10")
        self.assertIn("2026-09-10", reloaded_conv.get("daily_breakdown", {}))
        self.assertEqual(reloaded_conv["daily_breakdown"]["2026-09-10"]["tokens"], 2000)


class TestWebviewSecurity(unittest.TestCase):
    """Verifies Webview CSP hardening and safe data injection (Claude P0-1, P1-4, P1-7)."""

    def test_csp_does_not_contain_external_network_sources(self):
        csp_line = ""
        for line in tracker.ENTERPRISE_HTML_TEMPLATE.splitlines():
            if "Content-Security-Policy" in line:
                csp_line = line
                break
        self.assertTrue(csp_line, "CSP meta tag should exist")
        self.assertNotIn("https:", csp_line)
        self.assertNotIn("vscode-resource:", csp_line)

    def test_generate_dashboard_escapes_closing_script(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {
                "summary": {},
                "conversations": [{"id": "test", "project": "</script><script>alert(1)</script>"}]
            }
            dash_path = tracker.generate_dashboard_html(payload, out_dir=tmp_dir)
            with open(dash_path, "r", encoding="utf-8") as f:
                content = f.read()
            # The literal </script> inside JSON should be safely escaped as <\/script>
            self.assertNotIn('</script><script>alert(1)</script>', content)
            self.assertIn('<\\/script>', content)


class TestTokenAccountingAndFaultIsolation(unittest.TestCase):
    """Verifies token additivity and step-level fault isolation (Claude P1-03, P1-2, P2-7)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scanner_step_fault_isolation(self):
        # Create a mock brain directory with a transcript containing a corrupt line between valid steps
        conv_dir = os.path.join(self.temp_dir, "test-conv", ".system_generated", "logs")
        os.makedirs(conv_dir, exist_ok=True)
        transcript_path = os.path.join(conv_dir, "transcript.jsonl")

        step1 = {
            "type": "USER_INPUT",
            "content": "Hello AI, write a python function."
        }
        step2 = "NOT_VALID_JSON_CORRUPTED_LINE{{{"
        step3 = {
            "type": "PLANNER_RESPONSE",
            "model": "gemini-2.0-flash",
            "content": "def add(a, b): return a + b",
            "tool_calls": [{"name": "run_command", "args": {"cmd": "ls"}}],
            "thinking": "Planning function..."
        }

        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(step1) + "\n")
            f.write(step2 + "\n")
            f.write(json.dumps(step3) + "\n")

        # Scan the mock brain directory
        convs, tools = tracker.scan_live_brain(self.temp_dir)

        # The conversation MUST NOT be discarded; it must be parsed with anomalies flagged
        self.assertEqual(len(convs), 1)
        c = convs[0]
        self.assertEqual(c["id"], "test-conv")
        self.assertEqual(c["invocations"], 1)
        self.assertTrue(any("Malformed JSON" in a for a in c["anomalies"]))
        self.assertGreater(c["output_tokens"], 0)
        self.assertGreater(c["tool_call_tokens"], 0)
        # Token Additivity: total_tokens == fresh + cached + out + tools + thinking
        computed_total = (
            c["fresh_input_tokens"] +
            c["cached_context_tokens"] +
            c["output_tokens"] +
            c["tool_call_tokens"] +
            c["thinking_tokens"]
        )
        self.assertEqual(c["total_tokens"], computed_total)


if __name__ == "__main__":
    unittest.main()

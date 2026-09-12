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
import hashlib
import multiprocessing
import re
import subprocess

# Add parent directory to path so tracker can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tracker


def _worker_scan(brain_dir, db_path):
    tracker.merge_ledger_and_live(brain_path=brain_dir, db_path=db_path)


def _worker_upsert(db_path, conv):
    tracker.save_conversations_to_ledger([conv], db_path=db_path)



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


class TestContextWindowPrecedence(unittest.TestCase):
    """Verifies prefix vs exact matching and context-window precedence (P1-2)."""

    def test_context_limit_o1_mini(self):
        self.assertEqual(tracker.get_model_context_limit("o1-mini"), 128_000)

    def test_context_limit_o1(self):
        self.assertEqual(tracker.get_model_context_limit("o1"), 200_000)

    def test_context_limit_o3_and_o3_mini(self):
        self.assertEqual(tracker.get_model_context_limit("o3"), 200_000)
        self.assertEqual(tracker.get_model_context_limit("o3-mini"), 200_000)

    def test_context_limit_gpt4_vs_gpt4o(self):
        self.assertEqual(tracker.get_model_context_limit("gpt-4"), 128_000)
        self.assertEqual(tracker.get_model_context_limit("gpt-4o"), 128_000)
        self.assertEqual(tracker.get_model_context_limit("gpt-4o-mini"), 128_000)

    def test_context_limit_claude_and_gemini(self):
        self.assertEqual(tracker.get_model_context_limit("claude-3-5-sonnet-20241022"), 200_000)
        self.assertEqual(tracker.get_model_context_limit("claude-opus-4"), 200_000)
        self.assertEqual(tracker.get_model_context_limit("gemini-2.0-flash"), 200_000)
        self.assertEqual(tracker.get_model_context_limit("gemini-1.5-pro"), 200_000)

    def test_context_limit_suffixed_names(self):
        self.assertEqual(tracker.get_model_context_limit("o1-mini-2024-09-12"), 128_000)
        self.assertEqual(tracker.get_model_context_limit("o1-mini-preview"), 128_000)
        self.assertEqual(tracker.get_model_context_limit("o3-mini-2025-01-31"), 200_000)

    def test_context_limit_unknown_model_fallback(self):
        self.assertEqual(tracker.get_model_context_limit("completely-unknown-custom-model"), tracker.DEFAULT_CONTEXT_WINDOW)


class TestPricingIdentitiesAndAliases(unittest.TestCase):
    """Verifies strict financial separation of GPT-4 vs GPT-4o and alias correctness (P2-2)."""

    def test_pricing_gpt4_distinct_from_gpt4o(self):
        p4 = tracker.get_pricing("gpt-4")
        p4o = tracker.get_pricing("gpt-4o")
        self.assertNotEqual(p4["input_uncached"], p4o["input_uncached"])
        self.assertEqual(p4["input_uncached"], 30.00)
        self.assertEqual(p4["output"], 60.00)
        self.assertEqual(p4o["input_uncached"], 2.50)
        self.assertEqual(p4o["output"], 10.00)

    def test_pricing_alias_gpt_4_maps_to_gpt4_not_gpt4o(self):
        p_alias = tracker.get_pricing("gpt 4")
        p4o = tracker.get_pricing("gpt-4o")
        self.assertEqual(p_alias["input_uncached"], 30.00)
        self.assertEqual(p_alias["output"], 60.00)
        self.assertNotEqual(p_alias["input_uncached"], p4o["input_uncached"])

    def test_pricing_family_attribution(self):
        self.assertEqual(tracker.get_pricing("gpt-4")["family"], "OpenAI")
        self.assertEqual(tracker.get_pricing("gpt-4o")["family"], "OpenAI")
        self.assertEqual(tracker.get_pricing("gpt-4o-mini")["family"], "OpenAI")
        self.assertEqual(tracker.get_pricing("claude-3-5-sonnet")["family"], "Anthropic")
        self.assertEqual(tracker.get_pricing("gemini-2.0-flash")["family"], "Google")

    def test_turn_cost_non_negative_and_additive(self):
        uncached, cached = tracker.calculate_turn_cost("gpt-4", 1000, 2000, 500)
        self.assertGreaterEqual(uncached, 0.0)
        self.assertGreaterEqual(cached, 0.0)
        self.assertLessEqual(cached, uncached)


class TestHardenedWebviewAndCSV(unittest.TestCase):
    """Verifies CSP cryptographic nonce, zero inline handlers, and safe CSV serializing (P2-1, P2-4)."""

    def test_canonical_csp_contains_nonce_and_no_unsafe_inline(self):
        template = tracker.get_dashboard_template()
        csp_line = ""
        for line in template.splitlines():
            if "Content-Security-Policy" in line:
                csp_line = line
                break
        self.assertTrue(csp_line, "CSP meta tag must exist")
        self.assertIn("script-src 'nonce-__NONCE__';", csp_line)
        self.assertNotIn("'unsafe-inline'", csp_line.split("script-src")[1].split(";")[0])
        self.assertNotIn("https:", csp_line)
        self.assertNotIn("vscode-resource:", csp_line)

    def test_generate_dashboard_injects_cryptographic_nonce(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {"summary": {}, "conversations": []}
            dash_path = tracker.generate_dashboard_html(payload, out_dir=tmp_dir)
            with open(dash_path, "r", encoding="utf-8") as f:
                content = f.read()

            csp_match = re.search(r"script-src 'nonce-([a-zA-Z0-9_\-]+)'", content)
            script_match = re.search(r"<script nonce=\"([a-zA-Z0-9_\-]+)\">", content)
            self.assertIsNotNone(csp_match, "CSP must contain injected nonce")
            self.assertIsNotNone(script_match, "<script> tag must contain injected nonce")

            csp_nonce = csp_match.group(1)
            script_nonce = script_match.group(1)
            self.assertEqual(csp_nonce, script_nonce)
            self.assertGreaterEqual(len(csp_nonce), 24)

    def test_no_inline_on_event_attributes_in_canonical_dashboard(self):
        template = tracker.get_dashboard_template()
        inline_handlers = re.findall(r"(\son[a-z]+=[^>\s]+)", template)
        self.assertEqual(inline_handlers, [], f"Found forbidden inline event handlers: {inline_handlers}")

    def test_xss_payload_injection_neutralized(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {
                "summary": {},
                "conversations": [
                    {
                        "id": "xss-test-1",
                        "project": "</script><script>alert(1)</script>",
                        "primary_model": '<img src=x onerror=alert("XSS")>',
                        "tools": {'"><svg/onload=alert(1)>': 1},
                        "anomalies": ["javascript:alert(1)"]
                    }
                ]
            }
            dash_path = tracker.generate_dashboard_html(payload, out_dir=tmp_dir)
            with open(dash_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Verify no unescaped </script> tag inside JSON
            self.assertNotIn("</script><script>alert(1)</script>", content)
            self.assertIn("<\\/script>", content)

    def test_browser_csv_cell_formula_and_quote_neutralization(self):
        def mock_browser_csv_cell(value):
            text = str(value if value is not None else "")
            safe = "'" + text if re.match(r"^[=+\-@\t\r]", text) else text
            return f'"{safe.replace(chr(34), chr(34) + chr(34))}"'

        self.assertEqual(mock_browser_csv_cell("=1+1"), '"\'=1+1"')
        self.assertEqual(mock_browser_csv_cell("+cmd"), '"\'+cmd"')
        self.assertEqual(mock_browser_csv_cell("-malicious"), '"\'-malicious"')
        self.assertEqual(mock_browser_csv_cell("@SUM(A1:A10)"), '"\'@SUM(A1:A10)"')
        self.assertEqual(mock_browser_csv_cell("\tmalicious"), '"\'\tmalicious"')
        self.assertEqual(mock_browser_csv_cell('He said "Hello"'), '"He said ""Hello"""')
        self.assertEqual(mock_browser_csv_cell("Normal Workspace"), '"Normal Workspace"')


class TestSQLiteAuthoritativeConcurrency(unittest.TestCase):
    """Verifies multi-process concurrency, zero lost updates, and database integrity (P1-1)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_ledger.sqlite")
        tracker.init_database(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_session(self, brain_dir, conv_id, project, model, prompt_text):
        conv_dir = os.path.join(brain_dir, conv_id, ".system_generated", "logs")
        os.makedirs(conv_dir, exist_ok=True)
        transcript = os.path.join(conv_dir, "transcript.jsonl")
        steps = [
            {"type": "USER_INPUT", "content": prompt_text},
            {"type": "PLANNER_RESPONSE", "model": model, "content": "Done", "tool_calls": []}
        ]
        with open(transcript, "w", encoding="utf-8") as f:
            for s in steps:
                f.write(json.dumps(s) + "\n")

    def test_multiprocess_concurrent_scanners_no_lost_updates(self):
        # Process A sees Conv A + Conv C
        # Process B sees Conv A + Conv D
        # Final DB must contain A, C, and D
        brain_a = os.path.join(self.temp_dir, "brain_a")
        brain_b = os.path.join(self.temp_dir, "brain_b")

        self._create_mock_session(brain_a, "conv-A", "ProjA", "gpt-4o", "Hello from A")
        self._create_mock_session(brain_a, "conv-C", "ProjC", "gpt-4o", "Hello from C")

        self._create_mock_session(brain_b, "conv-A", "ProjA", "gpt-4o", "Hello from A updated")
        self._create_mock_session(brain_b, "conv-D", "ProjD", "gpt-4o", "Hello from D")

        p1 = multiprocessing.Process(target=_worker_scan, args=(brain_a, self.db_path))
        p2 = multiprocessing.Process(target=_worker_scan, args=(brain_b, self.db_path))

        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)

        self.assertEqual(p1.exitcode, 0, "Worker 1 failed")
        self.assertEqual(p2.exitcode, 0, "Worker 2 failed")

        ledger = tracker.load_ledger_from_db(self.db_path)
        self.assertIn("conv-A", ledger, "Conversation A must survive concurrent scan")
        self.assertIn("conv-C", ledger, "Conversation C must survive concurrent scan")
        self.assertIn("conv-D", ledger, "Conversation D must survive concurrent scan")

        # Database integrity check
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchall()
        conn.close()
        self.assertEqual(res, [("ok",)])

    def test_simultaneous_writes_to_same_conv_id(self):
        c1 = {"id": "same-conv", "date": "2026-09-12", "project": "P1", "primary_model": "gpt-4o", "total_tokens": 1000}
        c2 = {"id": "same-conv", "date": "2026-09-12", "project": "P1", "primary_model": "gpt-4o", "total_tokens": 2000}

        p1 = multiprocessing.Process(target=_worker_upsert, args=(self.db_path, c1))
        p2 = multiprocessing.Process(target=_worker_upsert, args=(self.db_path, c2))

        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)

        self.assertEqual(p1.exitcode, 0)
        self.assertEqual(p2.exitcode, 0)

        ledger = tracker.load_ledger_from_db(self.db_path)
        self.assertIn("same-conv", ledger)
        self.assertIn(ledger["same-conv"]["total_tokens"], [1000, 2000])

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        self.assertEqual(cur.fetchall(), [("ok",)])
        conn.close()


class TestSourceCodeIntegrityAndPackaging(unittest.TestCase):
    """Verifies single source of truth, hash equality, and secure publishing credentials (P3-1, P2-3)."""

    def test_root_and_extension_tracker_sha256_equality(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        root_path = os.path.join(base_dir, "tracker.py")
        ext_path = os.path.join(base_dir, "extension", "tracker.py")

        with open(root_path, "rb") as f:
            h_root = hashlib.sha256(f.read()).hexdigest()
        with open(ext_path, "rb") as f:
            h_ext = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(h_root, h_ext, "root tracker.py and extension/tracker.py MUST be byte-for-byte identical")

    def test_canonical_dashboard_sha256_equality(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        root_path = os.path.join(base_dir, "dashboard.html")
        ext_path = os.path.join(base_dir, "extension", "dashboard.html")

        with open(root_path, "rb") as f:
            h_root = hashlib.sha256(f.read()).hexdigest()
        with open(ext_path, "rb") as f:
            h_ext = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(h_root, h_ext, "root dashboard.html and extension/dashboard.html MUST be byte-for-byte identical")

    def test_publish_script_enforces_vsce_pat_env_var(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        script_path = os.path.join(base_dir, "extension", "publish_extension.sh")
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("VSCE_PAT", content, "publish_extension.sh must reference VSCE_PAT environment variable")
        self.assertIn("Please set the VSCE_PAT environment variable", content)
        self.assertNotIn('publish -p "$1"', content, "publish_extension.sh must NOT accept PAT as positional parameter $1")


if __name__ == "__main__":
    unittest.main()

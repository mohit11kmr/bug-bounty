#!/usr/bin/env python3
"""
test_e2e_pipeline.py — Deterministic Local E2E Verification Test Harness.

Strictly non-destructive and local:
  - Spins up a local Python HTTP server on 127.0.0.1.
  - Verifies:
      1. Scope filtering and wildcard evaluation.
      2. Scanner target ingestion from assets.json -> scanner-targets.txt.
      3. False-positive elimination: Standard HTTP 200 API is REJECTED, not fabricated.
      4. True vulnerability verification: CORS reflection + .env secret leak are VERIFIED.
      5. State machine integrity: DISCOVERED/TRIAGED -> VALIDATING -> VERIFIED | REJECTED.
      6. Report generation in canonical evidence directory.
"""

import http.server
import json
import os
import shutil
import sqlite3
import sys
import threading
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "recon"))

import auto_hunter
import intelligence
import report_gen
import scanner


class MockSecurityServerHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Quiet logging

    def do_GET(self):
        # 1. Normal API 200 endpoint (Should be REJECTED / not marked as vulnerability)
        if self.path == "/api/v1/users":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "https://trusted.example.com")
            self.end_headers()
            self.wfile.write(b'{"users": ["alice", "bob"], "status": "ok"}')

        # 2. CORS Misconfiguration endpoint (Should be VERIFIED)
        elif self.path == "/cors-vuln":
            req_origin = self.headers.get("Origin", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", req_origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.end_headers()
            self.wfile.write(b'{"account_id": 99912, "email": "victim@test.local"}')

        # 3. Sensitive file exposure (.env with secret key) (Should be VERIFIED)
        elif self.path == "/.env":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"APP_KEY=base64:mocksecretkey1234567890=\nDB_PASSWORD=supersecret_pass\n")

        # 5. Real login form (has an actual password input field) — SHOULD be VERIFIED
        elif self.path == "/admin/login":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Admin Sign In</h1><form>"
                b"<input type='text' name='username'>"
                b"<input type='password' name='password'>"
                b"<button>Log In</button></form></body></html>"
            )

        # 6. Normal page with just a "Login" link in its nav bar, no actual
        #    password field — SHOULD NOT be verified (this is the exact false
        #    positive pattern found on a real Flipkart/Myntra product page).
        elif self.path == "/product/some-item":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><nav><a href='/login'>Login</a></nav>"
                b"<h1>Some Product</h1><p>Buy now for $9.99</p></body></html>"
            )

        # 4. Dead endpoint
        elif self.path == "/404-dead":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Default OK")


class TestE2EPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Start local mock HTTP server on a dynamic port
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockSecurityServerHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        # 2. Setup mock target directory
        cls.prog_name = "test_mock_prog"
        cls.prog_dir = BASE / cls.prog_name
        cls.data_dir = BASE / "recon" / "data" / cls.prog_name
        cls.evidence_dir = BASE / "evidence" / "reports" / cls.prog_name

        cls.prog_dir.mkdir(parents=True, exist_ok=True)
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        (cls.data_dir / "raw").mkdir(parents=True, exist_ok=True)

        # Mock scope.yaml
        cls.scope = {
            "program": {"handle": cls.prog_name, "name": "Mock Test Program"},
            "roots": ["127.0.0.1", "localhost"],
            "excluded": ["excluded.localhost"],
            "allowed": {"max_requests_per_minute": 1000, "max_concurrency": 2},
        }
        (cls.prog_dir / "scope.yaml").write_text(json.dumps(cls.scope))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

        # Clean up test directories
        if cls.prog_dir.exists():
            shutil.rmtree(cls.prog_dir, ignore_errors=True)
        if cls.data_dir.exists():
            shutil.rmtree(cls.data_dir, ignore_errors=True)
        if cls.evidence_dir.exists():
            shutil.rmtree(cls.evidence_dir, ignore_errors=True)

    def test_01_scanner_target_ingestion_and_contract(self):
        """Test scanner.py correctly ingests assets.json, filters scope, and writes scanner-targets.txt."""
        assets = [
            {"host": "127.0.0.1", "url": f"http://127.0.0.1:{self.port}", "status": 200},
            {"host": "excluded.localhost", "url": "http://excluded.localhost", "status": 200},
            {"host": "*.wildcard.local", "url": "http://*.wildcard.local", "status": 200},
        ]
        assets_file = self.data_dir / "assets.json"
        assets_file.write_text(json.dumps(assets))

        targets = scanner.collect_scan_targets(self.prog_name, self.scope)
        target_file = self.data_dir / "raw" / "scanner-targets.txt"

        self.assertTrue(target_file.exists())
        self.assertIn("127.0.0.1", targets)
        self.assertNotIn("excluded.localhost", targets)  # Excluded check
        self.assertNotIn("*.wildcard.local", targets)   # Wildcard stripped

    def test_02_false_positive_elimination_on_normal_api(self):
        """Test that normal 200 OK API endpoint is NOT fabricated into a vulnerability."""
        is_in_scope = auto_hunter.make_scope_filter(self.scope)

        candidate = {
            "url": f"http://127.0.0.1:{self.port}/api/v1/users",
            "tag": "api_surface",
            "score": 85,  # High score previously triggered fabrication
        }

        # Must return None (unverified / normal endpoint)
        result = auto_hunter.verify_candidate(candidate, is_in_scope)
        self.assertIsNone(result, "Normal HTTP 200 API endpoint was falsely fabricated as a vulnerability!")

    def test_03_true_vulnerability_verification(self):
        """Test that legitimate CORS and secret leak exposures ARE verified with evidence."""
        is_in_scope = auto_hunter.make_scope_filter(self.scope)

        # A. CORS misconfiguration test
        cors_cand = {
            "url": f"http://127.0.0.1:{self.port}/cors-vuln",
            "tag": "cors_misconfig",
            "score": 75,
        }
        cors_result = auto_hunter.verify_candidate(cors_cand, is_in_scope)
        self.assertIsNotNone(cors_result)
        self.assertEqual(cors_result["status"], "VERIFIED")
        self.assertEqual(cors_result["tag"], "cors_misconfig")
        self.assertIn("Verified CORS reflection", cors_result["notes"])

        # B. Sensitive file exposure test
        env_cand = {
            "url": f"http://127.0.0.1:{self.port}/.env",
            "tag": "config_leak",
            "score": 80,
        }
        env_result = auto_hunter.verify_candidate(env_cand, is_in_scope)
        self.assertIsNotNone(env_result)
        self.assertEqual(env_result["status"], "VERIFIED")
        self.assertIn("env_file", env_result["notes"])

    def test_04b_admin_auth_panel_requires_real_password_field(self):
        """Regression test for a real false positive found 2026-09-09: a normal
        product page with a 'Login' nav link was auto-VERIFIED as an exposed
        admin/auth surface just because the word 'login' appeared anywhere in
        the page body. The check now requires an actual password <input> field."""
        is_in_scope = auto_hunter.make_scope_filter(self.scope)

        # A. Real login form (has a password field) -> MUST verify
        real_login_cand = {
            "url": f"http://127.0.0.1:{self.port}/admin/login",
            "tag": "admin_internal",
            "score": 60,
        }
        real_result = auto_hunter.verify_candidate(real_login_cand, is_in_scope)
        self.assertIsNotNone(real_result, "Real login form with password field should be VERIFIED")
        self.assertEqual(real_result["status"], "VERIFIED")

        # B. Normal product page with only a nav-bar Login link -> MUST NOT verify
        normal_page_cand = {
            "url": f"http://127.0.0.1:{self.port}/product/some-item",
            "tag": "auth",
            "score": 50,
        }
        normal_result = auto_hunter.verify_candidate(normal_page_cand, is_in_scope)
        self.assertIsNone(
            normal_result,
            "Normal page with just a 'Login' nav link was falsely verified as an auth/admin surface!"
        )

    def test_04_end_to_end_state_machine_and_report_generation(self):
        """Test candidate queue transitions and canonical report generation."""
        # 1. Initialize SQLite recon.db
        db_path = self.data_dir / "recon.db"
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.executescript(intelligence.SCHEMA)

        # Seed candidate queue with 1 normal API and 1 real vuln
        now = "2026-09-06"
        cur.execute(
            "INSERT INTO candidate_findings (url, host, method, tag, score, status, created_at, updated_at) "
            "VALUES (?, ?, 'GET', ?, ?, 'TRIAGED', ?, ?)",
            (f"http://127.0.0.1:{self.port}/api/v1/users", "127.0.0.1", "api_surface", 85, now, now)
        )
        cur.execute(
            "INSERT INTO candidate_findings (url, host, method, tag, score, status, created_at, updated_at) "
            "VALUES (?, ?, 'GET', ?, ?, 'TRIAGED', ?, ?)",
            (f"http://127.0.0.1:{self.port}/cors-vuln", "127.0.0.1", "cors_misconfig", 80, now, now)
        )
        con.commit()
        con.close()

        # 2. Run auto_hunter
        verified_list = auto_hunter.run_auto_hunter(self.prog_name, min_score=50, dry_run=False)

        # 3. Assertions on verified findings
        self.assertEqual(len(verified_list), 1)
        self.assertEqual(verified_list[0]["tag"], "cors_misconfig")

        # 4. Assertions on database statuses
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        api_row = cur.execute(
            "SELECT status, notes FROM candidate_findings WHERE url LIKE '%/api/v1/users'"
        ).fetchone()
        cors_row = cur.execute(
            "SELECT status, notes FROM candidate_findings WHERE url LIKE '%/cors-vuln'"
        ).fetchone()
        con.close()

        # State machine assertion: Normal API MUST be REJECTED
        self.assertEqual(api_row[0], "REJECTED")
        self.assertIn("Non-vulnerable", api_row[1])

        # State machine assertion: Real vuln MUST be VERIFIED
        self.assertEqual(cors_row[0], "VERIFIED")

        # 5. Assert report generation in canonical directory
        reports = list(self.evidence_dir.glob("H1_REPORT_*.md"))
        self.assertGreaterEqual(len(reports), 1)

        rep_content = reports[0].read_text()
        self.assertIn("[VERIFIED]", rep_content)
        self.assertIn("CWE-942", rep_content)


if __name__ == "__main__":
    unittest.main()

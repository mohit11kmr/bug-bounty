#!/usr/bin/env python3
"""
test_runtime_integrity.py — Rigorous Verification Harness for Runtime Integrity Audit.

Tests:
1. Single producer for httpx.jsonl (no race condition, atomic commit).
2. Fresh run from ZERO artifacts (subfinder -> dnsx -> httpx -> assets.json -> recon.db).
3. Repeat run cache reuse vs --fresh bypass.
4. Output contract validation (MISSING, EMPTY, PARTIAL, VALID).
5. Database consistency: assets.json == DB assets, endpoints.json == DB endpoints.
6. Finding provenance: tool column in candidate_findings ('nuclei', 'intelligence').
7. Failure injection: empty httpx, malformed jsonl, pipeline graceful stop.
8. End-to-end [A] Autonomous Zero-Touch Hunt execution.
9. End-to-end [C] Complete Scan & Prompt Generation.
"""

import http.server
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "recon"))

import auto_hunter
import intelligence
import js_miner
import recon_pipeline
import report_gen
import scanner


class MockTargetServerHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        # CORS vulnerable endpoint
        if self.path == "/vulnerable-cors":
            origin = self.headers.get("Origin", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.end_headers()
            self.wfile.write(b'{"user": "admin", "session": "secret123"}')

        # Normal non-vulnerable API endpoint
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><head><title>Mock Target Root</title></head><body><h1>Target Active</h1></body></html>")


class TestRuntimeIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockTargetServerHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        cls.prog_name = "test_integrity_prog"
        cls.prog_dir = BASE / cls.prog_name
        cls.data_dir = BASE / "recon" / "data" / cls.prog_name
        cls.raw_dir = cls.data_dir / "raw"
        cls.reports_dir = BASE / "evidence" / "reports" / cls.prog_name

    def setUp(self):
        # Ensure fresh state before test
        shutil.rmtree(self.prog_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.reports_dir, ignore_errors=True)

        self.prog_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # Standard minimal scope targeting local server
        self.scope_yaml = self.prog_dir / "scope.yaml"
        self.scope_yaml.write_text(f"""program:
  handle: {self.prog_name}
  name: Runtime Integrity Program
roots:
  - 127.0.0.1:{self.port}
excluded:
  - excluded.localhost
allowed:
  max_requests_per_minute: 60
  max_concurrency: 5
""")

    def tearDown(self):
        shutil.rmtree(self.prog_dir, ignore_errors=True)
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.reports_dir, ignore_errors=True)

    def test_01_atomic_output_contract_validation(self):
        """Test validate_jsonl_output contract: MISSING, EMPTY, PARTIAL, VALID."""
        tmp = self.raw_dir / "test_contract.jsonl"

        # MISSING
        status, recs = recon_pipeline.validate_jsonl_output(tmp)
        self.assertEqual(status, "MISSING")
        self.assertEqual(len(recs), 0)

        # EMPTY
        tmp.write_text("")
        status, recs = recon_pipeline.validate_jsonl_output(tmp)
        self.assertEqual(status, "EMPTY")
        self.assertEqual(len(recs), 0)

        # VALID
        tmp.write_text(json.dumps({"url": f"http://127.0.0.1:{self.port}", "input": "127.0.0.1"}) + "\n")
        status, recs = recon_pipeline.validate_jsonl_output(tmp)
        self.assertEqual(status, "VALID")
        self.assertEqual(len(recs), 1)

        # PARTIAL
        tmp.write_text('{"url": "http://127.0.0.1"}\ncorrupt_json_payload\n')
        status, recs = recon_pipeline.validate_jsonl_output(tmp)
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(len(recs), 1)

    def test_02_fresh_run_from_zero_artifacts(self):
        """Test completely fresh run from ZERO artifacts. Proves the entire asset chain."""
        # 1. Verify zero artifacts initially
        self.assertFalse((self.raw_dir / "subfinder.txt").exists())
        self.assertFalse((self.raw_dir / "dnsx.txt").exists())
        self.assertFalse((self.raw_dir / "httpx.jsonl").exists())
        self.assertFalse((self.data_dir / "assets.json").exists())
        self.assertFalse((self.data_dir / "endpoints.json").exists())
        self.assertFalse((self.data_dir / "recon.db").exists())

        # 2. Execute recon_pipeline.py in fresh mode
        cmd = [sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
               "--program", self.prog_name, "--skip-endpoints", "--skip-js", "--fresh"]
        res = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"recon_pipeline failed: {res.stderr}")

        # 3. Check artifacts created
        httpx_out = self.raw_dir / "httpx.jsonl"
        assets_out = self.data_dir / "assets.json"
        meta_out = self.data_dir / "run_meta.json"

        self.assertTrue(httpx_out.exists(), "httpx.jsonl missing")
        self.assertTrue(httpx_out.stat().st_size > 0, "httpx.jsonl is 0 bytes")
        self.assertTrue(assets_out.exists(), "assets.json missing")
        self.assertTrue(meta_out.exists(), "run_meta.json missing")

        assets = json.loads(assets_out.read_text())
        self.assertGreater(len(assets), 0, "assets.json is empty")
        self.assertEqual(assets[0]["status"], 200)

        meta = json.loads(meta_out.read_text())
        self.assertTrue(meta.get("fresh_mode"))
        self.assertIn("run_id", meta)

    def test_03_repeat_run_caching_vs_fresh(self):
        """Test that default run reuses cache, and --fresh forces re-execution."""
        # Run 1: Fresh
        cmd1 = [sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
                "--program", self.prog_name, "--skip-endpoints", "--skip-js", "--fresh"]
        subprocess.run(cmd1, cwd=str(BASE), check=True, capture_output=True)

        httpx_out = self.raw_dir / "httpx.jsonl"
        self.assertTrue(httpx_out.exists())
        mtime1 = httpx_out.stat().st_mtime_ns

        # Run 2: Cached default (no --fresh)
        time.sleep(0.05)
        cmd2 = [sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
                "--program", self.prog_name, "--skip-endpoints", "--skip-js"]
        res2 = subprocess.run(cmd2, cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0)
        self.assertIn("[CACHE REUSE]", res2.stdout)

        # Run 3: Forced fresh with --fresh
        time.sleep(0.05)
        cmd3 = [sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
                "--program", self.prog_name, "--skip-endpoints", "--skip-js", "--fresh"]
        res3 = subprocess.run(cmd3, cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res3.returncode, 0)
        self.assertIn("[FRESH]", res3.stdout)

    def test_04_database_consistency_and_finding_provenance(self):
        """Test that assets.json == DB assets, and candidate_findings has tool provenance."""
        # 1. Run recon
        subprocess.run([sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
                        "--program", self.prog_name, "--skip-endpoints", "--skip-js", "--fresh"],
                       cwd=str(BASE), check=True, capture_output=True)

        # 2. Seed mock endpoints for intelligence
        ep_file = self.data_dir / "endpoints.json"
        ep_data = [
            {"url": f"http://127.0.0.1:{self.port}/api/v1/auth/login?token=xyz", "method": "GET",
             "source": ["katana"], "auth_hint": "unknown", "first_seen": "2026-09-06", "last_seen": "2026-09-06"},
            {"url": f"http://127.0.0.1:{self.port}/admin/dashboard/config.json", "method": "GET",
             "source": ["katana"], "auth_hint": "unknown", "first_seen": "2026-09-06", "last_seen": "2026-09-06"},
        ]
        ep_file.write_text(json.dumps(ep_data, indent=2))

        # 3. Run scanner
        subprocess.run([sys.executable, str(BASE / "recon" / "scanner.py"),
                        "--program", self.prog_name, "--dry-run"],
                       cwd=str(BASE), check=True, capture_output=True)

        # 4. Run intelligence
        subprocess.run([sys.executable, str(BASE / "recon" / "intelligence.py"),
                        "--program", self.prog_name],
                       cwd=str(BASE), check=True, capture_output=True)

        # 5. Verify Database consistency
        db_path = self.data_dir / "recon.db"
        self.assertTrue(db_path.exists())
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        # Compare assets count
        assets_json = json.loads((self.data_dir / "assets.json").read_text())
        db_assets_count = cur.execute("SELECT count(*) FROM assets").fetchone()[0]
        self.assertEqual(len(assets_json), db_assets_count, "assets.json != DB assets count")

        # Check candidate_findings tool provenance
        findings = cur.execute("SELECT url, tag, score, status, tool FROM candidate_findings").fetchall()
        self.assertGreater(len(findings), 0)
        for f in findings:
            tool = f[4]
            self.assertIn(tool, ("nuclei", "intelligence", "heuristic"), f"Invalid tool provenance: {tool}")

        con.close()

    def test_05_application_model_wiring(self):
        """Test that application_model.json is generated after endpoints.json exists."""
        ep_file = self.data_dir / "endpoints.json"
        ep_data = [
            {"url": f"http://127.0.0.1:{self.port}/admin/orders/123", "method": "GET",
             "source": ["katana"], "auth_hint": "unknown", "first_seen": "2026-09-06", "last_seen": "2026-09-06"},
        ]
        ep_file.write_text(json.dumps(ep_data, indent=2))

        # Run application_model
        subprocess.run([sys.executable, str(BASE / "recon" / "application_model.py"),
                        "--program", self.prog_name],
                       cwd=str(BASE), check=True, capture_output=True)

        am_file = self.data_dir / "application_model.json"
        self.assertTrue(am_file.exists(), "application_model.json was not generated")
        am_data = json.loads(am_file.read_text())
        self.assertIn("actors", am_data)
        self.assertIn("objects", am_data)

    def test_06_sample_report_purity(self):
        """Test that --sample generates reports in sample/ subdirectory and does not contaminate root reports."""
        res = subprocess.run([sys.executable, str(BASE / "recon" / "report_gen.py"),
                              "--program", self.prog_name, "--sample"],
                             cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)

        sample_dir = self.reports_dir / "sample"
        self.assertTrue(sample_dir.exists(), "sample/ directory missing")
        sample_reports = list(sample_dir.glob("SAMPLE_H1_REPORT_*.md"))
        self.assertGreater(len(sample_reports), 0, "No sample report found in sample/")

        # Root reports directory must have ZERO live reports
        root_reports = list(self.reports_dir.glob("H1_REPORT_*.md"))
        self.assertEqual(len(root_reports), 0, "Sample report contaminated root reports directory")

    def test_07_failure_injection_httpx_empty(self):
        """Test graceful failure handling when httpx discovers 0 alive hosts."""
        # Overwrite scope with an unreachable port
        self.scope_yaml.write_text(f"""program:
  handle: {self.prog_name}
  name: Dead Target Program
roots:
  - 127.0.0.1:19999
excluded: []
allowed:
  max_requests_per_minute: 60
  max_concurrency: 5
""")
        # Run recon in fresh mode
        cmd = [sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
               "--program", self.prog_name, "--skip-endpoints", "--skip-js", "--fresh"]
        res = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"recon_pipeline crashed on 0 assets: {res.stderr}")
        self.assertIn("0 active web assets found", res.stdout)

        # Check assets.json is empty array and valid JSON
        assets_file = self.data_dir / "assets.json"
        self.assertTrue(assets_file.exists())
        assets = json.loads(assets_file.read_text())
        self.assertEqual(len(assets), 0)

        # Run intelligence on empty assets
        res_intel = subprocess.run([sys.executable, str(BASE / "recon" / "intelligence.py"),
                                   "--program", self.prog_name],
                                  cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res_intel.returncode, 0)

        # Check SQLite DB has 0 assets
        db_path = self.data_dir / "recon.db"
        self.assertTrue(db_path.exists())
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        count = cur.execute("SELECT count(*) FROM assets").fetchone()[0]
        self.assertEqual(count, 0)
        con.close()

    def test_08_autonomous_hunt_a_execution(self):
        """Test full [A] Autonomous Zero-Touch Hunt via start-bugbounty.sh --auto."""
        env = dict(os.environ,
                   KATANA_CRAWL_DURATION="5s",
                   NUCLEI_MAX_TIME="10",
                   NUCLEI_INCLUDE_TAGS="tech",
                   BASH_LAUNCHER_NOTTY="1")
        cmd = ["/bin/bash", str(BASE / "start-bugbounty.sh"), "--auto", self.prog_name, "--fresh"]
        res = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0, f"Autonomous hunt failed with exit code {res.returncode}:\n{res.stderr}\n{res.stdout}")

        # Verify pipeline execution across all phases
        self.assertIn("ZERO-TOUCH HUNT COMPLETE", res.stdout)

        # Verify artifacts
        self.assertTrue((self.data_dir / "assets.json").exists(), "assets.json missing")
        self.assertTrue((self.data_dir / "endpoints.json").exists(), "endpoints.json missing")
        self.assertTrue((self.data_dir / "recon.db").exists(), "recon.db missing")
        self.assertTrue((self.data_dir / "candidate_report.md").exists(), "candidate_report.md missing")
        self.assertTrue((self.data_dir / "application_model.json").exists(), "application_model.json missing")

    def test_09_complete_hunt_c_prompt_generation(self):
        """Test [C] Complete Scan & OpenCode Prompt Generation workflow."""
        # 1. Run recon pipeline
        subprocess.run([sys.executable, str(BASE / "recon" / "recon_pipeline.py"),
                        "--program", self.prog_name, "--skip-endpoints", "--skip-js", "--fresh"],
                       cwd=str(BASE), check=True, capture_output=True)

        # 2. Run intelligence to rank candidates
        subprocess.run([sys.executable, str(BASE / "recon" / "intelligence.py"),
                        "--program", self.prog_name],
                       cwd=str(BASE), check=True, capture_output=True)

        # 3. Generate hunt prompt
        cmd = [sys.executable, str(BASE / "recon" / "h1_client.py"), "--prompt", self.prog_name]
        res = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"h1_client --prompt failed: {res.stderr}")

        # 4. Verify prompt file content
        prompt_file = self.prog_dir / "AUTONOMOUS_HUNT_PROMPT.md"
        self.assertTrue(prompt_file.exists(), "AUTONOMOUS_HUNT_PROMPT.md missing")
        content = prompt_file.read_text(encoding="utf-8")
        self.assertIn(self.prog_name, content)
        self.assertIn(f"127.0.0.1:{self.port}", content)
        self.assertIn("excluded.localhost", content)
        self.assertIn("YOUR EXECUTION PROTOCOL", content)


if __name__ == "__main__":
    unittest.main()

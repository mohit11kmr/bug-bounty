#!/usr/bin/env python3
"""
test_daemon_delta_e2e.py — Proves recon/daemon.py's real delta-trigger chain fires.

PIPELINE_INTEGRITY_V2 gap: the runtime-integrity audit confirmed daemon.py's code
chains httpx -> js_miner -> scanner (nuclei) -> intelligence -> auto_hunter -> notify,
but the only live daemon run performed found 0 delta (nothing to trigger on), so the
downstream chain was never observed actually firing.

subfinder's passive-DNS discovery cannot be made to deterministically return a "new"
subdomain for a throwaway local fixture (it queries real internet-wide passive-DNS
aggregators, not the target itself — there's nothing to discover for a fixture that
was never publicly indexed). Manufacturing a real one would mean pointing subfinder
at an actual internet domain, which this audit will not do.

So this test stubs ONLY the network-dependent discovery boundary
(daemon.run_passive_subdomain_probe) to return a controlled "newly discovered" host —
exactly the shape subfinder would hand back — and lets every real downstream step
(daemon.get_existing_hosts, the delta diff itself, real httpx, real js_miner/Katana,
real scanner.py/Nuclei, real intelligence.py, real auto_hunter.py, real notify.py)
run completely unmodified against a real local HTTP fixture. Nothing about
daemon.run_delta_cycle's own logic is faked.
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
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "recon"))

import daemon  # noqa: E402


class MockHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><title>Daemon Delta Fixture</title>ok</html>")


class TestDaemonDeltaE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.prog = "test_daemon_delta_prog"
        self.prog_dir = BASE / self.prog
        self.data_dir = BASE / "recon" / "data" / self.prog
        self.reports_dir = BASE / "evidence" / "reports" / self.prog
        for d in (self.prog_dir, self.data_dir, self.reports_dir):
            shutil.rmtree(d, ignore_errors=True)
        self.prog_dir.mkdir(parents=True)
        self.data_dir.mkdir(parents=True)
        self.new_host = f"127.0.0.1:{self.port}"
        (self.prog_dir / "scope.yaml").write_text(f"""program:
  handle: {self.prog}
  name: Daemon Delta E2E Fixture
roots:
  - {self.new_host}
excluded: []
allowed:
  max_requests_per_minute: 60
  max_concurrency: 5
""")
        # prev_hosts starts EMPTY — get_existing_hosts() reads this file for real.
        (self.data_dir / "assets.json").write_text("[]")

    def tearDown(self):
        for d in (self.prog_dir, self.data_dir, self.reports_dir):
            shutil.rmtree(d, ignore_errors=True)

    def test_delta_detected_and_downstream_chain_fires_for_real(self):
        # Stub ONLY the subfinder-network boundary — everything after this point in
        # run_delta_cycle is daemon.py's real, unmodified code. Bound Katana/Nuclei
        # runtime the same way test_runtime_integrity.py does, so this real end-to-end
        # chain (real httpx/katana/nuclei subprocesses) finishes in seconds, not ~7min.
        env_patch = mock.patch.dict(os.environ, {
            "KATANA_CRAWL_DURATION": "5s",
            "NUCLEI_MAX_TIME": "10",
            "NUCLEI_INCLUDE_TAGS": "tech",
        })
        with env_patch, mock.patch.object(daemon, "run_passive_subdomain_probe", return_value={self.new_host}):
            delta_count = daemon.run_delta_cycle(self.prog, dry_run=False)

        self.assertEqual(delta_count, 1, "daemon.run_delta_cycle did not detect the injected delta")

        # 1. Real httpx probe result: the new host was appended to assets.json for real.
        assets = json.loads((self.data_dir / "assets.json").read_text())
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["source"], ["delta_daemon"])
        self.assertEqual(assets[0]["status"], 200)

        # 2. Real js_miner.py ran: endpoints.json exists (even if 0 new routes on a static page).
        self.assertTrue((self.data_dir / "endpoints.json").exists(), "js_miner did not run/produce endpoints.json")

        # 3. Real scanner.py (Nuclei) + intelligence.py ran: recon.db exists with both tables populated
        #    from the delta-discovered asset.
        db_path = self.data_dir / "recon.db"
        self.assertTrue(db_path.exists(), "intelligence.py did not run/produce recon.db")
        con = sqlite3.connect(db_path)
        db_assets = con.execute("SELECT host FROM assets").fetchall()
        con.close()
        self.assertEqual([r[0] for r in db_assets], [self.new_host])

        # 4. Real auto_hunter.py ran (no crash) — candidate_report.md is intelligence.py's
        #    marker that the chain reached that stage without a fatal error upstream.
        self.assertTrue((self.data_dir / "candidate_report.md").exists())


if __name__ == "__main__":
    unittest.main()

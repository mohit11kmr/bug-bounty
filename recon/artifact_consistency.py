#!/usr/bin/env python3
"""
artifact_consistency.py — Stale-artifact / run-ownership diagnostic.

Read-only: never resynchronizes, mutates, or deletes any file or DB row — it only
reports. Uses the run_id embedded by recon_pipeline.py/js_miner.py/scanner.py/
intelligence.py in assets.json, endpoints.json, and recon.db rows to answer:

    "Is recon.db caught up with the latest assets.json/endpoints.json discovery,
     as declared by this program's run_meta.json?"

Background: a real bug-bounty program (`meesho`) was found with recon.db's `assets`
table at 0 rows for ~10 hours after assets.json had already been repopulated by a
later run — nothing detected this automatically until a manual `stat` comparison
was done by hand. This tool makes that comparison a one-line, run_id-based check
instead of an mtime guess. See docs/audit/PIPELINE_INTEGRITY_V2_FINAL_AUDIT.md.

Usage:
  python3 recon/artifact_consistency.py --program meesho
  python3 recon/artifact_consistency.py --selfcheck
"""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RECON = BASE / "recon"


def _latest_run_id(records: list) -> str | None:
    """run_YYYYMMDD_HHMMSS_xxxxxx sorts lexically by time, so max() = most recent."""
    run_ids = {r.get("run_id", "legacy") for r in records if isinstance(r, dict)}
    run_ids.discard("legacy")
    return max(run_ids) if run_ids else None


def check_program(program: str, data_dir: Path | None = None) -> dict:
    """Read-only consistency check. Returns a report dict; missing files are a
    valid, reported status rather than an exception."""
    data_dir = data_dir or (RECON / "data" / program)
    rows = []
    overall = "CONSISTENT"

    meta_file = data_dir / "run_meta.json"
    expected_run = None
    if meta_file.exists():
        expected_run = json.loads(meta_file.read_text()).get("run_id")
        rows.append({"artifact": "run_meta.json", "run_id": expected_run,
                     "mtime": meta_file.stat().st_mtime, "expected_run": expected_run,
                     "status": "CONSISTENT"})
    else:
        rows.append({"artifact": "run_meta.json", "run_id": None, "mtime": None,
                     "expected_run": None, "status": "MISSING"})

    json_latest = {}
    for name, table in (("assets.json", "assets"), ("endpoints.json", "endpoints")):
        f = data_dir / name
        if not f.exists():
            rows.append({"artifact": name, "run_id": None, "mtime": None,
                         "expected_run": expected_run, "status": "MISSING"})
            continue
        try:
            records = json.loads(f.read_text())
        except Exception as e:
            rows.append({"artifact": name, "run_id": None, "mtime": f.stat().st_mtime,
                         "expected_run": expected_run, "status": f"MALFORMED ({e})"})
            overall = "STALE / OUT OF SYNC"
            continue
        latest = _latest_run_id(records) if records else None
        json_latest[table] = latest
        if expected_run is None:
            status = "UNKNOWN (no run_meta.json to compare against)"
        elif not records:
            status = "CONSISTENT (empty)"
        elif latest is None:
            status = "LEGACY (pre-run-ownership records only)"
        elif latest >= expected_run:
            # == : written by the same recon_pipeline.py run as run_meta.json.
            # >  : a later stage (js_miner.py) appended records with its own,
            #      newer run_id after run_meta.json was last written — expected.
            status = "CONSISTENT"
        else:
            status = "STALE / OUT OF SYNC (older than the last recorded run)"
            overall = "STALE / OUT OF SYNC"
        rows.append({"artifact": name, "run_id": latest, "mtime": f.stat().st_mtime,
                     "expected_run": expected_run, "status": status})

    db_file = data_dir / "recon.db"
    if not db_file.exists():
        rows.append({"artifact": "recon.db", "run_id": None, "mtime": None,
                     "expected_run": expected_run, "status": "MISSING"})
        return {"program": program, "overall": overall, "rows": rows}

    con = sqlite3.connect(db_file)
    cur = con.cursor()
    for table in ("assets", "endpoints"):
        try:
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        except sqlite3.OperationalError as e:
            rows.append({"artifact": f"recon.db:{table}", "run_id": None, "mtime": None,
                         "expected_run": expected_run, "status": f"ERROR: {e}"})
            continue
        if not cols:
            rows.append({"artifact": f"recon.db:{table}", "run_id": None,
                         "mtime": db_file.stat().st_mtime, "expected_run": expected_run,
                         "status": "MISSING (table not created yet)"})
            continue
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if "run_id" not in cols:
            status = "CONSISTENT (empty)" if n == 0 else "LEGACY (no run_id column — pre-dates run ownership)"
            db_latest = None
        else:
            db_run_ids = {r[0] for r in cur.execute(f"SELECT DISTINCT run_id FROM {table}").fetchall()}
            db_run_ids.discard(None)
            db_run_ids.discard("legacy")
            db_latest = max(db_run_ids) if db_run_ids else None
            src_latest = json_latest.get(table)
            if n == 0:
                status = "CONSISTENT (empty)"
            elif expected_run is None:
                status = "UNKNOWN (no run_meta.json to compare against)"
            elif src_latest and (db_latest is None or db_latest < src_latest):
                status = f"STALE / OUT OF SYNC (DB last synced {db_latest or 'legacy'}, source has {src_latest})"
                overall = "STALE / OUT OF SYNC"
            else:
                status = "CONSISTENT"
        rows.append({"artifact": f"recon.db:{table}", "run_id": db_latest,
                     "mtime": db_file.stat().st_mtime, "expected_run": expected_run, "status": status})
    con.close()

    return {"program": program, "overall": overall, "rows": rows}


def print_report(report: dict) -> None:
    print(f"[artifact_consistency] program={report['program']}")
    print(f"{'ARTIFACT':<20} {'RUN_ID':<26} {'MTIME':<20} {'EXPECTED_RUN':<26} STATUS")
    for r in report["rows"]:
        mtime_str = datetime.fromtimestamp(r["mtime"]).isoformat(timespec="seconds") if r["mtime"] else "-"
        print(f"{r['artifact']:<20} {str(r['run_id']):<26} {mtime_str:<20} {str(r['expected_run']):<26} {r['status']}")
    print()
    print(f"OVERALL: {report['overall']}")


def _selfcheck() -> None:
    import shutil
    import tempfile
    print("[artifact_consistency] Running selfcheck...")
    tmp = Path(tempfile.mkdtemp(prefix="artifact_consistency_selfcheck_"))
    try:
        # Case 1: everything freshly written by the same run -> CONSISTENT
        (tmp / "run_meta.json").write_text(json.dumps({"run_id": "run_20260101_000000_aaaaaa"}))
        (tmp / "assets.json").write_text(json.dumps([{"host": "a", "run_id": "run_20260101_000000_aaaaaa"}]))
        (tmp / "endpoints.json").write_text(json.dumps([{"url": "http://a", "run_id": "run_20260101_000000_aaaaaa"}]))
        con = sqlite3.connect(tmp / "recon.db")
        con.execute("CREATE TABLE assets (host TEXT, run_id TEXT)")
        con.execute("CREATE TABLE endpoints (url TEXT, run_id TEXT)")
        con.execute("INSERT INTO assets VALUES ('a', 'run_20260101_000000_aaaaaa')")
        con.execute("INSERT INTO endpoints VALUES ('http://a', 'run_20260101_000000_aaaaaa')")
        con.commit(); con.close()
        report = check_program("selfcheck", data_dir=tmp)
        assert report["overall"] == "CONSISTENT", f"expected CONSISTENT, got {report['overall']}"

        # Case 2: assets.json regenerated by a NEWER run, DB never resynced -> STALE
        (tmp / "run_meta.json").write_text(json.dumps({"run_id": "run_20260102_000000_bbbbbb"}))
        (tmp / "assets.json").write_text(json.dumps([{"host": "a", "run_id": "run_20260102_000000_bbbbbb"}]))
        report = check_program("selfcheck", data_dir=tmp)
        assert report["overall"] == "STALE / OUT OF SYNC", f"expected STALE, got {report['overall']}"
        db_row = next(r for r in report["rows"] if r["artifact"] == "recon.db:assets")
        assert "STALE" in db_row["status"], "DB row should be flagged stale"

        # Case 3: missing run_meta.json -> reported, not crashed
        (tmp / "run_meta.json").unlink()
        report = check_program("selfcheck", data_dir=tmp)
        assert report["rows"][0]["status"] == "MISSING"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("[artifact_consistency] selfcheck OK: consistent/stale/missing cases verified.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", help="program folder name")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    if not args.program:
        raise SystemExit("ERROR: --program required (or use --selfcheck)")

    report = check_program(args.program)
    print_report(report)
    raise SystemExit(0 if report["overall"] == "CONSISTENT" else 1)


if __name__ == "__main__":
    main()

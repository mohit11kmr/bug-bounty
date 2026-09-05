#!/usr/bin/env python3
"""
intelligence.py — Guide Phase 2b: priority scoring + SQLite candidate queue.

Input : recon/data/<program>/assets.json + endpoints.json (pipeline output)
Output: recon/data/<program>/recon.db (SQLite) + top_priority.json + report

Scoring (deterministic heuristics — guide §14 priority = severity + confidence + exposure):
  - Interestingness score 0-100 per endpoint (pattern-based, no LLM needed for Phase 2)
  - High-value surfaces: api docs, auth, admin, debug, config leaks, IDOR-prone params
  - Exposure: host status (200 vs 403) + endpoint count per host
  - candidate_findings queue: ready for Phase 3 manual/scan hooks
"""

import argparse
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # bug-bounty/
RECON = BASE / "recon"

# ---------------------------------------------------------------------------
# Deterministic endpoint scoring — pattern → score contribution
# ---------------------------------------------------------------------------

# (regex, weight, tag) — jab bhi match, weight add hota hai; tag first-match wins
RULES = [
    # --- API documentation / attack surface goldmines ---
    (r"swagger|openapi|api-docs|apidocs|redoc|graphql|/v[0-9]+/", 25, "api_surface"),
    # --- Config / secret leaks ---
    (r"\.env$|\.env\.|config\.(json|yaml|yml|php|js)$|/\.git|\.git/|backup|\.bak$",
     30, "config_leak"),
    # --- Auth & session ---
    (r"login|signin|oauth|token|auth|session|password|reset|register|logout|jwt|sso",
     20, "auth"),
    # --- Admin / internal surfaces ---
    (r"admin|internal|debug|test|staging|dev\.|console|dashboard|ops|manage|staff",
     20, "admin_internal"),
    # --- IDOR-prone API patterns (resource + id) ---
    (r"/(user|users|order|orders|account|profile|address|invoice|product|items?|"
     r"cart|payment|transaction|booking|ticket)/", 12, "resource"),
    (r"[?&](id|user_id|order_id|product_id|uid|account_id|invoice_id|token_id)=",
     15, "idor_param"),
    # --- File-based info / doc types ---
    (r"\.(json|xml|yaml|yml|sql|log|bak|txt|pdf|xls[x]?|csv)$", 5, "file"),
    (r"\.(js|js.map)$", 8, "javascript"),
    # --- Probes of interest ---
    (r"robots\.txt|sitemap|\.well-known|security\.txt", 6, "probe"),
    # --- Redirection / open-redirect flags ---
    (r"[?&](url|redirect|next|return|callback|dest|goto|ref|target)=", 10, "redirect"),
]

NEGATIVE = [
    # Homepage / static noise — de-duplicate weight (mild minus, not zero)
    (r"^https?://[^/]+/?$", -2, "homepage"),
    (r"\.(css|png|jpe?g|gif|svg|ico|woff2?|ttf|eot|map)$", -5, "asset"),
    (r"\.(woff|woff2|ttf|eot)", -5, "font"),
]


def score_url(url: str) -> tuple[int, str]:
    """Return (score 0-100, top_tag). First matching RULES tag wins; negatives subtract."""
    score = 0
    tag = "normal"
    for rx, w, t in RULES:
        if re.search(rx, url, re.IGNORECASE):
            score += w
            if tag == "normal":
                tag = t
    for rx, w, t in NEGATIVE:
        if re.search(rx, url, re.IGNORECASE):
            score += w
    return max(0, min(100, score)), tag


def host_weight(status) -> int:
    """Exposure: 200/30x > 401 > 403 > unresolvable."""
    if status in (200, 201, 202, 204):
        return 20
    if status in (301, 302, 303, 307, 308):
        return 15
    if status == 401:
        return 12
    if status == 403:
        return 8
    return 5


# ---------------------------------------------------------------------------
# SQLite — guide §8 data model
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    host TEXT PRIMARY KEY,
    url TEXT, ip TEXT, status INTEGER, title TEXT,
    technologies TEXT, source TEXT, first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS endpoints (
    url TEXT PRIMARY KEY,
    host TEXT, method TEXT, source TEXT, auth_hint TEXT,
    score INTEGER, tag TEXT, first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS candidate_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT, host TEXT, method TEXT,
    tag TEXT, score INTEGER, status TEXT DEFAULT 'triage',  -- triage|valid|invalid|duplicate
    confidence REAL DEFAULT 0.0,
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT,
    UNIQUE(url, tag)
);
CREATE INDEX IF NOT EXISTS idx_endpoints_score ON endpoints(score DESC);
CREATE INDEX IF NOT EXISTS idx_cands_status ON candidate_findings(status);
"""


def write_candidate_report(program: str, data_dir: Path, con: sqlite3.Connection, limit: int = 25) -> None:
    """Human-readable candidate queue (deduped by surface)."""
    rows = con.execute(
        "SELECT url, host, tag, score FROM candidate_findings ORDER BY score DESC").fetchall()
    # dedupe: redirect-query variants normalize kar ke unique surface
    seen = {}
    for url, host, tag, score in rows:
        path = re.sub(r"^https?://[^/]+", "", url)
        path = re.sub(r"[?&](redirect|next|return|callback|goto|ref|target)=[^&#]*", "", path)
        key = (host, path, tag)
        if key not in seen or score > seen[key][0]:
            seen[key] = (score, url, tag)
    top = sorted(seen.values(), key=lambda x: -x[0])[:limit]
    lines = [
        f"# {program.title()} — Candidate Finding Queue (Phase 2b)",
        "",
        "> Generated by recon/intelligence.py — deterministic scoring (no LLM).",
        "> Status: **triage** — har entry manually validate karo (in-scope, repro, impact).",
        "",
        f"Total candidates in DB: {len(rows)} | Deduped surfaces: {len(seen)}",
        "",
    ]
    for score, url, tag in top:
        lines.append(f"- [{score:3}] **{tag}** `{url}`")
    out = data_dir / "candidate_report.md"
    out.write_text("\n".join(lines))
    print(f"[intel] report -> {out.relative_to(BASE)} ({len(top)} surfaces)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default="meesho")
    ap.add_argument("--top", type=int, default=40, help="kitte top endpoints report me")
    args = ap.parse_args()

    data_dir = RECON / "data" / args.program
    assets = json.loads((data_dir / "assets.json").read_text())
    endpoints = json.loads((data_dir / "endpoints.json").read_text())

    # host -> exposure
    status_map = {}
    for a in assets:
        status_map[a["host"]] = a.get("status")
    for u in endpoints:
        url = u["url"]
        m = re.match(r"https?://([^/:]+)", url)
        if m and m.group(1).lower() not in status_map:
            status_map[m.group(1).lower()] = None

    scored = []
    for u in endpoints:
        url = u["url"]
        base = re.match(r"https?://([^/:]+)", url)
        host = base.group(1).lower() if base else "?"
        s, tag = score_url(url)
        total = s + host_weight(status_map.get(host))
        scored.append({**u, "host": host, "score": total, "tag": tag})

    scored.sort(key=lambda x: x["score"], reverse=True)

    # persistence
    db_path = data_dir / "recon.db"
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    cur.execute("DELETE FROM assets")
    cur.execute("DELETE FROM endpoints")
    now = date.today().isoformat()
    for a in assets:
        cur.execute(
            "INSERT OR REPLACE INTO assets VALUES (?,?,?,?,?,?,?,?,?)",
            (a["host"], a.get("url",""), a.get("ip",""), a.get("status"),
             a.get("title",""), ",".join(a.get("technologies",[])),
             ",".join(a.get("source",[])), a.get("first_seen"), a.get("last_seen")))
    for x in scored:
        cur.execute(
            "INSERT OR REPLACE INTO endpoints VALUES (?,?,?,?,?,?,?,?,?)",
            (x["url"], x["host"], x["method"], ",".join(x["source"]),
             x["auth_hint"], x["score"], x["tag"], x["first_seen"], x["last_seen"]))
    # candidate queue refresh: sirf endpoint-scored 'triage' rows nikalo.
    # Scanner/nuclei findings (vuln_* tags) aur human-triaged rows (valid/duplicate/wontfix)
    # PRESERVE karo — intelligence.py ka kaam koi nuclear wipe nahi.
    cur.execute("DELETE FROM candidate_findings WHERE status='triage' AND tag NOT LIKE 'vuln_%'")
    seen = set()
    for x in scored:
        if x["score"] >= 40 and (x["url"], x["tag"]) not in seen:
            seen.add((x["url"], x["tag"]))
            cur.execute(
                "INSERT INTO candidate_findings "
                "(url,host,method,tag,score,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'triage',?,?) "
                "ON CONFLICT(url, tag) DO NOTHING",
                (x["url"], x["host"], x["method"], x["tag"], x["score"], now, now))
    con.commit()

    top = scored[:args.top]
    top_simple = [{"score": x["score"], "tag": x["tag"], "url": x["url"]} for x in top]
    (data_dir / "top_priority.json").write_text(json.dumps(top_simple, indent=2))

    n_cands = cur.execute("SELECT COUNT(*) FROM candidate_findings").fetchone()[0]
    print(f"[intel] program={args.program}")
    print(f"[intel] assets={len(assets)} endpoints={len(scored)} db={db_path.name}")
    print(f"[intel] candidate_findings (score>=40): {n_cands}")
    print(f"[intel] top {args.top} saved -> top_priority.json")
    tag_counts = {}
    for x in scored:
        tag_counts[x["tag"]] = tag_counts.get(x["tag"], 0) + 1
    print(f"[intel] tag distribution: {dict(sorted(tag_counts.items(), key=lambda kv: -kv[1]))}")

    write_candidate_report(args.program, data_dir, con, args.top)
    con.close()


if __name__ == "__main__":
    main()
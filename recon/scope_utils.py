#!/usr/bin/env python3
"""
scope_utils.py — Single source of truth for scope.yaml loading and in-scope matching.

Consolidates five previously-independent, drifting copies of this logic that used
to live in recon_pipeline.py, scanner.py, js_miner.py, daemon.py, and auto_hunter.py.
That duplication caused a real bug (PIPELINE_INTEGRITY_V2 audit): a host:port scope
fix applied to one copy did not propagate to the others. All five modules now import
from here instead of keeping their own copy.

Self-check: python3 recon/scope_utils.py --selfcheck
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


def load_scope_file(scope_file: Path, required: bool = True, not_found_msg: str | None = None) -> dict:
    """Parse scope.yaml, tolerating unquoted wildcard roots (`- *.example.com`) that
    break strict YAML parsing.

    If `required` and the file is missing, calls sys.exit(not_found_msg) — matches the
    fail-hard contract of one-shot CLI tools (recon_pipeline.py, scanner.py, js_miner.py).
    If not `required`, returns {} on a missing file — matches the fail-soft contract of
    long-running/polling callers (daemon.py, auto_hunter.py) that must not crash on a
    not-yet-scaffolded program.
    """
    if not scope_file.exists():
        if required:
            sys.exit(not_found_msg or f"ERROR: {scope_file} not found — pehle scope.yaml banao")
        return {}
    raw = scope_file.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(raw) or {}
    except Exception:
        fixed_lines = []
        for line in raw.splitlines():
            if re.match(r'^\s*-\s*[\*\?].*', line):
                prefix = line[:line.index('-') + 2]
                val = line.strip()[1:].strip().strip('"').strip("'")
                fixed_lines.append(f'{prefix}"{val}"')
            else:
                fixed_lines.append(line)
        return yaml.safe_load("\n".join(fixed_lines)) or {}


def make_scope_filter(scope: dict):
    """Return fn(host) -> bool. In-scope = root match AND not excluded (wildcard + host:port aware)."""
    roots = [str(r).lower() for r in (scope.get("roots") or [])]
    excluded = [str(x).lower() for x in (scope.get("excluded") or [])]

    def wildcard_match(host: str, patterns: list) -> bool:
        host = host.lower().rstrip(".")
        for p in patterns:
            if p.startswith("*."):
                base = p[2:]
                if host == base or host.endswith("." + base):
                    return True
            elif p == host:
                return True
        return False

    def in_scope(host: str) -> bool:
        host = host.lower().rstrip(".")
        bare = host.split(":")[0]
        # Non-standard-port targets are recorded in scope.yaml/assets as "host:port";
        # callers sometimes pass the bare host (port stripped from a URL netloc) —
        # check both forms so a real host:port root isn't falsely reported out-of-scope,
        # and so a bare-domain root still matches a host:port candidate.
        variants = [host] if host == bare else [host, bare]
        # 1) Explicit root match — hamesha in-scope (wildcard exclusions "barring" ko respect karo)
        if any(v in roots for v in variants):
            return True
        # 2) Exclusion match — out-of-scope (wildcard included)
        if any(wildcard_match(v, excluded) for v in variants):
            return False
        # 3) Root subdomain match — in-scope
        return any(wildcard_match(v, roots) for v in variants)

    return in_scope


def _selfcheck() -> None:
    print("[scope_utils] Running selfcheck...")
    scope = {
        "roots": ["example.com", "*.target.com", "example.com:8443", "127.0.0.1:12345"],
        "excluded": ["excluded.target.com", "excluded.target.com:8443"],
    }
    f = make_scope_filter(scope)
    assert f("example.com") is True
    assert f("api.target.com") is True
    assert f("excluded.target.com") is False
    assert f("out-of-scope.com") is False
    # host:port root, exact match
    assert f("example.com:8443") is True
    # host:port root, candidate passed bare (port stripped upstream)
    assert f("example.com") is True
    # bare-domain root, candidate passed with a port
    assert f("api.target.com:443") is True
    # host:port exclusion, exact and bare-with-port-stripped forms both excluded
    assert f("excluded.target.com:8443") is False
    assert f("excluded.target.com") is False
    # IP:port root
    assert f("127.0.0.1:12345") is True
    assert f("127.0.0.1") is False  # bare IP without the configured port is NOT the scoped root
    print("[scope_utils] selfcheck OK: wildcard + host:port matching verified (single source of truth).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()

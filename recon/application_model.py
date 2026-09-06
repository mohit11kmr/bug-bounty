#!/usr/bin/env python3
"""
application_model.py — attack-surface understanding layer.

Input : recon/data/<program>/endpoints.json (pipeline output)
Output: recon/data/<program>/application_model.json

Deterministic heuristics — no LLM. URL path parts se:
  - actors      (login/admin/panel/dashboard segments + generic role words)
  - objects     (resource nouns: order, user, catalog, invoice, file, ...)
  - actions     (create/update/delete/export/refund/invite/login/logout)
  - sensitive params (id, user_id, order_id, role, ...)
  - auth-required surfaces (admin/panel/dashboard paths)

Human can then edit application_model.json to refine the object/ownership graph
(through `manual://` markers). The file is the bridge between "URLs collected" and
"app understood" — the missing layer the hypothesis engine consumes.

STATUS (PIPELINE_INTEGRITY_V2 audit): CONNECTED, but not to the deterministic Python
pipeline (intelligence.py/auto_hunter.py/scanner.py never parse this file — they don't
need to, their own scoring is independent). It is consumed by the `prob-hunter`
OpenCode agent (~/.config/opencode/agents/prob-hunter.md, invoked manually as
`@prob-hunter`, see WORKFLOW.md §6) as a secondary input alongside candidate_report.md
for actor/object ownership priors (BOLA/IDOR scoring). It is regenerated automatically
here and in js_miner.py whenever endpoints.json exists — invoking @prob-hunter is a
separate, human-triggered step, not something the default OpenCode handoff does itself.

Self-check: python3 recon/application_model.py --selfcheck
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RECON = BASE / "recon"

SELFCHECK_URLS = [
    "https://supplier.meesho.com/panel/v3/new/order/123",
    "https://api.meesho.com/api/orders/456?user_id=7",
    "https://meesho.com/admin/dashboard/export",
    "https://static.meesho.com/js/bundle.js",
]


def _selfcheck() -> None:
    m = collect(SELFCHECK_URLS)
    assert "supplier" in m["actors"]["observed"], "supplier actor miss"
    assert m["objects"]["observed"].get("order", 0) >= 1, "order object miss"
    assert "export" in m["actions"]["observed"], "export action miss"
    assert "user_id" in m["sensitive_params"], "user_id param miss"
    assert any("admin" in p for p in m["auth_surfaces"]), "admin auth surface miss"
    count_urls = len(SELFCHECK_URLS)
    for act in m["actions"]["observed"]:
        assert m["actions"]["observed"][act] <= count_urls, f"action {act} overcounts (double-slash regex bug)"
    print("selfcheck OK: actors/objects/actions/params/auth_surfaces all detected, no overcount")


# URL path segment -> role bucket. First-match wins (ordered).
ROLE_PATTERNS = [
    ("admin",     [r"(^|/|\.)(admin|staff|ops|manage)(/|\.|$|_)"]),
    ("supplier",  [r"(^|/|\.)(supplier|seller|partner|vendor)(/|\.|$|_)"]),
    ("affiliate", [r"(^|/|\.)(affiliate)(/|\.|$|_)"]),
    ("consumer",  [r"(^|/|\.)(user|users|account|profile|customer|me)(/|\.|$|_)"]),
]

# resource nouns (object) detection — path segments / query values
OBJECT_WORDS = {
    "order": [r"(^|/)(order|orders)(/|$|_)"],
    "catalog": [r"(^|/)(catalog|catalogs|product|products|sku|inventory)(/|$|_)"],
    "invoice": [r"(^|/)(invoice|invoices|bill|receipt)(/|$|_)"],
    "user": [r"(^|/)(user|users|account|profile|customer|address)(/|$|_)"],
    "payment": [r"(^|/)(payment|payments|transaction|transactions|refund)(/|$|_)"],
    "file": [r"(^|/)(file|files|upload|download|media|image|images|doc)(/|$|_)"],
    "fulfillment": [r"(^|/)(shipment|shipping|fulfill|delivery|logistic|track)(/|$|_)"],
    "reviews": [r"(^|/)(review|reviews|rating|ratings|comment)(/|$|_)"],
    "coupon": [r"(^|/)(coupon|coupons|promo|promotion|voucher|offer)(/|$|_)"],
}

ACTION_WORDS = [
    "create", "add", "new", "update", "edit", "modify", "patch",
    "delete", "remove", "cancel", "bulk",
    "export", "download", "upload", "import",
    "refund", "pay", "checkout", "return",
    "invite", "approve", "reject", "assign", "share", "change-password",
    "login", "logout", "register", "signup", "verify", "reset",
]

SENSITIVE_PARAMS = ["id", "user_id", "order_id", "product_id", "account_id",
                    "invoice_id", "token_id", "role", "org", "organization",
                    "shop_slug", "supplier_id", "affiliate_id", "redirect",
                    "next", "url", "return", "callback", "download", "file", "path"]


def collect(paths: list[str]) -> dict:
    actors, objects, actions, params, auth_surfaces = Counter(), Counter(), Counter(), Counter(), Counter()
    for u in paths:
        low = u.lower().split("?")[0]
        # auth surface: panel/admin/dashboard/console/manage
        if re.search(r"(^|/)(panel|admin|dashboard|console|staff|ops|manage)(/|$|_)", low):
            auth_surfaces[low] += 0  # count unique once below
        # role bucket
        for role, pats in ROLE_PATTERNS:
            if any(re.search(p, low) for p in pats):
                actors[role] += 1
                break
        # object words in path
        for obj, pats in OBJECT_WORDS.items():
            if any(re.search(p, low) for p in pats):
                objects[obj] += 1
        # actions in path
        for a in ACTION_WORDS:
            if re.search(r"(?:^|/|[-_])" + re.escape(a) + r"(?:/|$|[-_])", low):
                actions[a] += 1
        # sensitive params in query string
        q = u.split("?", 1)[1] if "?" in u else ""
        if q:
            for p in re.findall(r"([\w-]+)=", q):
                if p in SENSITIVE_PARAMS:
                    params[p] += 1

    # unique auth paths (not counts)
    auth_paths = sorted({re.sub(r"(\?.*|:[\d]+|/\d+.*$)", "", p)
                         for p in [x for x in paths if re.search(
                             r"(^|/)(panel|admin|dashboard|console|staff|ops|manage)(/|$|_)", x.lower())]})
    return {
        "actors": {
            "observed": {k: v for k, v in actors.most_common() if v},
            "note": "auto-checklist hai — human refine karo (manual:// toggle)",
        },
        "objects": {
            "observed": {k: v for k, v in objects.most_common() if v},
        },
        "actions": {
            "observed": {k: v for k, v in actions.most_common() if v},
        },
        "sensitive_params": {k: v for k, v in params.most_common()},
        "auth_surfaces": auth_paths,
        "ownership_graph": {
            "template": "Human-defined. Fill: actor -> object (e.g. supplier -> order)",
            "value": [],
        },
        "workflow_states": {
            "template": "Human-defined. Fill: [current] -> [next] transitions worth testing",
            "value": [],
        },
        "generated_by": "application_model.py (deterministic, no LLM)",
        "refine_manually": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default="meesho")
    ap.add_argument("--selfcheck", action="store_true", help="run self-check and exit")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    data_dir = RECON / "data" / args.program
    ep_file = data_dir / "endpoints.json"
    if not ep_file.exists():
        raise SystemExit(f"ERROR: {ep_file} nahi mila — pehle recon_pipeline chalao")

    endpoints = json.loads(ep_file.read_text())
    urls = [e.get("url", "") for e in endpoints]
    model = collect(urls)

    out = data_dir / "application_model.json"
    out.write_text(json.dumps(model, indent=2, ensure_ascii=False))
    print(f"[model] wrote {out.relative_to(BASE)}")
    print(f"[model] actors={list(model['actors']['observed'])}")
    print(f"[model] objects={list(model['objects']['observed'])}")
    print(f"[model] actions={list(model['actions']['observed'])[:15]}")
    print(f"[model] auth_surfaces={len(model['auth_surfaces'])}")
    if model["refine_manually"]:
        print("[model] NOTE: ownership_graph + workflow_states human edit ke liye empty hain — hypothesis engine tabhi full hota hai jab ye bhar jaaye")


if __name__ == "__main__":
    main()

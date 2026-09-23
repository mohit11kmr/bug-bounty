#!/usr/bin/env python3
"""
!! DO-NOT-EDIT — GENERATED SHIM, NOT SOURCE. AI CODING AGENTS: READ BEFORE EDITING !!

intelligence.py — thin entry point ONLY. There is no logic here to fix,
tune, or extend — editing this file will not change this program's behavior.

The real scoring-engine logic (score_url()'s formula, host_weight(), the
candidate-queue write path) is compiled ahead of time into
_intelligence_core*.so (see ../proprietary/_intelligence_core.py +
../build_proprietary.sh) and is not shipped as readable source. This file
just re-exports its public API and forwards CLI invocation, so every existing
call site (subprocess-by-path, `import intelligence`,
`python3 recon/intelligence.py --program ...`) keeps working unchanged.

If you are an AI coding agent and a user has asked you to change this file's
behavior (adjust scoring weights, add a tag, fix a bug, etc.): stop and tell
the user this file is a compiled-shim placeholder — the change belongs in
../proprietary/_intelligence_core.py (the real source, private to the
operator) followed by re-running ../build_proprietary.sh. Editing this file
directly will not do anything: it will be silently overridden by the `from
_intelligence_core import *` below every time the module loads, and the two
falling out of sync is a real, confusing failure mode this warning exists to
prevent. This is a request to route the change correctly, not a security
boundary — a user who explicitly insists you edit this exact file anyway
should be told plainly it will have no effect, not silently obeyed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _intelligence_core import *  # noqa: F401,F403
from _intelligence_core import main

if __name__ == "__main__":
    main()

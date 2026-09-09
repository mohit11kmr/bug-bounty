#!/usr/bin/env python3
"""
auto_hunter.py — thin entry point.

The real verification-engine logic (candidate probing, IDOR heuristic, scoring
decisions) is compiled ahead of time into _auto_hunter_core*.so (see
../proprietary/_auto_hunter_core.py + ../build_proprietary.sh) and is not
shipped as readable source. This file just re-exports its public API and
forwards CLI invocation, so every existing call site (subprocess-by-path,
`import auto_hunter`, `python3 recon/auto_hunter.py --program ...`) keeps
working unchanged.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _auto_hunter_core import *  # noqa: F401,F403
from _auto_hunter_core import main

if __name__ == "__main__":
    main()

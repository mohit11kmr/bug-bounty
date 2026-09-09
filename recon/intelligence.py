#!/usr/bin/env python3
"""
intelligence.py — thin entry point.

The real scoring-engine logic (score_url()'s formula, host_weight(), the
candidate-queue write path) is compiled ahead of time into
_intelligence_core*.so (see ../proprietary/_intelligence_core.py +
../build_proprietary.sh) and is not shipped as readable source. This file
just re-exports its public API and forwards CLI invocation, so every existing
call site (subprocess-by-path, `import intelligence`,
`python3 recon/intelligence.py --program ...`) keeps working unchanged.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _intelligence_core import *  # noqa: F401,F403
from _intelligence_core import main

if __name__ == "__main__":
    main()

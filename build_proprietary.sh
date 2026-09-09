#!/usr/bin/env bash
# =============================================================================
# Compiles the real verification/scoring logic (kept OUTSIDE the distributed
# repo, in proprietary/ — gitignored, never committed) into .so extension
# modules dropped into recon/. Customers/collaborators who get the repo get a
# working binary but never the readable source for these two files.
#
# Run this yourself (the operator) whenever proprietary/_auto_hunter_core.py
# or proprietary/_intelligence_core.py change, then commit the resulting
# recon/_auto_hunter_core*.so + recon/_intelligence_core*.so (they ARE meant
# to be tracked — see .gitignore's negation for them).
#
# Requires a build-only Cython venv (not needed at runtime by end users —
# they just get the prebuilt .so). Creates one at .build_venv/ if missing.
# =============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d proprietary ] || [ ! -f proprietary/_auto_hunter_core.py ] || [ ! -f proprietary/_intelligence_core.py ]; then
  echo "ERROR: proprietary/_auto_hunter_core.py and/or proprietary/_intelligence_core.py not found." >&2
  echo "       This script only compiles them — it doesn't have a copy to fall back on." >&2
  exit 1
fi

VENV=".build_venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "[1/4] Creating build-only venv at $VENV/ (Cython is a build dependency, not shipped to users)..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet cython setuptools
else
  echo "[1/4] Reusing existing build venv at $VENV/"
fi

echo "[2/4] Compiling proprietary/_auto_hunter_core.py + _intelligence_core.py -> .so..."
"$VENV/bin/python" - <<'PYEOF'
from setuptools import setup
from Cython.Build import cythonize
import sys
sys.argv = ["setup.py", "build_ext", "--inplace"]
setup(
    ext_modules=cythonize(
        ["proprietary/_auto_hunter_core.py", "proprietary/_intelligence_core.py"],
        compiler_directives={"language_level": "3"},
    ),
    script_args=["build_ext", "--inplace"],
)
PYEOF

echo "[3/4] Moving compiled .so into recon/ (removing any previous version)..."
# cythonize's build_ext --inplace drops these at the project root (the .py
# sources have no package/__init__.py, so setuptools treats them as
# top-level modules) — not inside proprietary/. Look in both places to be safe.
rm -f recon/_auto_hunter_core*.so recon/_intelligence_core*.so
for f in _auto_hunter_core*.so _intelligence_core*.so proprietary/_auto_hunter_core*.so proprietary/_intelligence_core*.so; do
  [ -f "$f" ] && mv "$f" recon/
done

echo "[4/4] Stripping debug symbols + cleaning intermediate build files..."
strip --strip-debug recon/_auto_hunter_core*.so recon/_intelligence_core*.so 2>/dev/null || true
rm -f proprietary/_auto_hunter_core.c proprietary/_intelligence_core.c
rm -rf build/

echo ""
echo "✓ Done. recon/ now has:"
ls -la recon/_auto_hunter_core*.so recon/_intelligence_core*.so
echo ""
echo "Commit these two .so files (they're the shipped product for this logic)."
echo "proprietary/*.py stays local only — .gitignore keeps it out of every commit."

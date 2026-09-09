#!/usr/bin/env bash
# =============================================================================
# One-command dependency installer for the bug-bounty tool.
# Installs the recon tools this launcher actually needs (see
# recon/recon_pipeline.py's TOOLS list + scanner.py's katana/nuclei usage) so a
# new customer doesn't have to hunt down each Go-install command themselves.
#
# Usage: ./install_dependencies.sh
# Tested target: Ubuntu/Debian. Other distros: install the equivalent packages
# for python3, git, and Go 1.21+ yourself, then re-run — the Go-install steps
# below are distro-agnostic.
# =============================================================================
set -euo pipefail

echo "=== Bug Bounty Tool — Dependency Installer ==="
echo ""

# ---- 1. Core system packages ----
if command -v apt-get >/dev/null 2>&1; then
  echo "[1/3] Installing python3, git, golang via apt..."
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-pip git golang-go
else
  echo "[1/3] apt-get not found — install python3, git, and Go 1.21+ yourself, then re-run this script."
  echo "      (This installer only automates the Go-based recon tools below.)"
fi

# ---- 2. ProjectDiscovery + gau recon tools ----
echo ""
echo "[2/3] Installing recon tools (subfinder, dnsx, httpx, gau, katana, nuclei)..."
export PATH="$PATH:$(go env GOPATH 2>/dev/null)/bin:$HOME/go/bin"
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/lc/gau/v2/cmd/gau@latest

GOBIN="$(go env GOPATH 2>/dev/null)/bin"
echo ""
echo "[3/3] Adding $GOBIN to PATH (this shell + ~/.bashrc for future shells)..."
if ! grep -qF "$GOBIN" "$HOME/.bashrc" 2>/dev/null; then
  echo "export PATH=\"\$PATH:$GOBIN\"" >> "$HOME/.bashrc"
fi
export PATH="$PATH:$GOBIN"

echo ""
echo "=== Verifying installs ==="
missing=0
for t in subfinder dnsx httpx katana nuclei gau python3 git; do
  if command -v "$t" >/dev/null 2>&1; then
    printf "  ✓ %-12s %s\n" "$t" "$(command -v "$t")"
  else
    printf "  ✗ %-12s NOT FOUND\n" "$t"
    missing=1
  fi
done

echo ""
if [ "$missing" -eq 0 ]; then
  echo "✓ All core tools installed. Open a NEW terminal (or 'source ~/.bashrc') then run ./start-bugbounty.sh"
else
  echo "⚠ Some tools are missing — check the errors above and re-run, or install them manually."
  echo "  See SECURITY_TOOLS_GUIDE.md for per-tool manual install instructions."
fi

echo ""
echo "=== Optional (not required to start) ==="
echo "- Docker (for wpscan integration): sudo apt install docker.io && sudo systemctl enable --now docker"
echo "- WPScan API token (free): https://wpscan.com/register — set up via the launcher's [W] menu"

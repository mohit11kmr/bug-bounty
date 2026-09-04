#!/usr/bin/env bash
# Bug Bounty Workspace Launcher — click to open terminal with opencode
# opencode ka absolute path — login/non-login shell dono mein chalta hai
OPCODE_BIN="$HOME/.opencode/bin/opencode"
if [ ! -x "$OPCODE_BIN" ]; then
  OPCODE_BIN="$(command -v opencode 2>/dev/null)"
fi
if [ -z "$OPCODE_BIN" ]; then
  : "${XDG_DATA_HOME:=$HOME/.local/share}"
  OPCODE_BIN="$XDG_DATA_HOME/opencode/bin/opencode"
  [ -x "$OPCODE_BIN" ] || OPCODE_BIN="opencode"
fi

cd "$HOME/Desktop/projects/bug-bounty" || exit 1
exec xfce4-terminal \
  --title="Bug Bounty — opencode" \
  --geometry=120x34 \
  --working-directory="$HOME/Desktop/projects/bug-bounty" \
  -e "bash -lc 'exec \"$OPCODE_BIN\"; echo; echo \"[bug-bounty session ended — press Enter to close]\"; read'"

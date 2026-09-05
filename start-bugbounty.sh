#!/usr/bin/env bash
# =============================================================================
# Bug Bounty — Launcher
# Desktop click / terminal: two flows — Start NEW scan (agent-driven) ya
# Continue EXISTING target (session resume). Existing targets hamesha list.
# =============================================================================
set -uo pipefail

WS="$HOME/Desktop/projects/bug-bounty"
[ -n "${OPCODE_BIN:-}" ] && [ -x "$OPCODE_BIN" ] \
  || OPCODE_BIN="$HOME/.opencode/bin/opencode"
[ -x "$OPCODE_BIN" ] || OPCODE_BIN="$(command -v opencode 2>/dev/null)"
[ -n "$OPCODE_BIN" ] || OPCODE_BIN="opencode"

# ---- Colors ----
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; R=$'\e[0m'; B=$'\e[1m'

# ---- If no tty (desktop .desktop launch), self-wrap in a terminal ----
# ---- If no tty (desktop .desktop launch), self-wrap in a terminal ----
# (BASH_LAUNCHER_NOTTY=1 dekhkar bypass — testing me use hota hai)
if [ ! -t 1 ] && [ "${BASH_LAUNCHER_NOTTY:-0}" != "1" ]; then
  exec xfce4-terminal --title="Bug Bounty — Launcher" \
    --geometry=110x32 --working-directory="$WS" \
    -e "bash -lc 'exec \"$0\"'"
fi

cd "$WS" || exit 1

# =============================================================================
# Helpers
# =============================================================================
normalize_name() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr -s ' ' '_' | tr -cd 'a-z0-9_-'
}

# Targets = workspace root par folder jisme scope.yaml hai
existing_targets() {
  local d
  for d in "$WS"/*/; do
    [ -f "$d/scope.yaml" ] && basename "$d"
  done
}

create_target_folder() {
  local name="$1"
  local tdir="$WS/$name"
  mkdir -p "$tdir"
  if [ ! -f "$tdir/scope.yaml" ]; then
    cat > "$tdir/scope.yaml" <<'YAML'
# Program — Engagement Contract (machine-readable)
# Har session: H1 scope APIs se sync karo. Test-cred/password YAHAN kabhi nahi.
program:
  handle: "$PROGRAM"
  name: "$NAME"
  confirmed: false

roots: []
excluded: []
allowed:
  methods: [GET, HEAD, OPTIONS, POST]
  max_requests_per_minute: 60
  max_concurrency: 5
  destructive_actions: false
  sqlmap: "--batch --risk 1"
YAML
  fi
  [ -f "$tdir/SCOPE.md" ] || cat > "$tdir/SCOPE.md" <<MD
# $name — Program Scope

> launcher ne naya target folder banaya. Pehle kaam: H1 scope + exclusions verify,
> yahan roots/excluded fill karo, phir session shuru.
MD
  [ -f "$tdir/NOTES.md" ] || echo "# $name — Hunt Progress" > "$tdir/NOTES.md"
}

# =============================================================================
# Flow 1 — Start NEW scan (agent-driven target discovery)
# =============================================================================
new_scan() {
  echo ""
  echo "${B}${C}=== START NEW SCAN ===${R}"
  echo "  (agent naya target dhoondh raha hai — HackerOne programs scan,"
  echo "   workspace me jo already hain wo skip)"
  echo ""

  # OpenRouter credits na ho to agent dispatch fail ho sakta hai — confirm first
  local out
  echo "${Y}[*] hackerone-analyst scanning programs...${R}"
  out="$(timeout 240 "$OPCODE_BIN" run --agent hackerone-analyst \
    'NEW TARGET SCAN (launcher se): HackerOne programs scan karo.
     Rule 1: `hackerone_list_programs` chalao.
     Rule 2: workspace existing targets ko SKIP karo (folders jisme scope.yaml hai:
       '"$(existing_targets | tr '\n' ' ')"').
     Rule 3: SIRF naye candidates return karo, strictly is format me, HARD STOP:
       <handle> | <program name>
     Har line me exactly ek ` | ` separator. Koi commentary, numbering, ya markdown nahi.
     Agar koi naya candidate nahi mila to `NONE` print karo.' 2>&1)"

  # Parse: "handle | name" lines
  local candidates=() detail line handle name
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*([a-zA-Z0-9._-]+)[[:space:]]*\|[[:space:]]*(.+)$ ]]; then
      handle="${BASH_REMATCH[1]}"; name="${BASH_REMATCH[2]}"
      candidates+=("$handle | $name")
    fi
  done <<< "$out"

  if [ "${#candidates[@]}" -eq 0 ]; then
    echo "  ${Y}❌ Koi naya candidate parse nahi hua. Agent raw output:${R}"
    echo "$out" | tail -5
    echo ""
    read -r -p "  Dobara try? [Y/n]: " again
    [[ "$again" =~ ^[nN]$ ]] || new_scan
    return
  fi

  echo "  ${G}Naye candidates ($(printf '%s\n' "${candidates[@]}" | grep -c .)):${R}"
  local i=1 c
  for c in "${candidates[@]}"; do
    echo "    ${G}[$i]${R} ${B}$c${R}"
    i=$((i+1))
  done
  echo "    ${Y}[0]${R} Cancel"

  echo ""
  local sel
  read -r -p "  Select number: " sel

  if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -lt "$i" ]; then
    local handle="${candidates[$((sel-1))]%% | *}"
    local fname dup
    fname="$(normalize_name "$handle")"
    # Duplicate guard: fuzzy vs existing folders
    dup=""
    while IFS= read -r t; do
      [ "$(normalize_name "$t")" = "$fname" ] && dup="$t" && break
    done < <(existing_targets)
    if [ -n "$dup" ]; then
      echo "  ${Y}⚠ '$fname' ka folder already hai ('$dup') — naya nahi banega.${R}"
      read -r -p "  Usi me open karun? [y/N]: " ans
      [[ "$ans" =~ ^[yY]$ ]] && cd "$WS/$dup"
      return
    fi
    create_target_folder "$fname"
    echo "  ${G}✓ Target folder banaya: ${C}$fname/${R}"
    echo ""
    echo "  ${Y}Ab SCOPE.md me roots/excluded bharne se pehle scope verify karo,${R}"
    echo "  phir session:"
    echo "    $ cd $WS/$fname && $OPCODE_BIN"
  else
    echo "  ${Y}Cancelled.${R}"
  fi
  return
}

# =============================================================================
# Flow 2 — Continue EXISTING target (session resume)
# =============================================================================
continue_target() {
  local targets=() t i=1 sel
  while IFS= read -r t; do targets+=("$t"); done < <(existing_targets)
  if [ "${#targets[@]}" -eq 0 ]; then
    echo "  ${Y}Koi existing target nahi (scope.yaml wala folder). Pehle [1] New scan use karo.${R}"
    return
  fi

  echo ""
  echo "${B}${C}=== EXISTING TARGETS — select karo ===${R}"
  for t in "${targets[@]}"; do
    echo "    ${G}[$i]${R} ${B}$t${R}"
    i=$((i+1))
  done
  echo "    ${Y}[0]${R} Cancel"
  echo ""
  read -r -p "  Select number: " sel

  if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -lt "$i" ]; then
    local pick="${targets[$((sel-1))]}"
    echo "  ${G}✓ Resume: ${C}$pick/${R}  (session continue ya new)"
    cd "$WS/$pick"
    if "$OPCODE_BIN" --continue 2>/dev/null; then
      :
    else
      exec "$OPCODE_BIN"
    fi
  else
    echo "  ${Y}Cancelled.${R}"
  fi
}

# =============================================================================
# Main menu
# =============================================================================
main_menu() {
  while true; do
    clear
    echo ""
    echo "  ${B}${C}╔══════════════════════════════════════════════╗${R}"
    echo "  ${B}${C}║        BUG BOUNTY — LAUNCHER                  ║${R}"
    echo "  ${B}${C}╚══════════════════════════════════════════════╝${R}"
    echo ""
    echo "  ${G}[1]${R} Start NEW scan   — agent naya target dhoonde"
    echo "  ${G}[2]${R} Continue EXISTING — session resume"
    echo "  ${G}[3]${R} Quit"
    echo ""
    echo "  ${Y}Current:${R} in-scope targets par hunting (nothing out-of-scope)"
    echo ""
    echo "  ${B}Existing targets in workspace:${R}"
    local t n=0
    while IFS= read -r t; do
      n=$((n+1))
      echo "      ${G}[$n]${R} $t"
    done < <(existing_targets)
    [ "$n" -eq 0 ] && echo "      (koi nahi — pehle [1] se naya scan start karo)"
    echo ""
    read -r -p "  Select: " choice

    case "$choice" in
      1) new_scan ;;
      2) continue_target ;;
      3) echo "  Bye."; exit 0 ;;
      *) echo "  Invalid — 1, 2, ya 3."; sleep 1 ;;
    esac
  done
}

main_menu
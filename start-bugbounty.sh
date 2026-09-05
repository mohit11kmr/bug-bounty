#!/usr/bin/env bash
# =============================================================================
# Bug Bounty — Launcher
# Desktop click / terminal: two flows — Start NEW scan (agent-driven) ya
# Continue EXISTING target (session resume).
# =============================================================================
set -uo pipefail

WS="$HOME/Desktop/projects/bug-bounty"
[ -n "${OPCODE_BIN:-}" ] && [ -x "$OPCODE_BIN" ] \
  || OPCODE_BIN="$HOME/.opencode/bin/opencode"
[ -x "$OPCODE_BIN" ] || OPCODE_BIN="$(command -v opencode 2>/dev/null)"
[ -n "$OPCODE_BIN" ] || OPCODE_BIN="opencode"

# ---- Colors ----
R=$'\e[0m'; B=$'\e[1m'; D=$'\e[2m'
G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; RED=$'\e[31m'
LINE=$'\e[38;5;245m'   # muted gray for borders
DIM=$'\e[90m'

# ---- If no tty (desktop launch) self-wrap in a terminal ----
# (BASH_LAUNCHER_NOTTY=1 bypasses wrap — testing)
if [ ! -t 1 ] && [ "${BASH_LAUNCHER_NOTTY:-0}" != "1" ]; then
  exec xfce4-terminal --title="Bug Bounty — Launcher" \
    --geometry=110x32 --working-directory="$WS" \
    -e "bash -lc 'exec \"$0\"'"
fi

cd "$WS" || exit 1

# =============================================================================
# UI primitives
# =============================================================================
W=52   # box inner width
sep()  { printf "${LINE}%s${R}\n" "$(printf '─%.0s' $(seq 1 "$W"))"; }
padl() { printf "%${1}s%s" "" "$2"; }          # right-pad helper (left spaces)
sp()   { printf ' %s ' "$1"; }

title_box() {  # centered title bar: title_box "text"
  local t="$1" pad
  pad=$(( (W - ${#t}) / 2 ))
  printf "${LINE}╭%s╮${R}\n" "$(printf '─%.0s' $(seq 1 "$W"))"
  printf "${LINE}│${R}%$((pad))s${B}${C}%s${R}%$((W - pad - ${#t}))s${LINE}│${R}\n" "" "$t" ""
  printf "${LINE}╰%s╯${R}\n" "$(printf '─%.0s' $(seq 1 "$W"))"
}

opt() {  # aligned menu row: opt "<num>" "<label>" "<desc>"
  printf "  ${G}%s${R}  ${B}%-26s${R}${DIM}%s${R}\n" "[$1]" "$2" "$3"
}

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
# Splash screen
# =============================================================================
splash() {
  clear
  echo ""
  echo "   ${C}██╗██╗██╗  ██████╗  ██████╗ ██╗██╗${R}"
  echo "   ${C}██╗██╗██║ ██╔═══██╗██╔═══██╗██║██║${R}"
  echo "   ${C}██╗██╗██║ ██║   ██║██████╔╝██║██║${R}"
  echo "   ${C}██║██║██║ ██║   ██║██╔═══██╗██║██║${R}"
  echo "   ${C}╚═╝╚═╝╚═╝ ╚██████╔╝██████╔╝╚═╝╚═╝${R}"
  echo "   ${C}████████████████████████████████████${R}"
  echo ""
  echo "   ${B}${C}     B U G   B O U N T Y — L A U N C H E R${R}"
  echo ""
  echo "   ${DIM}Workspace:${R}  $WS"
  echo "   ${DIM}Targets:${R}    $(existing_targets | grep -c .) active"
  echo "   ${DIM}Agent:${R}      hackerone-analyst (${D}HackerOne authorized hunting${R})"
  echo ""
  echo "   ${LINE}──────────────────────────────────────────────${R}"
  echo "   ${DIM}Legal first: SIRF in-scope targets.${R}"
  echo ""
  if [ "${BASH_LAUNCHER_SKIP_SPLASH:-0}" != "1" ]; then
    read -r -s -n1 -p "   Press Enter to continue..."
  fi
}

# =============================================================================
# Flow 1 — Start NEW scan (agent-driven target discovery)
# =============================================================================
new_scan() {
  echo ""
  title_box " START NEW SCAN "
  echo ""
  echo "  ${DIM}Agent naya target dhoondh raha hai —${R}"
  echo "  ${DIM}HackerOne programs scan honge, jo already${R}"
  echo "  ${DIM}workspace me hain wo skip.*${R}"
  echo ""

  local out
  echo "  ${Y}◌${R} hackerone-analyst scanning programs..."
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
    echo "  ${RED}✗ Koi naya candidate parse nahi hua.${R}"
    echo "$out" | tail -5
    echo ""
    read -r -p "  Dobara try? [${G}Y${R}/${DIM}n${R}]: " again
    [[ "$again" =~ ^[nN]$ ]] || new_scan
    return
  fi

  echo ""
  echo "  ${D}── naye candidates ───────────────────────────${R}"
  local i=1 c
  for c in "${candidates[@]}"; do
    printf "  ${B}${C}%2d${R}   %s\n" "$i" "$c"
    i=$((i+1))
  done
  printf "  ${D}%2s   %s${R}\n" "0" "Cancel"
  echo "  ${D}──────────────────────────────────────────────${R}"
  echo ""
  local sel
  read -r -p "  ${B}Select${R} [0-$((i-1))]: " sel

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
      echo ""
      echo "  ${Y}⚠`` '$fname' ka folder already hai ($dup).${R}"
      read -r -p "  Usi me open karun? [${G}y${R}/${DIM}N${R}]: " ans
      [[ "$ans" =~ ^[yY]$ ]] && cd "$WS/$dup"
      return
    fi
    create_target_folder "$fname"
    echo ""
    echo "  ${G}✓${R} ${B}Target folder banaya: ${C}$fname/${R}"
    echo ""
    echo "  ${DIM}Pehle SCOPE.md me roots/excluded verify karo,${R}"
    echo "  ${DIM}phir session:${R}"
    echo "    ${B}cd $WS/$fname && $OPCODE_BIN${R}"
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
  title_box " EXISTING TARGETS — SELECT "
  echo ""
  for t in "${targets[@]}"; do
    printf "  ${B}${C}%2d${R}   %s\n" "$i" "$t"
    i=$((i+1))
  done
  printf "  ${D}%2s   %s${R}\n" "0" "Cancel"
  echo ""
  read -r -p "  ${B}Select${R} [0-$((i-1))]: " sel

  if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -lt "$i" ]; then
    local pick="${targets[$((sel-1))]}"
    echo ""
    echo "  ${G}✓${R} ${B}Resume: ${C}$pick/${R}"
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
    title_box " BUG BOUNTY — LAUNCHER "
    echo ""
    echo "  ${B}Select an action:${R}"
    echo ""
    opt "1" "Start NEW scan"       "agent discovers new HackerOne target"
    opt "2" "Continue EXISTING"    "resume a hunt session"
    opt "3" "Quit"                 ""
    echo ""
    sep
    echo "  ${D}── existing targets ─────────────($(existing_targets | grep -c .))────────${R}"
    local t n=0
    while IFS= read -r t; do
      n=$((n+1))
      printf "     ${G}%2d${R}  %s\n" "$n" "$t"
    done < <(existing_targets)
    [ "$n" -eq 0 ] && echo "     ${DIM}(koi nahi — pehle [1] se naya scan start karo)${R}"
    echo ""
    read -r -p "  ${B}Your choice${R} [1-3]: " choice

    case "$choice" in
      1) new_scan ;;
      2) continue_target ;;
      3) echo "  Bye."; exit 0 ;;
      *) echo "  ${RED}Invalid — 1, 2, ya 3.${R}"; sleep 1 ;;
    esac
  done
}

splash
main_menu
#!/usr/bin/env bash
# =============================================================================
# TriagePilot — Mission Control & Autonomous Hunting Launcher (v1.0.0)
# High-Performance Terminal Suite for Authorized HackerOne Engagements.
# Features:
# - Live multi-step HackerOne program discovery (Cash Bounty vs All filter)
# - End-to-End Autonomous Hunt pipeline (Recon → JS Miner → Triage → Pre-filled Agent)
# - Real-time target metrics, pre-flight diagnostics, and recon diff engine.
# =============================================================================
set -uo pipefail

export PYTHONUNBUFFERED=1
# Derived from the script's own location — never hardcoded — so this launcher
# works for any user/company regardless of where they clone/install the repo.
WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- Load HackerOne Credentials (.env.h1) & Enforce Permissions ----
[ -f "$WS/.env.h1" ] && chmod 600 "$WS/.env.h1" 2>/dev/null || true
[ -f "$WS/.env.notify" ] && chmod 600 "$WS/.env.notify" 2>/dev/null || true
[ -f "$WS/.env.wpscan" ] && chmod 600 "$WS/.env.wpscan" 2>/dev/null || true
[ -f "$WS/.env.account" ] && chmod 600 "$WS/.env.account" 2>/dev/null || true

if [ -z "${H1_USERNAME:-}" ] || [ -z "${H1_API_TOKEN:-}" ]; then
  if [ -f "$WS/.env.h1" ]; then
    # shellcheck disable=SC1091
    source "$WS/.env.h1"
  elif [ -f "$HOME/.h1_env" ]; then
    # shellcheck disable=SC1091
    source "$HOME/.h1_env"
  fi
fi

[ -n "${OPCODE_BIN:-}" ] && [ -x "$OPCODE_BIN" ] \
  || OPCODE_BIN="$HOME/.opencode/bin/opencode"
[ -x "$OPCODE_BIN" ] || OPCODE_BIN="$(command -v opencode 2>/dev/null)"
[ -n "$OPCODE_BIN" ] || OPCODE_BIN="opencode"

# ---- Cyber Terminal Palette ----
R=$'\e[0m'; B=$'\e[1m'; D=$'\e[2m'; I=$'\e[3m'
CYAN=$'\e[38;5;51m'; BLUE=$'\e[38;5;39m'; PURPLE=$'\e[38;5;141m'
GREEN=$'\e[38;5;48m'; GOLD=$'\e[38;5;220m'; ORANGE=$'\e[38;5;208m'
RED=$'\e[38;5;196m'; MUTED=$'\e[38;5;244m'; BORDER=$'\e[38;5;239m'
LINE=$'\e[38;5;241m'

# ---- Desktop Auto-Wrap (Only for interactive double-click launch with 0 arguments) ----
if [ ! -t 1 ] && [ "$#" -eq 0 ] && [ "${BASH_LAUNCHER_NOTTY:-0}" != "1" ]; then
  exec xfce4-terminal --title="TriagePilot — Mission Control" \
    --geometry=120x36 --working-directory="$WS" \
    -e "bash -lc 'exec \"$0\"'"
fi

cd "$WS" || exit 1

# ---- Hard requirement check — fail with a clear message, not a cryptic
# mid-script crash, if the one non-negotiable dependency is missing ----
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install it first (e.g. 'sudo apt install python3') and re-run this launcher." >&2
  exit 1
fi

# ---- Account/subscription server — auto-start a LOCAL instance if no remote
# one is configured (ACCOUNT_SERVER_URL unset/default). This only ever touches
# localhost:8899, never a real deployed server — once ACCOUNT_SERVER_URL points
# somewhere real (see docs/deploy_account_server_gcp.sh), this is a no-op.
# Runs before any UI/color setup so it works identically for --auto/--daemon
# invocations too, where recon_pipeline.py's account-gate would otherwise hit
# the same "connection refused" this was built to prevent. ----
if [ -z "${ACCOUNT_SERVER_URL:-}" ] || [[ "$ACCOUNT_SERVER_URL" == *"127.0.0.1"* ]] || [[ "$ACCOUNT_SERVER_URL" == *"localhost"* ]]; then
  if ! python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('${ACCOUNT_SERVER_URL:-http://127.0.0.1:8899}/health', timeout=2)
except Exception:
    sys.exit(1)
" >/dev/null 2>&1; then
    secret_file="$WS/.env.account_admin"
    if [ ! -f "$secret_file" ]; then
      new_secret="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
      printf '# Admin secret for recon/account_client.py --admin-set-tier / --admin-reset-password.\n# Auto-generated on first local run. Never committed (.gitignore: **/.env.*).\nexport ACCOUNT_ADMIN_SECRET="%s"\n' "$new_secret" > "$secret_file"
      chmod 600 "$secret_file"
      echo "Generated a local admin secret at $secret_file (needed for tier upgrades after payment)."
    fi
    # shellcheck disable=SC1090
    source "$secret_file"
    export ACCOUNT_ADMIN_SECRET
    nohup python3 "$WS/recon/account_server.py" >> "$WS/.account_server.log" 2>&1 &
    disown 2>/dev/null || true
    sleep 1
  fi
fi

# =============================================================================
# UI Primitives & Centered Responsive Framing
# =============================================================================
W=82   # Frame width
PAD=0
P=""

_GEOM_LAST_USEC=0
_TERM_COLS=80

_term_cols_cached() {
  # sep()/title_box()/opt()/section_hdr()/center()/center_block() each call
  # this independently, and ONE screen redraw fires 10-30 of them back to
  # back with nothing blocking in between. A live window-maximize doesn't
  # send a single WINCH — the window manager animates it, firing several in
  # quick succession. If one lands between two draw calls of the SAME frame,
  # `tput cols` can report a DIFFERENT value mid-frame: some lines then get
  # the old (narrower) width, others get the new (wider) one — producing the
  # jagged "stale fragments on the left, live content shifted right" tear
  # seen on fullscreen/resize. A whole frame's draw calls run in well under
  # a millisecond of wall time (no I/O between them), so caching the queried
  # value for a short window guarantees every call within one frame reuses
  # the exact same number, while the very next frame still picks up a real
  # resize immediately (debounce window is far shorter than a human
  # keypress or the next loop iteration).
  #
  # NOTE: this sets the globals _TERM_COLS/_GEOM_LAST_USEC directly and must
  # be invoked as a plain statement (`_term_cols_cached`), never inside
  # `$(...)` — command substitution forks a subshell, and writes to those
  # globals from inside one never reach back out, silently breaking the
  # whole cache. Callers read the result from `$_TERM_COLS` afterward.
  local now_sec now_usec now_total
  now_sec="${EPOCHREALTIME%.*}"
  now_usec="${EPOCHREALTIME#*.}"
  now_total=$(( now_sec * 1000000 + 10#$now_usec ))
  if [ "$_GEOM_LAST_USEC" -gt 0 ] && [ $(( now_total - _GEOM_LAST_USEC )) -lt 150000 ]; then
    return
  fi

  local cols=""
  # tput cols queries the terminal driver directly, so it always reflects the
  # CURRENT window size (e.g. after going fullscreen). $COLUMNS is a shell
  # variable set once at startup — it goes stale on resize (bash only
  # refreshes it after a foreground command completes with checkwinsize on,
  # which isn't reliable inside a script's own read-loops), so it must only
  # be a fallback, never checked first.
  if command -v tput >/dev/null 2>&1; then
    cols="$(tput cols 2>/dev/null || true)"
  fi
  if [ -z "$cols" ] || [ "$cols" -le 0 ] 2>/dev/null; then
    if [ -n "${COLUMNS:-}" ] && [ "$COLUMNS" -gt 0 ] 2>/dev/null; then
      cols="$COLUMNS"
    fi
  fi
  if [ -z "$cols" ] || [ "$cols" -le 0 ] 2>/dev/null; then
    cols=80
  fi
  _TERM_COLS="$cols"
  _GEOM_LAST_USEC="$now_total"
}

update_geom() {
  _term_cols_cached
  local cols="$_TERM_COLS"

  if [ "$cols" -ge 96 ]; then
    W=84
  elif [ "$cols" -ge 84 ]; then
    W=80
  else
    W=$(( cols - 4 ))
  fi
  [ "$W" -lt 74 ] && W=74

  PAD=$(( (cols - W) / 2 ))
  [ "$PAD" -lt 0 ] && PAD=0
  P="$(printf '%*s' "$PAD" "")"
}

# Fullscreen/resize the terminal window while sitting on a menu (no keypress)
# and nothing redrew — update_geom() only recomputes W/PAD when SOMETHING
# calls it, and every menu screen only calls it at the top of its own loop,
# before the blocking `read` for the next choice. A resize mid-read never
# reached that point. Registering a real (non-empty) handler for SIGWINCH
# makes bash's `read` builtin return early the moment the terminal reports a
# resize — every menu loop here is `while true: update_geom; clear; draw;
# read; case; done`, so an interrupted read just falls through to the loop's
# next iteration and redraws with fresh geometry, with no key needed.
trap 'update_geom' WINCH

# Every screen in this script calls the plain `clear` builtin before
# redrawing. `clear` alone repaints only the terminal's currently-visible
# rows — on a fast resize/maximize it can race the terminal emulator's own
# internal repaint, or leave a stray strip of the previous (narrower) frame
# visible if the emulator hasn't finished settling into its new size yet.
# Shadowing `clear` with a function (bash resolves a bare command name to a
# function before PATH) upgrades every existing bare `clear` call in this
# file for free: home the cursor, wipe the visible screen AND the
# scrollback/saved-lines buffer (\033[3J), so no leftover glyphs from a
# stale width can survive into the next frame.
clear() {
  command clear
  printf '\033[H\033[2J\033[3J'
}

_char_len() {
  # Locale-INDEPENDENT character (codepoint) count. NEVER use bash's own
  # ${#var} for text that may contain multi-byte UTF-8 (the banner's
  # box-drawing art, emoji in menu labels, em-dashes) — bash's ${#var} only
  # counts codepoints correctly when the shell's own locale (LC_CTYPE) is
  # UTF-8-aware. This script is launched via `exec xfce4-terminal -e ...`
  # (see splash()/main_menu() call sites), and that spawned shell does not
  # reliably inherit the desktop session's LANG — a real, observed case: with
  # no/POSIX locale, ${#var} silently falls back to counting raw BYTES, so
  # an 84-character banner line reports as 222 bytes (each block-drawing
  # glyph is 3 bytes). That blows every center()/center_block()/title_box()
  # padding calculation negative, which clamps to 0 and renders flush-left
  # instead of centered — exactly the "banner won't center in fullscreen"
  # symptom this fixes. python3 is already a hard requirement for this whole
  # tool (checked earlier in this script) and always decodes its argv as
  # UTF-8 regardless of the parent shell's locale (PEP 538/540 C-locale
  # coercion — verified empirically even under `env -i`), so its len() is
  # correct no matter what locale xfce4-terminal's shell ends up with.
  python3 -c 'import sys; print(len(sys.argv[1]))' "$1"
}

sep() {
  update_geom
  printf "%s${LINE}%s${R}\n" "$P" "$(printf '─%.0s' $(seq 1 "$W"))"
}

title_box() {
  update_geom
  local title="$1" subtitle="${2:-}" pad pad2 inner_w=$W
  local clean_title clean_sub title_len sub_len
  clean_title="$(printf '%s' "$title" | sed 's/\x1b\[[0-9;]*m//g')"
  title_len="$(_char_len "$clean_title")"
  pad=$(( (inner_w - title_len) / 2 ))
  [ "$pad" -lt 0 ] && pad=0
  local rpad=$(( inner_w - pad - title_len ))
  [ "$rpad" -lt 0 ] && rpad=0

  printf "%s${BORDER}╭%s╮${R}\n" "$P" "$(printf '─%.0s' $(seq 1 "$inner_w"))"
  printf "%s${BORDER}│${R}%*s${B}${CYAN}%s${R}%*s${BORDER}│${R}\n" "$P" "$pad" "" "$title" "$rpad" ""
  if [ -n "$subtitle" ]; then
    clean_sub="$(printf '%s' "$subtitle" | sed 's/\x1b\[[0-9;]*m//g')"
    sub_len="$(_char_len "$clean_sub")"
    pad2=$(( (inner_w - sub_len) / 2 ))
    [ "$pad2" -lt 0 ] && pad2=0
    local rpad2=$(( inner_w - pad2 - sub_len ))
    [ "$rpad2" -lt 0 ] && rpad2=0
    printf "%s${BORDER}│${R}%*s${MUTED}%s${R}%*s${BORDER}│${R}\n" "$P" "$pad2" "" "$subtitle" "$rpad2" ""
  fi
  printf "%s${BORDER}╰%s╯${R}\n" "$P" "$(printf '─%.0s' $(seq 1 "$inner_w"))"
}

opt() {
  update_geom
  local key="$1" label="$2" desc="${3:-}"
  printf "%s  ${GREEN}%-5s${R} ${B}%-34s${R} ${MUTED}%s${R}\n" "$P" "[$key]" "$label" "$desc"
}

center() {
  local txt="$1" w len clean
  _term_cols_cached
  w="$_TERM_COLS"
  clean="$(printf '%s' "$txt" | sed 's/\x1b\[[0-9;]*m//g')"
  len="$(_char_len "$clean")"
  local ind=$(( (w - len) / 2 ))
  [ "$ind" -lt 0 ] && ind=0
  printf "%*s%s\n" "$ind" "" "$txt"
}

center_block() {
  local block="$1" color="$2" w max=0 len line lines=()
  _term_cols_cached
  w="$_TERM_COLS"
  while IFS= read -r line; do
    len="$(_char_len "$line")"
    [ "$len" -gt "$max" ] && max="$len"
    lines+=("$line")
  done <<< "$block"
  local indent=$(( (w - max) / 2 ))
  [ "$indent" -lt 0 ] && indent=0
  for line in "${lines[@]}"; do
    printf "%*s${color}%s${R}\n" "$indent" "" "$line"
  done
}

section_hdr() {
  update_geom
  local text="$1"
  local pad_len=$(( W - ${#text} - 6 ))
  [ "$pad_len" -lt 2 ] && pad_len=2
  printf "%s  ${MUTED}── %s %s${R}\n" "$P" "$text" "$(printf '─%.0s' $(seq 1 "$pad_len"))"
}

# =============================================================================
# Helper Utilities & Metrics Engine
# =============================================================================
normalize_name() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr -s ' ' '_' | tr -cd 'a-z0-9_-'
}

existing_targets() {
  local d
  for d in "$WS"/*/; do
    [ -f "$d/scope.yaml" ] && basename "$d"
  done
  return 0
}

target_stats() {
  local target="$1"
  local d="$WS/recon/data/$target"
  local a_file="$d/assets.json"
  local e_file="$d/endpoints.json"
  local db_file="$d/recon.db"
  local raw_hosts="$d/raw/hosts.txt"

  if [ "$target" = "general" ]; then
    printf "${MUTED}Local Lab / Practice${R}"
    return
  fi

  local n_assets=0 n_endpoints=0 n_cands=0 top_score=0
  if [ -s "$a_file" ]; then
    n_assets=$(grep -c '"host":' "$a_file" 2>/dev/null || true)
  fi
  if [ "$n_assets" -eq 0 ] 2>/dev/null && [ -s "$raw_hosts" ]; then
    n_assets=$(wc -l < "$raw_hosts" 2>/dev/null || true)
  fi
  n_assets="${n_assets%%$'\n'*}"
  [ -z "$n_assets" ] && n_assets=0

  if [ -s "$e_file" ]; then
    n_endpoints=$(grep -c '"url":' "$e_file" 2>/dev/null || true)
    n_endpoints="${n_endpoints%%$'\n'*}"
  fi
  [ -z "$n_endpoints" ] && n_endpoints=0

  if [ -f "$db_file" ] && command -v sqlite3 >/dev/null 2>&1; then
    local row
    row=$(sqlite3 "$db_file" "SELECT count(*), COALESCE(max(score), 0) FROM candidate_findings;" 2>/dev/null || echo "0|0")
    n_cands=$(echo "$row" | cut -d'|' -f1)
    top_score=$(echo "$row" | cut -d'|' -f2)
  fi
  n_cands="${n_cands%%$'\n'*}"
  [ -z "$n_cands" ] && n_cands=0
  top_score="${top_score%%$'\n'*}"
  [ -z "$top_score" ] && top_score=0

  if [ "$n_assets" -gt 0 ] || [ "$n_endpoints" -gt 0 ]; then
    printf "${GREEN}🟢 %s hosts${R} · ${CYAN}%s URLs${R} · ${GOLD}%s cands${R} ${MUTED}(Top: %s)${R}" \
      "$n_assets" "$n_endpoints" "$n_cands" "$top_score"
  else
    local n_roots=0
    if [ -f "$WS/$target/scope.yaml" ]; then
      n_roots=$(grep -c '^\s*- ' "$WS/$target/scope.yaml" 2>/dev/null || true)
      n_roots="${n_roots%%$'\n'*}"
    fi
    [ -z "$n_roots" ] && n_roots=0
    printf "${GOLD}🟡 Scope ready${R} ${MUTED}(%s assets) · Scan pending${R}" "$n_roots"
  fi
}

# =============================================================================
# Multi-program dashboard — one-screen overview across every target workspace,
# so juggling several programs doesn't mean opening each one just to check status.
# =============================================================================
show_dashboard() {
  clear
  title_box " 📊 DASHBOARD — ALL TARGETS " "Cross-program overview"
  echo ""
  local any=0
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    any=1
    echo "${P}  ${B}${CYAN}$t${R}"
    python3 -c "
import json, sqlite3
from pathlib import Path
base = Path('$WS')
d = base / 'recon' / 'data' / '$t'
db = d / 'recon.db'
run_meta = d / 'run_meta.json'

if run_meta.exists():
    try:
        m = json.loads(run_meta.read_text())
        print(f\"    Last run: {m.get('run_at','?')} (run_id={m.get('run_id','?')}, fresh={m.get('fresh_mode')})\")
    except Exception:
        pass
else:
    print('    No recon run yet.')

if db.exists():
    con = sqlite3.connect(db)
    try:
        rows = con.execute(\"SELECT status, count(*) FROM candidate_findings GROUP BY status\").fetchall()
        if rows:
            print('    Candidates: ' + ', '.join(f'{s}={c}' for s, c in rows))
        verified = con.execute(\"SELECT count(*) FROM candidate_findings WHERE status='VERIFIED'\").fetchone()[0]
        needs_review = con.execute(\"SELECT count(*) FROM candidate_findings WHERE status='NEEDS_MANUAL_CONFIRMATION'\").fetchone()[0]
        if verified:
            print(f'    \033[38;5;48m✓ {verified} VERIFIED finding(s) — check evidence/reports/$t/\033[0m')
        if needs_review:
            print(f'    \033[38;5;220m? {needs_review} NEEDS_MANUAL_CONFIRMATION — check recon.db / NOTES.md\033[0m')
    except sqlite3.OperationalError:
        print('    recon.db exists but has no candidate_findings table yet.')
    con.close()
else:
    print('    No recon.db yet.')
"
    echo ""
  done < <(existing_targets)
  [ "$any" -eq 0 ] && echo "${P}  ${MUTED}Koi target nahi hai abhi.${R}"
  echo ""
  sep
  read -r -p "${P}  Press Enter to return... " _
}

# =============================================================================
# Autopilot — one ON/OFF toggle: auto-picks a fresh program, auto-creates its
# folder, auto-runs the full zero-touch hunt, then auto-moves to the next
# fresh program — forever, until turned off. See recon/autopilot.py.
# =============================================================================
autopilot_menu() {
  local pid_file="$WS/recon/data/.autopilot.pid"
  clear
  title_box " 🚀 AUTOPILOT " "One switch — target-pick, scan, next-target, all automatic"
  echo ""
  local running=0 pid=""
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      running=1
    fi
  fi

  if [ "$running" -eq 1 ]; then
    echo "${P}  ${GREEN}● Autopilot is ON${R} ${MUTED}(PID: $pid)${R}"
    echo "${P}  ${MUTED}Log: tail -f $WS/.autopilot.log${R}"
    echo ""
    echo "${P}  [1] Turn OFF   [0] Back"
    local c
    read -r -p "${P}  Choice: " c
    if [ "$c" = "1" ]; then
      kill "$pid" 2>/dev/null
      rm -f "$pid_file"
      echo "${P}  ${GOLD}Autopilot turned OFF.${R}"
      sleep 1
    fi
  else
    echo "${P}  ${MUTED}Abhi OFF hai. ON karne par ye khud-ba-khud karega:${R}"
    echo "${P}    1. Tumhare PC ki capability check karega (CPU/RAM) — safe settings khud chunega"
    echo "${P}    2. Ek fresh/kam-crowded bounty-program dhoondega (jo abhi tak set up nahi hai)"
    echo "${P}    3. Uska folder/scope khud banayega"
    echo "${P}    4. Poora recon+scan+verify hunt khud chalayega"
    echo "${P}    5. Khatam hone par agla fresh-program khud uthayega — repeat, jab tak OFF na karo"
    echo ""
    echo "${P}  ${GOLD}⚠ Ye account ka daily-scan-limit/trial khud respect karta hai${R} ${MUTED}—"
    echo "${P}  agar quota khatam ho jaye, khud ruk jayega aur wajah batayega.${R}"
    echo ""
    echo "${P}  [1] Turn ON   [0] Back"
    local c
    read -r -p "${P}  Choice: " c
    if [ "$c" = "1" ]; then
      nohup python3 "$WS/recon/autopilot.py" > "$WS/.autopilot.log" 2>&1 &
      local new_pid=$!
      disown 2>/dev/null || true
      mkdir -p "$(dirname "$pid_file")"
      echo "$new_pid" > "$pid_file"
      echo "${P}  ${GREEN}✓ Autopilot ON (PID: $new_pid).${R} ${MUTED}Log: $WS/.autopilot.log${R}"
      sleep 1
    fi
  fi
}

# =============================================================================
# Background job status — what's actually running right now, across all programs.
# Useful for long scope.yaml wildcard scopes where recon/scanning can run for hours.
# =============================================================================
show_background_jobs() {
  clear
  title_box " ⚙  BACKGROUND JOBS " "What's actually running right now"
  echo ""
  local found=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    found=1
    echo "${P}  $line"
  done < <(ps -eo pid,etime,cmd 2>/dev/null | grep -E "subfinder|dnsx|httpx|katana|nuclei|gau[[:space:]]|recon_pipeline\.py|js_miner\.py|scanner\.py|intelligence\.py|auto_hunter\.py|daemon\.py" | grep -v "grep\|show_background_jobs")
  if [ "$found" -eq 0 ]; then
    echo "${P}  ${MUTED}Koi bug-bounty process abhi background mein chal nahi raha.${R}"
  fi
  echo ""
  sep
  read -r -p "${P}  Press Enter to return... " _
}

check_opencode() {
  if ! command -v "$OPCODE_BIN" >/dev/null 2>&1 && [ ! -x "$OPCODE_BIN" ]; then
    echo ""
    echo "  ${ORANGE}⚠ OpenCode CLI installed nahi mila.${R}"
    echo "  ${MUTED}Install command:${R} ${CYAN}curl -fsSL https://opencode.ai/install | bash${R}"
    return 1
  fi
  return 0
}

create_target_folder() {
  local handle="$1"
  local name="${2:-$handle}"
  local tdir="$WS/$handle"
  mkdir -p "$tdir"
  if [ ! -f "$tdir/scope.yaml" ]; then
    cat > "$tdir/scope.yaml" <<YAML
# Program — Engagement Contract (machine-readable)
program:
  handle: "$handle"
  name: "$name"
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
  if [ ! -f "$tdir/SCOPE.md" ]; then
    cat > "$tdir/SCOPE.md" <<MD
# $name — SCOPE
> Program handle: \`$handle\`
> Har hunting session se pehle scope verify karein. Sirf authorized assets.

## In-Scope Assets
*(Fill in scope.yaml roots)*

## Excluded / Out-of-Scope
MD
  fi
  [ -f "$tdir/NOTES.md" ] || echo "# $handle — Hunt Progress" > "$tdir/NOTES.md"
}

# =============================================================================
# Authenticated test-account setup — enables the opt-in IDOR heuristic in
# recon/auto_hunter.py (load_auth_credentials()). Writes <target>/.env.auth.
# Works for any HackerOne program with a session-token- or cookie-based test
# account — nothing here is specific to any one site.
# =============================================================================
setup_auth_credentials() {
  local target="$1"
  local tdir="$WS/$target"
  local auth_file="$tdir/.env.auth"
  clear
  title_box " 🔑 AUTHENTICATED TEST ACCOUNT: $target " "Enables the IDOR heuristic in auto_hunter.py"
  echo ""
  echo "${P}  ${MUTED}This lets the automated pipeline replay requests as a logged-in test"
  echo "${P}  ${MUTED}account and check for IDOR (one account accessing another's numeric-ID"
  echo "${P}  ${MUTED}resources). It is completely optional — nothing changes for this target"
  echo "${P}  ${MUTED}until you fill this in, and it never runs against any program you"
  echo "${P}  ${MUTED}haven't set this up for.${R}"
  echo ""
  echo "${P}  ${B}You'll need a real test/collab account you're authorized to use on"
  echo "${P}  this specific program${R} — check the program's policy for how to get one."
  echo ""
  if [ -f "$auth_file" ]; then
    echo "${P}  ${GREEN}An .env.auth already exists for '$target':${R}"
    echo ""
    grep "AUTH_HEADER" "$auth_file" 2>/dev/null | sed "s/^/${P}    /"
    echo "${P}    AUTH_VALUE=<hidden>"
    echo ""
    echo "${P}  [1] Replace it   [0] Keep it and go back"
    local rep
    read -r -p "${P}  Choice: " rep
    [ "$rep" != "1" ] && return
    echo ""
  fi

  echo "${P}  ${B}Step 1 — which header carries your session?${R}"
  echo "${P}    [1] Authorization  (e.g. an API bearer token: \"Bearer eyJ...\")"
  echo "${P}    [2] Cookie         (e.g. a logged-in browser session: \"session=...\")"
  echo "${P}    [3] Custom header name (type your own, e.g. \"X-Api-Key\")"
  local hchoice header_name
  read -r -p "${P}  Choice [1-3, or 0 to cancel]: " hchoice
  case "$hchoice" in
    1) header_name="Authorization" ;;
    2) header_name="Cookie" ;;
    3) read -r -p "${P}  Header name: " header_name ;;
    *) return ;;
  esac
  [ -z "$header_name" ] && { echo "${P}  ${RED}Header name khali nahi ho sakta.${R}"; sleep 2; return; }

  echo ""
  echo "${P}  ${B}Step 2 — paste the full header value${R}"
  echo "${P}    ${MUTED}(e.g. \"Bearer eyJhbGciOi...\" or \"session=abc123; other=xyz\" —"
  echo "${P}    whatever your browser's DevTools \"Network\" tab shows for that header"
  echo "${P}    on a request you make while logged in as your test account)${R}"
  local header_value
  read -r -p "${P}  Value (or 0 to cancel): " header_value
  if [ -z "$header_value" ] || [ "$header_value" = "0" ]; then
    echo "${P}  ${MUTED}Cancelled — nothing saved.${R}"; sleep 1; return
  fi

  mkdir -p "$tdir"
  cat > "$auth_file" <<AUTHEOF
# Authenticated test-account session for '$target' — used only by recon/auto_hunter.py's
# opt-in IDOR heuristic (load_auth_credentials()). Never committed (see .gitignore: **/.env.*).
export AUTH_HEADER="$header_name"
export AUTH_VALUE="$header_value"
AUTHEOF
  chmod 600 "$auth_file"
  echo ""
  echo "${P}  ${GREEN}✓ Saved to $auth_file (chmod 600, gitignored).${R}"
  echo "${P}  ${MUTED}Next time you run auto_hunter.py (standalone, or via [A]/[F]) for"
  echo "${P}  '$target', it will print '🔑 Authenticated IDOR heuristic ENABLED'.${R}"
  echo ""
  sep
  read -r -p "${P}  Press Enter to continue... " _
}

# =============================================================================
# HackerOne API credentials wizard — writes <workspace>/.env.h1, read by
# recon/h1_client.py's get_auth_headers(). This is YOUR OWN H1 account, used
# to discover/sync programs you're already authorized on (bring-your-own-key —
# separate from the product's own login in .env.account, see setup_account()).
# =============================================================================
setup_h1_credentials() {
  local env_file="$WS/.env.h1"
  clear
  title_box " 🔑 HACKERONE API CREDENTIALS " "Your own H1 account — used to sync authorized programs"
  echo ""
  if [ -f "$env_file" ] && grep -q "H1_API_TOKEN" "$env_file" 2>/dev/null; then
    echo "${P}  ${GREEN}Credentials already saved.${R} Testing...${R}"
    # shellcheck disable=SC1090
    source "$env_file"
    python3 "$WS/recon/h1_client.py" --test-auth 2>/dev/null
    echo ""
    echo "${P}  [1] Replace them   [0] Keep and go back"
    local rep
    read -r -p "${P}  Choice: " rep
    [ "$rep" != "1" ] && return
    echo ""
  fi

  echo "${P}  ${MUTED}Get an API token: https://hackerone.com/settings/api_token${R}"
  echo "${P}  ${MUTED}(needs your H1 username too — visible in your profile URL)${R}"
  echo ""
  local h1_user h1_token
  read -r -p "${P}  H1 username (or 0 to cancel): " h1_user
  if [ -z "$h1_user" ] || [ "$h1_user" = "0" ]; then
    echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; return
  fi
  read -r -p "${P}  H1 API token (or 0 to cancel): " h1_token
  if [ -z "$h1_token" ] || [ "$h1_token" = "0" ]; then
    echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; return
  fi

  cat > "$env_file" <<H1EOF
# HackerOne API credentials — your own account, used by recon/h1_client.py
# to discover/sync programs you're authorized on. Never committed (.gitignore: **/.env.*).
export H1_USERNAME="$h1_user"
export H1_API_TOKEN="$h1_token"
H1EOF
  chmod 600 "$env_file"
  export H1_USERNAME="$h1_user" H1_API_TOKEN="$h1_token"
  echo ""
  echo "${P}  ${GREEN}✓ Saved.${R} Testing authentication..."
  python3 "$WS/recon/h1_client.py" --test-auth
  echo ""
  sep
  read -r -p "${P}  Press Enter to continue... " _
}

# =============================================================================
# WPScan API token — a global (not per-program) credential that enables
# recon/scanner.py's auto-triggered wpscan pass (fires whenever a program's
# assets.json has a WordPress-tagged host — see detect_wordpress_hosts()).
# Free tier: https://wpscan.com/register. Writes <workspace>/.env.wpscan.
# =============================================================================
setup_wpscan_token() {
  local env_file="$WS/.env.wpscan"
  clear
  title_box " 🛡  WPSCAN API TOKEN " "Enables automated WordPress vulnerability checks"
  echo ""
  echo "${P}  ${MUTED}scanner.py automatically runs wpscan on any host whose recon"
  echo "${P}  ${MUTED}data shows WordPress in its detected tech stack (any program,"
  echo "${P}  ${MUTED}not just one) — but wpscan needs a free API token to actually"
  echo "${P}  ${MUTED}look up known plugin/theme vulnerabilities. Without one, it"
  echo "${P}  ${MUTED}still runs but skips the vulnerability-database lookup.${R}"
  echo ""
  if [ -f "$env_file" ] && grep -q "WPSCAN_API_TOKEN" "$env_file" 2>/dev/null; then
    echo "${P}  ${GREEN}A token is already saved.${R}"
    echo ""
    echo "${P}  [1] Replace it   [0] Keep it and go back"
    local rep
    read -r -p "${P}  Choice: " rep
    [ "$rep" != "1" ] && return
    echo ""
  fi

  echo "${P}  ${B}Get a free token:${R} ${CYAN}https://wpscan.com/register${R}"
  echo "${P}  ${MUTED}(free tier: 25 requests/day — plenty for occasional per-program checks)${R}"
  echo ""
  local token
  read -r -p "${P}  Paste your WPScan API token (or 0 to cancel): " token
  if [ -z "$token" ] || [ "$token" = "0" ]; then
    echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; return
  fi

  cat > "$env_file" <<WPEOF
# WPScan API token — used only by recon/scanner.py's auto-triggered wpscan pass
# (detect_wordpress_hosts()/wpscan_check()). Never committed (see .gitignore: **/.env.*).
# Free tier: https://wpscan.com/register
export WPSCAN_API_TOKEN="$token"
WPEOF
  chmod 600 "$env_file"
  echo ""
  echo "${P}  ${GREEN}✓ Saved to $env_file (chmod 600, gitignored).${R}"
  echo "${P}  ${MUTED}Next time scanner.py finds a WordPress-tagged host (any program),"
  echo "${P}  it will run a real vulnerability-database lookup instead of skipping.${R}"
  echo ""
  sep
  read -r -p "${P}  Press Enter to continue... " _
}

# =============================================================================
# Account login — this product's own login (separate from HackerOne API
# creds in .env.h1). Gates the per-day scan quota enforced in
# recon/recon_pipeline.py's main() via recon/account_client.py.
# Server: recon/account_server.py (run separately, see docs/FUTURE_FEATURES.md).
# =============================================================================
setup_account() {
  local env_file="$WS/.env.account"
  clear
  title_box " 👤 ACCOUNT LOGIN " "Subscription tier & daily scan quota"
  echo ""
  if [ -f "$env_file" ] && grep -q "ACCOUNT_TOKEN" "$env_file" 2>/dev/null; then
    echo "${P}  ${GREEN}Logged in already.${R} Fetching status..."
    python3 "$WS/recon/account_client.py" --status 2>/dev/null
    echo ""
    echo "${P}  [1] Re-login (different account)   [0] Back"
    local rep
    read -r -p "${P}  Choice: " rep
    [ "$rep" != "1" ] && return
    echo ""
  fi

  echo "${P}  [1] Register (naya account)   [2] Login (existing account)   [0] Cancel"
  local mode
  read -r -p "${P}  Choice: " mode
  [ "$mode" != "1" ] && [ "$mode" != "2" ] && { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; return; }

  local email password
  read -r -p "${P}  Email: " email
  [ -z "$email" ] && { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; return; }
  read -r -s -p "${P}  Password: " password
  echo ""
  [ -z "$password" ] && { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; return; }

  local flag="--login"
  [ "$mode" = "1" ] && flag="--register"
  python3 "$WS/recon/account_client.py" $flag --email "$email" --password "$password"
  echo ""
  sep
  read -r -p "${P}  Press Enter to continue... " _
}

# =============================================================================
# Pre-Flight System Diagnostics
# =============================================================================
diagnostics_check() {
  clear
  title_box " ⚡ PRE-FLIGHT SYSTEM DIAGNOSTICS " "Tools, Environment & API Audit"
  echo ""
  echo "${P}  ${B}1. Core Security Tools:${R}"
  local tools=("subfinder" "dnsx" "httpx" "gau" "katana" "nuclei" "ffuf" "dalfox" "sqlmap" "jadx")
  for t in "${tools[@]}"; do
    if command -v "$t" >/dev/null 2>&1; then
      printf "%s    ${GREEN}✓${R} %-12s ${MUTED}%s${R}\n" "$P" "$t" "$(command -v "$t")"
    else
      printf "%s    ${RED}✗${R} %-12s ${RED}NOT FOUND${R}\n" "$P" "$t"
    fi
  done

  echo ""
  echo "${P}  ${B}2. Services & Environment:${R}"
  if docker info >/dev/null 2>&1; then
    printf "%s    ${GREEN}✓${R} %-12s ${MUTED}running${R}\n" "$P" "Docker"
  else
    printf "%s    ${GOLD}⚠${R} %-12s ${MUTED}stopped (sudo systemctl start docker)${R}\n" "$P" "Docker"
  fi

  if command -v "$OPCODE_BIN" >/dev/null 2>&1 || [ -x "$OPCODE_BIN" ]; then
    printf "%s    ${GREEN}✓${R} %-12s ${MUTED}%s${R}\n" "$P" "OpenCode" "$OPCODE_BIN"
  else
    printf "%s    ${GOLD}⚠${R} %-12s ${MUTED}not in PATH (curl -fsSL https://opencode.ai/install | bash)${R}\n" "$P" "OpenCode"
  fi

  echo ""
  echo "${P}  ${B}3. HackerOne API Credentials:${R}"
  if [ -n "${H1_USERNAME:-}" ]; then
    printf "%s    ${GREEN}✓${R} %-14s ${MUTED}%s***${R}\n" "$P" "H1_USERNAME" "${H1_USERNAME:0:3}"
  else
    printf "%s    ${GOLD}⚠${R} %-14s ${RED}not set in environment${R}\n" "$P" "H1_USERNAME"
  fi
  if [ -n "${H1_API_TOKEN:-}" ]; then
    printf "%s    ${GREEN}✓${R} %-14s ${MUTED}configured (hidden)${R}\n" "$P" "H1_API_TOKEN"
  else
    printf "%s    ${GOLD}⚠${R} %-14s ${RED}not set in environment${R}\n" "$P" "H1_API_TOKEN"
  fi

  echo ""
  echo "${P}  ${B}4. WPScan API Token (optional — enables automated WordPress checks):${R}"
  if grep -q "WPSCAN_API_TOKEN" "$WS/.env.wpscan" 2>/dev/null; then
    printf "%s    ${GREEN}✓${R} %-14s ${MUTED}configured (hidden)${R}\n" "$P" "WPSCAN_API_TOKEN"
  else
    printf "%s    ${GOLD}⚠${R} %-14s ${MUTED}not set — Main Menu [W] to configure (free: wpscan.com/register)${R}\n" "$P" "WPSCAN_API_TOKEN"
  fi

  echo ""
  echo "${P}  ${B}5. Account (subscription / daily scan quota):${R}"
  if grep -q "ACCOUNT_TOKEN" "$WS/.env.account" 2>/dev/null; then
    printf "%s    ${GREEN}✓${R} %-14s ${MUTED}logged in — Main Menu [A] for status${R}\n" "$P" "Account"
  else
    printf "%s    ${GOLD}⚠${R} %-14s ${MUTED}not logged in — Main Menu [A] to register/login${R}\n" "$P" "Account"
  fi

  echo ""
  sep
  echo "${P}  ${MUTED}[0] ↩ Back to Main Menu${R}"
  echo ""
  read -r -p "${P}  Press Enter or [0] to return... " _
}

# =============================================================================
# Recon Diff Engine
#
# STATUS: DISPLAY / INVESTIGATION TOOL ONLY (PIPELINE_INTEGRITY_V2 audit).
# Runs a passive subfinder pass and prints new-vs-known subdomains to the terminal.
# It does NOT write to assets.json or recon.db and does NOT feed scanner.py/
# intelligence.py/daemon.py — it is not a persistence or auto-discovery mechanism.
# To actually add newly-seen subdomains to the pipeline, re-run recon_pipeline.py
# (optionally --fresh).
# =============================================================================
target_diff() {
  local target="$1"
  local sfile="$WS/$target/scope.yaml"
  local afile="$WS/recon/data/$target/assets.json"

  if [ ! -f "$sfile" ]; then
    echo "${P}  ${RED}scope.yaml nahi mila: $sfile${R}"
    read -r -p "${P}  Press Enter or [0] to return... " _
    return
  fi

  clear
  title_box " ◈ RECON DIFF ENGINE: $target " "Subdomain Change Detection"
  echo ""
  echo "${P}  ${MUTED}Extracting in-scope roots from scope.yaml...${R}"

  local roots
  roots=$(python3 -c "import yaml; s = yaml.safe_load(open('$sfile')); print('\n'.join(s.get('roots', [])))" 2>/dev/null)

  if [ -z "$roots" ]; then
    echo "${P}  ${GOLD}Roots khali hain scope.yaml me.${R}"
    read -r -p "${P}  Press Enter or [0] to return... " _
    return
  fi

  echo "${P}  Roots: $(echo "$roots" | tr '\n' ' ')"
  echo ""
  echo "${P}  ${CYAN}◌ Running fast passive subdomain discovery...${R}"

  local raw_dir="$WS/recon/data/$target/raw"
  mkdir -p "$raw_dir"
  local tmp_current="$raw_dir/diff_current.txt"
  rm -f "$tmp_current"
  while IFS= read -r r; do
    [ -n "$r" ] && subfinder -d "$r" -silent 2>/dev/null >> "$tmp_current"
  done <<< "$roots"

  if [ ! -f "$tmp_current" ] || [ ! -s "$tmp_current" ]; then
    echo "${P}  ${GOLD}Koi subdomain return nahi hua.${R}"
    read -r -p "${P}  Press Enter or [0] to return... " _
    return
  fi

  sort -u -o "$tmp_current" "$tmp_current"
  local total_now
  total_now=$(wc -l < "$tmp_current")
  echo "${P}  ${GREEN}✓${R} Live subdomains found now: ${B}$total_now${R}"

  local tmp_known="$raw_dir/diff_known.txt"
  rm -f "$tmp_known"
  if [ -f "$afile" ]; then
    grep '"host":' "$afile" | sed -E 's/.*"host":\s*"([^"]+)".*/\1/' | sort -u > "$tmp_known"
  fi

  if [ -s "$tmp_known" ]; then
    local new_subs
    new_subs=$(comm -13 "$tmp_known" "$tmp_current")
    if [ -n "$new_subs" ]; then
      echo ""
      echo "${P}  ${GREEN}${B}🚨 NAYE SUBDOMAINS MIL GAYE (New Attack Surface):${R}"
      while IFS= read -r sub; do
        printf "%s    ${GREEN}+ %s${R}\n" "$P" "$sub"
      done <<< "$new_subs"
    else
      echo "${P}  ${MUTED}Koi naya subdomain nahi mila (Attack surface unchanged).${R}"
    fi
  else
    echo "${P}  ${MUTED}Existing assets.json nahi tha. Ye pehla snapshot hai ($total_now subdomains).${R}"
  fi

  echo ""
  sep
  read -r -p "${P}  Press Enter or [0] to return... " _
}

# Helper: Run a named pipeline phase, report duration, and trap exit codes
run_phase() {
  local phase_num="$1"
  local total_phases="$2"
  local phase_name="$3"
  shift 3
  local cmd=("$@")

  echo "${P}  ${B}${BLUE}◈ [Phase ${phase_num}/${total_phases}]${R} ⚡ ${B}${phase_name}...${R}"
  local t_start=$(date +%s)

  "${cmd[@]}"
  local exit_code=$?
  local t_dur=$(( $(date +%s) - t_start ))

  if [ $exit_code -ne 0 ]; then
    echo "${P}    ${RED}✗ Phase ${phase_num} failed with exit code ${exit_code} (${t_dur}s)${R}"
    return $exit_code
  fi

  echo "${P}    ${GREEN}✓ Phase ${phase_num} complete in ${t_dur}s.${R}"
  echo ""
  return 0
}

# =============================================================================
# COMPLETE AUTONOMOUS SCAN & HUNT PIPELINE (Recon → JS → Scan → Triage → AI Agent)
# =============================================================================
run_complete_hunt() {
  local target="$1"
  local fresh_flag="${2:-}"
  clear
  title_box " 🚀 COMPLETE AUTONOMOUS SCAN & HUNT " "$target"
  echo ""
  echo "${P}  ${B}Target:${R} ${CYAN}${B}$target${R}"
  echo "${P}  ${MUTED}Starting multi-phase automated surface discovery & agent handoff...${R}"
  echo ""
  sep

  # Phase 1: Recon Pipeline (Subdomains + HTTP probing + Archive URLs, skip duplicate JS)
  local recon_cmd=(python3 "$WS/recon/recon_pipeline.py" --program "$target" --skip-js)
  [ -n "$fresh_flag" ] && recon_cmd+=("$fresh_flag")
  run_phase 1 5 "Subdomain Enumeration & Alive Probing (httpx)" "${recon_cmd[@]}" || return 1

  # Phase 2: Client-side JS Miner & Route Extraction (Katana)
  run_phase 2 5 "Client-side Route & Secret Extraction (Katana)" \
    python3 "$WS/recon/js_miner.py" --program "$target" || return 1

  # Phase 3: Safe Vulnerability & Misconfiguration Scanning (Nuclei)
  run_phase 3 5 "Safe Vulnerability Scanning (Nuclei)" \
    python3 "$WS/recon/scanner.py" --program "$target" || return 1

  # Phase 4: Intelligence Triage & Ranking
  run_phase 4 5 "Intelligence Triage & Scoring (candidate_findings)" \
    python3 "$WS/recon/intelligence.py" --program "$target" --top 40 || return 1

  # Phase 5: Autonomous Hunt Prompt Generation
  local prompt_file="$WS/$target/AUTONOMOUS_HUNT_PROMPT.md"
  run_phase 5 5 "Generating Pre-Filled Autonomous Hunting Prompt" \
    python3 "$WS/recon/h1_client.py" --prompt "$target" || return 1

  if [ -f "$prompt_file" ]; then
    echo "${P}    ${GREEN}✓${R} Pre-filled hunting prompt ready: ${B}${CYAN}$prompt_file${R}"
  fi
  echo ""
  sep
  echo ""

  # Step 6: Launch OpenCode or Interactive Shell
  echo "${P}  ${B}${GOLD}🚀 READY TO HUNT:${R} Target surface analyzed aur AI Agent prompt tayyar hai!"
  echo ""
  echo "${P}  ${MUTED}Candidate findings, in-scope roots, aur rules prompt me pre-configured hain.${R}"
  echo ""
  opt "1" "🤖 Open in OpenCode AI Agent" "terminal session with pre-filled prompt"
  opt "2" "📜 View Full Hunt Prompt"     "terminal par prompt read karein"
  opt "3" "💻 Interactive Hunting Shell" "manual inspection with prompt in env"
  opt "0" "↩ Return to Target Menu"      "back to target operations"
  echo ""
  sep
  local ac_choice
  read -r -p "${P}  ${B}Select option [0-3, or B to return]:${R} " ac_choice

  case "$ac_choice" in
    1)
      cd "$WS/$target"
      if command -v opencode >/dev/null 2>&1 || [ -x "$OPCODE_BIN" ]; then
        echo ""
        echo "${P}  ${GREEN}✓${R} Launching OpenCode in $target/..."
        echo "${P}  ${MUTED}(AUTONOMOUS_HUNT_PROMPT.md loaded — press Submit to hunt)${R}"
        sleep 1
        if [ -f "$prompt_file" ]; then
          "$OPCODE_BIN" "$WS/$target" --prompt "$(cat "$prompt_file")"
        else
          "$OPCODE_BIN" "$WS/$target"
        fi
        cd "$WS"
      else
        echo ""
        echo "${P}  ${ORANGE}⚠ OpenCode binary PATH me nahi mila.${R}"
        echo "${P}  ${MUTED}Install command:${R} ${CYAN}curl -fsSL https://opencode.ai/install | bash${R}"
        echo ""
        echo "${P}  ${B}Aapka Pre-filled Prompt is file me save hai:${R}"
        echo "${P}    ${CYAN}$prompt_file${R}"
        echo ""
        read -r -p "${P}  Interactive hunting shell shuru karein? [Y/n]: " sh_ans
        if [[ ! "$sh_ans" =~ ^[nN]$ ]]; then
          export HUNT_PROMPT="$(cat "$prompt_file" 2>/dev/null)"
          echo "${P}  ${MUTED}(Prompt \$HUNT_PROMPT env variable me bhi loaded hai)${R}"
          PS1="[hunt:$target]\$ " bash --norc -i
        fi
        cd "$WS"
      fi
      ;;
    2)
      clear
      if [ -f "$prompt_file" ]; then
        cat "$prompt_file"
      fi
      echo ""
      sep
      read -r -p "${P}  Press Enter or [0] to return... " _
      ;;
    3)
      cd "$WS/$target"
      export HUNT_PROMPT="$(cat "$prompt_file" 2>/dev/null)"
      echo ""
      echo "${P}  ${GREEN}✓${R} Dropped into hunting shell for target: ${B}$target${R}"
      echo "${P}  ${MUTED}Prompt file: $prompt_file | Env: \$HUNT_PROMPT${R}"
      PS1="[hunt:$target]\$ " bash --norc -i
      cd "$WS"
      ;;
    0|[bB]*|[qQ]*)
      return
      ;;
    *)
      return
      ;;
  esac
}

# =============================================================================
# ZERO-TOUCH AUTONOMOUS HUNT & AUTO-REPORT PIPELINE
# Recon → JS Miner → Scanner → Intelligence → Auto-Hunter → Report Gen → Push Alert
# =============================================================================
run_zero_touch_hunt() {
  local target="$1"
  local fresh_flag="${2:-}"
  clear
  title_box " 🤖 AUTONOMOUS ZERO-TOUCH HUNT " "$target"
  echo ""
  echo "${P}  ${B}Target:${R} ${CYAN}${B}$target${R}"
  echo "${P}  ${MUTED}Initiating 100% automated reconnaissance, scanning, verification & report generation...${R}"
  echo ""
  sep

  # Phase 1: Recon Pipeline (Subdomains + Alive Probing, skip duplicate JS)
  local recon_cmd=(python3 "$WS/recon/recon_pipeline.py" --program "$target" --skip-js)
  [ -n "$fresh_flag" ] && recon_cmd+=("$fresh_flag")
  run_phase 1 6 "Reconnaissance & Asset Probing" "${recon_cmd[@]}" || return 1

  # Phase 2: Client-side JS Miner
  run_phase 2 6 "Client-side Route & Secret Extraction" \
    python3 "$WS/recon/js_miner.py" --program "$target" || return 1

  # Phase 3: Safe Vulnerability Scanning (Nuclei)
  run_phase 3 6 "Safe Vulnerability Scanning (Nuclei)" \
    python3 "$WS/recon/scanner.py" --program "$target" || return 1

  # Phase 4: Intelligence Triage & Scoring
  run_phase 4 6 "Intelligence Prioritization & Heuristic Scoring" \
    python3 "$WS/recon/intelligence.py" --program "$target" --top 40 || return 1

  # Phase 5: Headless Candidate Verification
  run_phase 5 6 "Headless Candidate Verification (CORS/Auth/Leaks)" \
    python3 "$WS/recon/auto_hunter.py" --program "$target" --min-score 50 || return 1

  # Phase 6: Report Compilation & Alert Dispatch
  echo "${P}  ${B}${BLUE}◈ [Phase 6/6]${R} ⚡ ${B}Report Compilation & Alert Dispatch...${R}"
  local rep_dir="$WS/evidence/reports/$target"
  local count=0
  if [ -d "$rep_dir" ]; then
    count=$(find "$rep_dir" -maxdepth 1 -name "H1_REPORT_*.md" | wc -l)
  fi

  python3 "$WS/recon/notify.py" \
    --title "🎯 Autonomous Zero-Touch Hunt Finished ($target)" \
    --message "Autonomous hunt completed successfully across 6 phases.\nVerified Reports generated: $count\nReports Directory: evidence/reports/$target/" \
    --severity "info"

  echo ""
  sep
  echo "${P}  ${B}${GREEN}✓ ZERO-TOUCH HUNT COMPLETE:${R} $count ready-to-submit HackerOne draft reports generated!"
  if [ "$count" -gt 0 ]; then
    echo "${P}  ${B}Reports Directory:${R} ${CYAN}$rep_dir/${R}"
  fi
  echo ""
  if [ -t 0 ]; then
    read -r -p "${P}  Press Enter or [0] to return... " _
  fi
}

# =============================================================================
# Target Action Sub-Menu
# =============================================================================
target_menu() {
  local target="$1"
  while true; do
    update_geom
    clear
    title_box " 🎯 MISSION CONTROL: $target " "Target Operations & Hunting Pipeline"
    echo ""
    echo "${P}  Target:  ${B}${CYAN}$target${R}"
    echo "${P}  Status:  $(target_stats "$target")"
    echo ""
    sep
    echo "${P}  ${B}Recommended Actions:${R}"
    opt "A" "🤖 AUTONOMOUS ZERO-TOUCH HUNT"      "Standard hunt (re-uses cached discovery)"
    opt "F" "⚡ FRESH ZERO-TOUCH HUNT (Force)"   "Bypass cache & force 100% fresh discovery"
    opt "C" "🚀 Complete Scan & OpenCode Prompt" "Standard workflow with AI agent prompt"
    echo ""
    echo "${P}  ${B}Individual Pipeline Modules:${R}"
    opt "1" "Interactive Shell / Session"        "Terminal hunting session"
    opt "2" "Recon Pipeline Only"               "subfinder → httpx → gau"
    opt "3" "Deep JS Miner (Katana)"            "client-side routes & secret extraction"
    opt "4" "Safe Vulnerability Scan"           "Nuclei rate-limited prober"
    opt "5" "View Candidate Report"             "Top-40 scored findings queue"
    opt "6" "Recon Diff Engine"                 "Check for newly deployed subdomains"
    opt "7" "View Scope & Notes"                "SCOPE.md & NOTES.md"
    opt "8" "🔑 Set Up Authenticated Test Account" "enables the auto_hunter.py IDOR heuristic"
    opt "9" "🩺 Check Data Freshness"            "is recon.db in sync with assets/endpoints.json?"
    opt "0" "↩ Back to Main Menu"               "return to mission control"
    echo ""
    sep
    local act
    read -r -p "${P}  ${B}Action for [$target]${R} [A/F/C/0-9, or B to return]: " act

    case "$act" in
      [aA]*)
        run_zero_touch_hunt "$target"
        ;;
      [fF]*)
        run_zero_touch_hunt "$target" "--fresh"
        ;;
      [cC]*)
        run_complete_hunt "$target"
        ;;
      1)
        cd "$WS/$target"
        if check_opencode; then
          echo ""
          echo "${P}  [1] OpenCode AI Session   [2] Interactive Bash Shell   [0] Back"
          local sc
          read -r -p "${P}  Choice [1-2, or 0 to cancel]: " sc
          if [ "$sc" = "1" ]; then
            local p_file="$WS/$target/AUTONOMOUS_HUNT_PROMPT.md"
            if [ -f "$p_file" ]; then
              "$OPCODE_BIN" "$WS/$target" --prompt "$(cat "$p_file")"
            else
              "$OPCODE_BIN" "$WS/$target"
            fi
            cd "$WS"
          elif [ "$sc" = "2" ]; then
            PS1="[bug-bounty:$target]\$ " bash --norc -i
            cd "$WS"
          fi
        else
          PS1="[bug-bounty:$target]\$ " bash --norc -i
          cd "$WS"
        fi
        ;;
      2)
        echo ""
        echo "${P}  ${CYAN}⚡ Running Recon Pipeline for '$target'...${R}"
        local t_recon_start=$(date +%s)
        python3 "$WS/recon/recon_pipeline.py" --program "$target"
        local t_recon_dur=$(( $(date +%s) - t_recon_start ))
        echo ""
        sep
        echo "${P}  ✓ Recon complete in ${t_recon_dur}s."
        # Scan-scale preview — a wildcard-heavy scope.yaml (*.example.org style) can
        # legitimately return tens of thousands of hosts, most of them redirects/dead.
        # Show the real breakdown before anyone commits hours to scanning all of them.
        python3 -c "
import json, sys
try:
    assets = json.load(open('$WS/recon/data/$target/assets.json'))
except Exception:
    sys.exit(0)
if len(assets) < 500:
    sys.exit(0)  # small scope — no need to warn
from collections import Counter
statuses = Counter(a.get('status') for a in assets)
live200 = sum(1 for a in assets if a.get('status') == 200)
print()
print(f'  ⚠  Large scope: {len(assets)} total assets discovered.')
print(f'     Status breakdown: ' + ', '.join(f'{k}={v}' for k, v in statuses.most_common()))
print(f'     Only {live200} return a genuine HTTP 200 (rest are redirects/errors) —')
print(f'     those {live200} are usually the real, distinct, worth-scanning surface.')
print(f'     Running Nuclei/JS-mining on ALL {len(assets)} could take hours-to-days at')
print(f'     safe rate limits. Consider option 9 (Data Freshness) or manually filtering')
print(f'     assets.json to status==200 before running a full scan on a scope this size.')
"
        sep
        read -r -p "${P}  Press Enter or [0] to continue..." _
        ;;
      3)
        echo ""
        echo "${P}  [1] Dry-run safe check   [2] Live JS Crawl   [0] Back"
        local jc
        read -r -p "${P}  Choice [1-2, or 0 to cancel]: " jc
        if [ "$jc" = "2" ]; then
          echo "${P}  ${CYAN}⚡ Running JS Miner for '$target'...${R}"
          local t_js_start=$(date +%s)
          python3 "$WS/recon/js_miner.py" --program "$target"
          local t_js_dur=$(( $(date +%s) - t_js_start ))
          echo ""
          sep
          read -r -p "${P}  ✓ JS Miner complete in ${t_js_dur}s. Press Enter or [0] to continue..." _
        elif [ "$jc" = "1" ]; then
          python3 "$WS/recon/js_miner.py" --program "$target" --dry-run
          echo ""
          sep
          read -r -p "${P}  Dry-run complete. Press Enter or [0] to continue..." _
        else
          continue
        fi
        ;;
      4)
        echo ""
        echo "${P}  [1] Dry-run safe check   [2] Live Nuclei scan   [0] Back"
        local nc
        read -r -p "${P}  Choice [1-2, or 0 to cancel]: " nc
        if [ "$nc" = "2" ]; then
          echo "${P}  ${CYAN}⚡ Running Safe Nuclei Scan for '$target'...${R}"
          local t_scan_start=$(date +%s)
          python3 "$WS/recon/scanner.py" --program "$target"
          local t_scan_dur=$(( $(date +%s) - t_scan_start ))
          echo ""
          sep
          read -r -p "${P}  ✓ Scan complete in ${t_scan_dur}s. Press Enter or [0] to continue..." _
        elif [ "$nc" = "1" ]; then
          python3 "$WS/recon/scanner.py" --program "$target" --dry-run
          echo ""
          sep
          read -r -p "${P}  Dry-run complete. Press Enter or [0] to continue..." _
        else
          continue
        fi
        ;;
      5)
        echo ""
        local rep="$WS/recon/data/$target/candidate_report.md"
        if [ -f "$rep" ]; then
          clear
          cat "$rep"
        else
          echo "${P}  ${GOLD}candidate_report.md nahi mila. Abhi intelligence run karein? [Y/n]${R}"
          local ir
          read -r -p "${P}  Choice [Y/n, or 0 to cancel]: " ir
          if [ "$ir" = "0" ] || [ "$ir" = "b" ] || [ "$ir" = "B" ]; then
            continue
          fi
          if [[ ! "$ir" =~ ^[nN]$ ]]; then
            python3 "$WS/recon/intelligence.py" --program "$target" --top 40
            [ -f "$rep" ] && cat "$rep"
          fi
        fi
        echo ""
        sep
        read -r -p "${P}  Press Enter or [0] to return... " _
        ;;
      6)
        target_diff "$target"
        ;;
      7)
        clear
        title_box " 📄 SCOPE & NOTES: $target " "In-Scope Roots & Hunt Log"
        echo ""
        echo "${P}=== $target/SCOPE.md ==="
        [ -f "$WS/$target/SCOPE.md" ] && cat "$WS/$target/SCOPE.md"
        echo ""
        echo "${P}=== $target/NOTES.md ==="
        [ -f "$WS/$target/NOTES.md" ] && cat "$WS/$target/NOTES.md"
        echo ""
        sep
        read -r -p "${P}  Press Enter or [0] to return... " _
        ;;
      8)
        setup_auth_credentials "$target"
        ;;
      9)
        clear
        title_box " 🩺 DATA FRESHNESS: $target " "Is recon.db in sync with assets.json / endpoints.json?"
        echo ""
        python3 "$WS/recon/artifact_consistency.py" --program "$target"
        echo ""
        sep
        read -r -p "${P}  Press Enter or [0] to return... " _
        ;;
      0|[bB]*|[qQ]*)
        return
        ;;
      *)
        echo "${P}  ${RED}Invalid choice.${R}"; sleep 1
        ;;
    esac
  done
}

# =============================================================================
# Flow 1 — Start NEW scan (Direct HackerOne API + Filter + Provision)
# =============================================================================
# =============================================================================
# Company / self-owned-domain target setup — for a user monitoring their OWN
# infrastructure rather than a HackerOne bug-bounty program (no H1 sync).
# There is no automated ownership-verification yet (no DNS-TXT check — see
# docs/FUTURE_FEATURES.md) so this wizard uses a typed acknowledgment as the
# MVP-level authorization gate, logged to the target's NOTES.md for a real
# accountability trail. Treat this as a placeholder, not a real security control,
# until DNS-TXT (or equivalent) verification is built.
# =============================================================================
setup_company_target() {
  update_geom
  clear
  title_box " 🏢 COMPANY TARGET — SELF-OWNED DOMAIN " "For monitoring infrastructure you own (not a HackerOne program)"
  echo ""
  echo "${P}  ${MUTED}Ye mode sirf apni khud ki company/domain monitor karne ke liye hai —${R}"
  echo "${P}  ${MUTED}HackerOne se sync nahi hota, sirf tumhare diye domains scan honge.${R}"
  echo ""
  local label
  read -r -p "${P}  Company/project name (or 0 to cancel): " label
  if [ -z "$label" ] || [ "$label" = "0" ]; then return; fi
  local fname
  fname="$(normalize_name "$label")"
  if [ -z "$fname" ]; then
    echo "${P}  ${RED}✗ Invalid name.${R}"; sleep 2; return
  fi
  if [ -d "$WS/$fname" ] && [ -f "$WS/$fname/scope.yaml" ]; then
    echo ""
    echo "${P}  ${GOLD}⚠ Target '$fname' already exists.${R}"
    read -r -p "${P}  Usi target ka menu open karein? [Y/n]: " om
    [[ ! "$om" =~ ^[nN]$ ]] && target_menu "$fname"
    return
  fi

  echo ""
  echo "${P}  ${B}Domains to monitor${R} ${MUTED}(ek-ek karke type karo, khaali line se end karo):${R}"
  local roots=() d
  while true; do
    read -r -p "${P}    Domain: " d
    [ -z "$d" ] && break
    roots+=("$d")
  done
  if [ "${#roots[@]}" -eq 0 ]; then
    echo "${P}  ${RED}✗ Koi domain nahi diya. Cancelled.${R}"; sleep 2; return
  fi

  echo ""
  echo "${P}  ${GOLD}⚠ ZAROORI: Active scanning sirf apne authorized/owned domains par karo.${R}"
  echo "${P}  ${MUTED}Type karo 'I OWN THESE DOMAINS' confirm karne ke liye ki upar diye${R}"
  echo "${P}  ${MUTED}sab domains tumhare khud ke hain ya tumhe test karne ki likhit ijazat hai:${R}"
  local ack
  read -r -p "${P}  Confirmation: " ack
  if [ "$ack" != "I OWN THESE DOMAINS" ]; then
    echo "${P}  ${RED}✗ Confirmation match nahi hua. Cancelled — koi target nahi banaya.${R}"
    sleep 2
    return
  fi

  mkdir -p "$WS/$fname"
  {
    echo "# Company Target — Engagement Contract (machine-readable)"
    echo "program:"
    echo "  handle: \"$fname\""
    echo "  name: \"$label\""
    echo "  confirmed: true   # ownership acknowledged via typed confirmation, see NOTES.md"
    echo ""
    echo "roots:"
    for d in "${roots[@]}"; do echo "  - $d"; done
    echo "excluded: []"
    echo "allowed:"
    echo "  methods: [GET, HEAD, OPTIONS, POST]"
    echo "  max_requests_per_minute: 60"
    echo "  max_concurrency: 5"
    echo "  destructive_actions: false"
  } > "$WS/$fname/scope.yaml"
  {
    echo "# $label — Hunt Progress"
    echo ""
    echo "## Ownership acknowledgment"
    echo "- Acknowledged by: typed 'I OWN THESE DOMAINS' at $(date -Iseconds)"
    echo "- Domains: ${roots[*]}"
    echo "- Note: this is a typed self-declaration, NOT an automated ownership check"
    echo "  (no DNS-TXT verification exists yet — see docs/FUTURE_FEATURES.md)."
  } > "$WS/$fname/NOTES.md"
  echo "# $label — SCOPE" > "$WS/$fname/SCOPE.md"
  echo ""
  echo "${P}  ${GREEN}✓${R} Company target created: ${B}$fname/${R} (${#roots[@]} domain(s))"
  echo ""
  title_box " TARGET CONFIGURED: $fname " "Ready for scanning"
  opt "C" "🚀 Run COMPLETE SCAN & PRE-FILL AGENT HUNT" "Recommended pipeline — ek-baar-ka scan"
  opt "W" "🐕 Turn ON Watchdog (continuous monitoring)" "Naya asset/change dikhe to khud-ba-khud scan+notify"
  opt "M" "🎯 Open Target Mission Control Menu"        "Target operations dashboard"
  opt "0" "↩ Return to Main Menu"                     "Mission control home"
  echo ""
  sep
  local post_act
  read -r -p "${P}  ${B}Choice [C/W/M/0]:${R} " post_act
  case "$post_act" in
    [cC]*) run_complete_hunt "$fname" ;;
    [wW]*)
      echo ""
      echo "${P}  ${B}Kitni der mein check kare?${R}"
      opt "1" "15 minute" ""
      opt "2" "1 ghanta (default)" ""
      opt "3" "6 ghante" ""
      opt "4" "24 ghante" ""
      opt "5" "Custom" ""
      local ic dsec
      read -r -p "${P}  Choice [1-5]: " ic
      case "$ic" in
        1) dsec=900 ;; 3) dsec=21600 ;; 4) dsec=86400 ;;
        5) read -r -p "${P}  Interval seconds mein: " dsec; [ -z "$dsec" ] && dsec=3600 ;;
        *) dsec=3600 ;;
      esac
      nohup python3 "$WS/recon/daemon.py" --program "$fname" --interval "$dsec" > "$WS/recon/data/daemon.log" 2>&1 &
      disown 2>/dev/null || true
      sleep 1
      echo "${P}  ${GREEN}✓ Watchdog ON for '$fname' (har ${dsec}s check karega).${R}"
      sleep 2
      ;;
    [mM]*) target_menu "$fname" ;;
    *) return ;;
  esac
}

new_scan_manual() {
  update_geom
  clear
  title_box " 🎯 MANUAL TARGET ENTRY " "Enter HackerOne Handle"
  echo ""
  echo "${P}  ${B}Enter program handle:${R}"
  echo "${P}  ${MUTED}(e.g. shopify, uber, gitlab, airbnb — enter '0' or 'b' to go back)${R}"
  echo ""
  sep
  local handle
  read -r -p "${P}  ${B}Handle [0 to Cancel]:${R} " handle
  handle="$(echo "$handle" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
  if [ -z "$handle" ] || [ "$handle" = "0" ] || [ "$handle" = "b" ] || [ "$handle" = "q" ]; then
    return
  fi
  if [[ ! "$handle" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo ""
    echo "${P}  ${RED}✗ Invalid program handle: '$handle'. Only alphanumeric characters, hyphens, and underscores are allowed.${R}"
    sleep 2
    return
  fi

  local fname
  fname="$(normalize_name "$handle")"

  if [ -d "$WS/$fname" ] && [ -f "$WS/$fname/scope.yaml" ]; then
    echo ""
    echo "${P}  ${GOLD}⚠ Target '$fname' already exists in workspace.${R}"
    read -r -p "${P}  Usi target ka menu open karein? [Y/n]: " om
    if [[ ! "$om" =~ ^[nN]$ ]]; then
      target_menu "$fname"
    fi
    return
  fi

  echo ""
  echo "${P}  ${CYAN}◌ Setting up target workspace for '$handle'...${R}"

  local h1_synced=0
  if [ -n "${H1_USERNAME:-}" ] && [ -n "${H1_API_TOKEN:-}" ]; then
    if python3 "$WS/recon/h1_client.py" --setup "$handle" --folder "$fname" 2>/dev/null; then
      h1_synced=1
    fi
  fi

  if [ "$h1_synced" -eq 0 ]; then
    create_target_folder "$fname" "$handle"
    echo "${P}  ${GREEN}✓${R} Created target scaffold: ${B}$fname/${R}"
    echo "${P}  ${MUTED}Kripya $fname/scope.yaml aur $fname/SCOPE.md me roots verify karein.${R}"
  fi

  echo ""
  title_box " TARGET CONFIGURED: $fname " "Ready for Autonomous Hunting"
  echo "${P}  ${B}Next Action for [$fname]:${R}"
  opt "C" "🚀 Run COMPLETE SCAN & PRE-FILL AGENT HUNT" "Recommended autonomous pipeline"
  opt "M" "🎯 Open Target Mission Control Menu"        "Target operations dashboard"
  opt "0" "↩ Return to Main Menu"                     "Mission control home"
  echo ""
  sep
  local post_act
  read -r -p "${P}  ${B}Choice [C/M/0, or B to return]:${R} " post_act
  case "$post_act" in
    [cC]*)
      run_complete_hunt "$fname"
      ;;
    [mM]*)
      target_menu "$fname"
      ;;
    *)
      return
      ;;
  esac
}

new_scan() {
  while true; do
    update_geom
    clear
    title_box " ⚡ TARGET DISCOVERY & PROVISIONING " "HackerOne Bug Bounty Programs"
    echo ""
    echo "${P}  ${B}Select Scan & Discovery Type:${R}"
    echo ""
    opt "1" '💰 Cash Bounties Only ($$$)'   "fetch only paid programs with guaranteed rewards"
    opt "2" "🌐 All Programs (Paid + VDP)"   "bounty programs + vulnerability disclosure"
    opt "3" "🎯 Manual Program Handle"      "type any handle e.g. shopify, gitlab, uber"
    opt "4" "🌱 Find Newer/Less-Crowded Programs" "sorted by newest-on-HackerOne first"
    opt "5" "🏢 Company — Monitor Own Domain"    "no HackerOne program — for companies scanning their own infra"
    opt "0" "↩ Back to Main Menu"           "return to mission control"
    echo ""
    sep
    local s_mode
    read -r -p "${P}  ${B}Select Scan Type [0-5, or B to return]:${R} " s_mode

    case "$s_mode" in
      0|[bB]*|[qQ]*)
        return
        ;;
      5)
        setup_company_target
        return
        ;;
      1|2|4)
        local bounty_flag="" sort_flag=""
        local scan_title="ALL HACKERONE PROGRAMS"
        if [ "$s_mode" = "1" ]; then
          bounty_flag="--bounty-only"
          scan_title="PAID CASH BOUNTY PROGRAMS"
        elif [ "$s_mode" = "4" ]; then
          bounty_flag="--bounty-only"
          sort_flag="--sort-recency"
          scan_title="NEWEST PROGRAMS ON HACKERONE (potentially less-crowded — not a guarantee)"
        fi

        if [ -z "${H1_USERNAME:-}" ] || [ -z "${H1_API_TOKEN:-}" ]; then
          echo ""
          echo "${P}  ${RED}⚠ H1_USERNAME ya H1_API_TOKEN set nahi hain.${R}"
          echo "${P}  ${MUTED}Auto-discovery ke liye credentials zaroori hain.${R}"
          echo ""
          echo "${P}  [1] Ab set karo (wizard)   [2] Manual handle enter karo   [0] Cancel"
          local mh
          read -r -p "${P}  Choice: " mh
          case "$mh" in
            1) setup_h1_credentials; continue ;;
            2) new_scan_manual; return ;;
            *) continue ;;
          esac
        fi

        echo ""
        echo "${P}  ${B}${CYAN}⚡ INITIATING LIVE HACKERONE DISCOVERY...${R}"
        echo ""

        # Live scanning with verbose progress steps visible to user
        local raw_json
        raw_json=$(python3 "$WS/recon/h1_client.py" --list $bounty_flag $sort_flag --verbose --json)

        if [ -z "$raw_json" ] || [ "$raw_json" = "[]" ]; then
          echo ""
          echo "${P}  ${RED}✗ Koi naya eligible program nahi mila ya network issue hai.${R}"
          read -r -p "${P}  Press Enter or [0] to return... " _
          continue
        fi

        # Parse into arrays
        local handles=() names=() bounties=()
        while IFS='|' read -r h n b; do
          [ -n "$h" ] && handles+=("$h") && names+=("$n") && bounties+=("$b")
        done < <(python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    b = '💰 Bounty' if p.get('offers_bounties') else 'ℹ VDP'
    started = (p.get('started_accepting_at') or '')[:10]
    if started:
        b = f'{b} (since {started})'
    print(f\"{p['handle']}|{p['name']}|{b}\")
" <<< "$raw_json")

        local count="${#handles[@]}"
        if [ "$count" -eq 0 ]; then
          echo "${P}  ${GOLD}Koi naya program nahi mila (sab already workspace me hain).${R}"
          read -r -p "${P}  Press Enter or [0] to return... " _
          continue
        fi

        # Paginated Program Browser (10 programs per page)
        local page=1 page_size=10
        local total_pages=$(( (count + page_size - 1) / page_size ))

        while true; do
          update_geom
          clear
          local start_idx=$(( (page - 1) * page_size ))
          local end_idx=$(( start_idx + page_size ))
          [ "$end_idx" -gt "$count" ] && end_idx="$count"

          title_box " $scan_title ($count) " "Page $page of $total_pages · Showing $((start_idx+1))-$end_idx of $count"
          echo ""
          printf "%s   ${MUTED}%-5s %-18s %-34s %-12s${R}\n" "$P" "#" "HANDLE" "PROGRAM NAME" "TYPE"
          sep
          local i
          for ((i=start_idx; i<end_idx; i++)); do
            local b_color="$MUTED"
            [[ "${bounties[$i]}" =~ "Bounty" ]] && b_color="$GOLD"
            printf "%s  ${GREEN}%3d${R}   ${B}%-18s${R} %-34s ${b_color}%s${R}\n" \
              "$P" "$((i+1))" "${handles[$i]}" "${names[$i]:0:32}" "${bounties[$i]}"
          done
          sep

          local nav_str=""
          [ "$page" -lt "$total_pages" ] && nav_str="${GREEN}[N]${R} Next Page ❯   "
          [ "$page" -gt 1 ] && nav_str="${nav_str}${CYAN}[P]${R} ❮ Prev Page   "
          nav_str="${nav_str}${MUTED}[0]${R} ↩ Back to Discovery   ${MUTED}[B]${R} ↩ Main Menu"
          echo "${P}  $nav_str"
          echo ""

          local sel
          read -r -p "${P}  ${B}Select Target [1-$count], Page [N/P], or [0/B to go back]:${R} " sel

          case "$sel" in
            [nN]*)
              if [ "$page" -lt "$total_pages" ]; then
                page=$((page + 1))
              else
                echo "${P}  ${GOLD}Aap pehle hi aakhri page ($total_pages) par hain.${R}"; sleep 1
              fi
              continue
              ;;
            [pP]*)
              if [ "$page" -gt 1 ]; then
                page=$((page - 1))
              else
                echo "${P}  ${GOLD}Aap pehle page (1) par hain.${R}"; sleep 1
              fi
              continue
              ;;
            0)
              # Back to discovery type menu
              break
              ;;
            [bB]*|[qQ]*)
              # Back to main menu
              return
              ;;
            *)
              if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -le "$count" ]; then
                local picked_handle="${handles[$((sel-1))]}"
                echo ""
                echo "${P}  ${CYAN}◌ Provisioning target workspace for '${picked_handle}' from H1 API...${R}"
                python3 "$WS/recon/h1_client.py" --setup "$picked_handle"
                local folder_name
                folder_name="$(normalize_name "$picked_handle")"
                echo ""
                title_box " TARGET CONFIGURED: $folder_name " "Ready for Autonomous Hunting"
                echo "${P}  ${GREEN}✓${R} Target workspace configured: ${B}$folder_name/${R}"
                echo ""
                echo "${P}  ${B}Next Action for [$folder_name]:${R}"
                opt "C" "🚀 Run COMPLETE SCAN & PRE-FILL AGENT HUNT" "Recommended"
                opt "M" "🎯 Open Target Mission Control Menu"        "Target operations dashboard"
                opt "0" "↩ Return to Main Menu"                     "Mission control home"
                echo ""
                sep
                local post_act
                read -r -p "${P}  ${B}Choice [C/M/0, or B to return]:${R} " post_act
                case "$post_act" in
                  [cC]*)
                    run_complete_hunt "$folder_name"
                    return
                    ;;
                  [mM]*)
                    target_menu "$folder_name"
                    return
                    ;;
                  *)
                    return
                    ;;
                esac
              else
                echo "${P}  ${RED}Invalid selection. Kripya 1-$count, N, P ya 0/B enter karein.${R}"; sleep 1
              fi
              ;;
          esac
        done
        ;;

      3)
        new_scan_manual
        ;;

      *)
        echo "${P}  ${RED}Invalid choice.${R}"; sleep 1
        ;;
    esac
  done
}

# =============================================================================
# Splash Screen
# =============================================================================
splash() {
  local rc
  # Unlike every menu screen (each its own `while true: update_geom; clear;
  # draw; read; case; done` loop that naturally redraws when a WINCH-
  # interrupted read falls through), splash() used to draw ONCE and then
  # block on a single read. The launcher opens xfce4-terminal at a fixed
  # --geometry=120x36 (see the desktop auto-wrap block near the top of this
  # file); if the user maximizes/resizes the window WHILE splash is still
  # sitting on "Press Enter..." (the common case — they see the banner, then
  # maximize, then press Enter), the banner had already been centered for
  # the OLD 120-column width and nothing ever redrew it for the new size —
  # printed terminal text doesn't reflow on its own when the window grows.
  # This loops the same way every other screen does: a WINCH interrupts the
  # read (bash reports that as a non-zero exit status with no character
  # captured), so it redraws at the new geometry and waits again; only an
  # actual keypress (exit status 0) breaks out.
  while true; do
    clear
    echo ""
    center_block "
  ████████╗██████╗ ██╗ █████╗  ██████╗ ███████╗██████╗ ██╗██╗      ██████╗ ████████╗
  ╚══██╔══╝██╔══██╗██║██╔══██╗██╔════╝ ██╔════╝██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
     ██║   ██████╔╝██║███████║██║  ███╗█████╗  ██████╔╝██║██║     ██║   ██║   ██║
     ██║   ██╔══██╗██║██╔══██║██║   ██║██╔══╝  ██╔═══╝ ██║██║     ██║   ██║   ██║
     ██║   ██║  ██║██║██║  ██║╚██████╔╝███████╗██║     ██║███████╗╚██████╔╝   ██║
     ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚══════╝ ╚═════╝    ╚═╝
" "${CYAN}"
    echo ""
    center "${B}${GOLD}v1.0.0${R} ${MUTED}—${R} ${B}${CYAN}MISSION CONTROL — AUTONOMOUS BUG BOUNTY SUITE${R}"
    echo ""
    center "${MUTED}Workspace:${R}  $WS"
    center "${MUTED}Targets:${R}    $(existing_targets | grep -c .) active"
    center "${MUTED}Engine:${R}     H1 API · Katana · Nuclei · Intelligence Scoring · OpenCode Agent"
    echo ""
    center "${LINE}────────────────────────────────────────────────────────────${R}"
    center "${MUTED}Legal First: SIRF in-scope authorized targets.${R}"
    echo ""
    if [ "${BASH_LAUNCHER_SKIP_SPLASH:-0}" != "1" ]; then
      center "Press Enter to enter Mission Control..."
      read -r -s -n1
      rc=$?
      # A trapped signal (WINCH) interrupting `read` reports an exit status
      # > 128 in bash — that's the "redraw and wait again" case. Anything
      # else (0 = real keypress, 1 = stdin closed/EOF) must break out, or a
      # closed/non-interactive stdin with this var unset would spin this
      # loop forever redrawing instead of just proceeding like the old
      # single-shot version did.
      [ "$rc" -le 128 ] && break
    else
      break
    fi
  done
}

# =============================================================================
# Continuous Recon Daemon Menu
# =============================================================================
# =============================================================================
# Watchdog — continuous monitoring for one site (company mode ya HackerOne
# program dono ke liye). Real engine: recon/daemon.py (delta-detect: naya
# subdomain/endpoint dikhe to khud scan+verify+notify karta hai).
# =============================================================================
_watchdog_pick_target() {
  # Prints the chosen target handle to stdout, or nothing if cancelled.
  # Lists existing target-folders (numbered) so nothing is hardcoded/assumed.
  local targets=() t n=0
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    n=$((n+1))
    targets+=("$t")
    echo "${P}    ${GREEN}${n}${R}  $t" >&2
  done < <(existing_targets)
  echo "${P}    ${MUTED}(ya naya handle type karo)${R}" >&2
  echo "" >&2
  local pick
  read -r -p "${P}  Target [number ya handle, 0 to cancel]: " pick >&2
  [ -z "$pick" ] || [ "$pick" = "0" ] && return 1
  if [[ "$pick" =~ ^[0-9]+$ ]] && [ "$pick" -ge 1 ] && [ "$pick" -le "$n" ]; then
    echo "${targets[$((pick-1))]}"
  else
    echo "$pick"
  fi
  return 0
}

daemon_menu() {
  while true; do
    update_geom
    clear
    title_box " 🐕 WATCHDOG — SITE MONITORING " "Apna site daalo, monitoring khud chalti rahegi"
    echo ""
    echo "${P}  Status: $(python3 "$WS/recon/daemon.py" --status)"
    echo ""
    sep
    opt "1" "Turn ON Watchdog (choose interval)" "Continuously monitor ek site — naya asset dikhe to auto-scan+notify"
    opt "2" "Run Single Check Now (no loop)"     "Ek baar delta-check karo, exit ho jao"
    opt "3" "Turn OFF Watchdog"                  "Terminate background monitor process"
    opt "0" "↩ Return to Main Menu"              "Back to Mission Control"
    echo ""
    sep
    local dc
    read -r -p "${P}  Choice [0-3, or B to return]: " dc
    case "$dc" in
      1)
        echo ""
        echo "${P}  ${B}Kaunsa site monitor karna hai?${R}"
        local dt
        dt="$(_watchdog_pick_target)" || { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; continue; }
        [ -z "$dt" ] && { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; continue; }
        echo ""
        echo "${P}  ${B}Kitni der mein check kare?${R}"
        opt "1" "15 minute"  "Bahut frequent — chhote site ke liye"
        opt "2" "1 ghanta"   "Default, zyada tools ke liye reasonable"
        opt "3" "6 ghante"   "Kam-frequent, kam load"
        opt "4" "24 ghante"  "Din mein ek baar"
        opt "5" "Custom (seconds mein type karo)" ""
        local ic dsec
        read -r -p "${P}  Choice [1-5]: " ic
        case "$ic" in
          1) dsec=900 ;;
          2) dsec=3600 ;;
          3) dsec=21600 ;;
          4) dsec=86400 ;;
          5) read -r -p "${P}  Interval seconds mein: " dsec; [ -z "$dsec" ] && dsec=3600 ;;
          *) dsec=3600 ;;
        esac
        nohup python3 "$WS/recon/daemon.py" --program "$dt" --interval "$dsec" > "$WS/recon/data/daemon.log" 2>&1 &
        disown 2>/dev/null || true
        sleep 1
        echo "${P}  ${GREEN}✓ Watchdog ON for '$dt' (har ${dsec}s check karega).${R}"
        python3 "$WS/recon/daemon.py" --status
        sleep 2
        ;;
      2)
        echo ""
        local dt
        dt="$(_watchdog_pick_target)" || { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; continue; }
        [ -z "$dt" ] && { echo "${P}  ${MUTED}Cancelled.${R}"; sleep 1; continue; }
        python3 "$WS/recon/daemon.py" --program "$dt" --once
        echo ""
        sep
        read -r -p "${P}  Press Enter to continue..." _
        ;;
      3)
        echo ""
        python3 "$WS/recon/daemon.py" --stop
        sleep 1
        ;;
      0|[bB]*)
        return
        ;;
      *)
        ;;
    esac
  done
}

# =============================================================================
# Main Menu
# =============================================================================
account_status_line() {
  local raw
  raw=$(python3 "$WS/recon/account_client.py" --status-line 2>/dev/null)
  case "$raw" in
    NOT_LOGGED_IN)
      echo "${GOLD}⚠ Not logged in${R} ${MUTED}— Main Menu [A] se account banao/login karo${R}" ;;
    ERROR\|*)
      echo "${MUTED}Account status unavailable (${raw#ERROR|})${R}" ;;
    *\|*\|*)
      local email tier remaining trial_info
      IFS='|' read -r email tier remaining trial_info <<< "$raw"
      local trial_suffix=""
      if [ -n "$trial_info" ]; then
        trial_suffix=" ${GOLD}[$trial_info]${R}"
      fi
      echo "${GREEN}✓${R} ${B}$email${R} ${MUTED}| $tier tier | $remaining scans left today${R}${trial_suffix}" ;;
    *)
      echo "${MUTED}Account status unavailable${R}" ;;
  esac
}

# =============================================================================
# First-run onboarding — triggers once (no .env.account yet) before the main
# menu, so a brand-new user (or company) doesn't land on an empty menu with no
# guidance. Fully skippable at every step; never runs for --auto/--daemon
# non-interactive invocations (see bottom of file).
# =============================================================================
onboarding_wizard() {
  [ -f "$WS/.env.account" ] && return
  clear
  title_box " 👋 WELCOME — FIRST-TIME SETUP " "Takes about 2 minutes, skippable anytime"
  echo ""
  echo "${P}  ${B}Kaun use kar raha hai?${R}"
  opt "1" "🎯 Individual bug-bounty hunter" "HackerOne programs par hunt karna hai"
  opt "2" "🏢 Company — apna domain monitor karna hai" "apni khud ki infra scan karni hai, no HackerOne"
  opt "0" "⏭  Skip abhi ke liye" "Main Menu se baad mein kabhi bhi [A]/[H] se setup kar sakte ho"
  echo ""
  sep
  local wtype
  read -r -p "${P}  Choice: " wtype
  [ "$wtype" != "1" ] && [ "$wtype" != "2" ] && return

  echo ""
  echo "${P}  ${B}Step 1/2 — Account (login/subscription)${R}"
  setup_account
  [ ! -f "$WS/.env.account" ] && return   # user cancelled account setup — stop here

  case "$wtype" in
    1)
      echo ""
      echo "${P}  ${B}Step 2/2 — Tumhara HackerOne account${R}"
      setup_h1_credentials
      echo ""
      read -r -p "${P}  Ab pehla program dhoondhna shuru karein? [Y/n]: " go
      [[ ! "$go" =~ ^[nN]$ ]] && new_scan
      ;;
    2)
      echo ""
      echo "${P}  ${B}Step 2/2 — Apna pehla domain add karo${R}"
      setup_company_target
      ;;
  esac
}

main_menu() {
  while true; do
    update_geom
    clear
    title_box " ⚡ TRIAGEPILOT — MISSION CONTROL " "HackerOne Hunting & Attack Surface Suite  ·  v1.0.0"
    echo ""
    echo "${P}  $(account_status_line)"
    echo ""
    echo "${P}  ${B}Mission Actions:${R}"
    opt "N" "⚡ Start NEW Scan"          "discover new HackerOne targets (Cash Bounty / All)"
    opt "P" "🚀 Autopilot (ON/OFF)"      "auto-pick target, auto-scan, auto-next — one switch"
    opt "M" "🐕 Watchdog (site monitoring)" "apna site daalo, continuously monitor hota rahega — interval-configurable"
    opt "T" "📱 Telegram & Phone Alerts" "pair phone number & setup telegram notifications"
    opt "H" "🔑 HackerOne API Credentials" "your own H1 account — needed to auto-discover programs"
    opt "W" "🛡  WPScan API Token"       "enables automated WordPress vulnerability checks"
    opt "A" "👤 Account (login/status)"  "subscription tier & daily scan quota"
    opt "D" "🔍 System Diagnostics"      "tools, APIs, Docker & environment audit"
    opt "V" "📊 Dashboard (all targets)" "candidates, verified findings, last run — one screen"
    opt "J" "⚙  Background Jobs"         "what's actually running right now"
    opt "Q" "🚪 Quit"                    "exit mission control"
    echo ""
    sep
    local target_count
    target_count=$(existing_targets | grep -c .)
    section_hdr "ACTIVE TARGET WORKSPACES ($target_count)"
    local targets=() t n=0
    while IFS= read -r t; do
      [ -z "$t" ] && continue
      n=$((n+1))
      targets+=("$t")
      local stats
      stats=$(target_stats "$t")
      printf "%s   ${GREEN}%2d${R}  ${B}%-16s${R} %s\n" "$P" "$n" "$t" "$stats"
    done < <(existing_targets)
    [ "$n" -eq 0 ] && echo "${P}     ${MUTED}(koi target nahi — [N] se naya scan start karein)${R}"
    echo ""
    sep
    local choice
    read -r -p "${P}  ${B}Select Target [1-$n] or Action [N/P/M/T/H/W/A/D/V/J/Q]:${R} " choice

    case "$choice" in
      [nN]*) new_scan ;;
      [pP]*) autopilot_menu ;;
      [mM]*) daemon_menu ;;
      [tT]*) python3 "$WS/recon/notify.py" --setup-telegram ;;
      [hH]*) setup_h1_credentials ;;
      [wW]*) setup_wpscan_token ;;
      [aA]*) setup_account ;;
      [dD]*) diagnostics_check ;;
      [vV]*) show_dashboard ;;
      [jJ]*) show_background_jobs ;;
      [qQ]*) echo "${P}  Happy hunting. Bye!"; exit 0 ;;
      *)
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$n" ]; then
          local picked="${targets[$((choice-1))]}"
          target_menu "$picked"
        else
          echo "${P}  ${RED}Invalid choice.${R}"; sleep 1
        fi
        ;;
    esac
  done
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  if [ "${1:-}" = "--auto" ] && [ -n "${2:-}" ]; then
    auto_tgt="$2"
    fresh_flag="${3:-}"
    if [[ ! "$auto_tgt" =~ ^[a-zA-Z0-9_-]+$ ]]; then
      echo "Error: Invalid target name '$auto_tgt'. Only alphanumeric, hyphen, and underscore allowed." >&2
      exit 1
    fi
    if [ -n "$fresh_flag" ]; then
      run_zero_touch_hunt "$auto_tgt" "$fresh_flag"
    else
      run_zero_touch_hunt "$auto_tgt"
    fi
    exit 0
  fi
  if [ "${1:-}" = "--daemon" ]; then
    shift
    python3 "$WS/recon/daemon.py" "$@"
    exit 0
  fi
  splash
  onboarding_wizard
  main_menu
fi

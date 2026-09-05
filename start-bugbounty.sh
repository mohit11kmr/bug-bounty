#!/usr/bin/env bash
# =============================================================================
# Bug Bounty — Mission Control & Launcher
# Terminal / Desktop click: Live stats, target sub-menus, pre-flight diagnostics,
# and recon diff engine.
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
if [ ! -t 1 ] && [ "${BASH_LAUNCHER_NOTTY:-0}" != "1" ]; then
  exec xfce4-terminal --title="Bug Bounty — Mission Control" \
    --geometry=115x34 --working-directory="$WS" \
    -e "bash -lc 'exec \"$0\"'"
fi

cd "$WS" || exit 1

# =============================================================================
# UI primitives
# =============================================================================
W=60   # box inner width
sep()  { printf "${LINE}%s${R}\n" "$(printf '─%.0s' $(seq 1 "$W"))"; }

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

center() {
  local txt="$1" w len
  w="${COLUMNS:-$(tput cols 2>/dev/null || echo 80)}"
  len="$(printf '%s' "$txt" | sed 's/\x1b\[[0-9;]*m//g' | wc -c)"
  printf "%$(( (w - len) / 2 ))s%s\n" "" "$txt"
}

center_block() {
  local block="$1" color="$2" w max=0 len line lines=()
  w="${COLUMNS:-$(tput cols 2>/dev/null || echo 80)}"
  while IFS= read -r line; do
    len="${#line}"
    [ "$len" -gt "$max" ] && max="$len"
    lines+=("$line")
  done <<< "$block"
  for line in "${lines[@]}"; do
    printf "%$(( (w - max) / 2 ))s${color}%s${R}\n" "" "$line"
  done
}

# =============================================================================
# Helpers & Stats Engine
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

  if [ "$target" = "general" ]; then
    printf "${DIM}Local Lab / Practice${R}"
    return
  fi

  local n_assets=0 n_endpoints=0 n_cands=0 top_score=0
  [ -f "$a_file" ] && n_assets=$(grep -c '"host":' "$a_file" 2>/dev/null || echo 0)
  [ -f "$e_file" ] && n_endpoints=$(grep -c '"url":' "$e_file" 2>/dev/null || echo 0)

  if [ -f "$db_file" ] && command -v sqlite3 >/dev/null 2>&1; then
    local row
    row=$(sqlite3 "$db_file" "SELECT count(*), COALESCE(max(score), 0) FROM candidate_findings;" 2>/dev/null || echo "0|0")
    n_cands=$(echo "$row" | cut -d'|' -f1)
    top_score=$(echo "$row" | cut -d'|' -f2)
  fi

  if [ "$n_assets" -gt 0 ] || [ "$n_endpoints" -gt 0 ]; then
    printf "${G}🟢 %s hosts · %s URLs · %s cands (Top: %s)${R}" \
      "$n_assets" "$n_endpoints" "$n_cands" "$top_score"
  else
    printf "${Y}🟡 Scope ready · Scan pending${R}"
  fi
}

check_opencode() {
  if ! command -v "$OPCODE_BIN" >/dev/null 2>&1 && [ ! -x "$OPCODE_BIN" ]; then
    echo ""
    echo "  ${Y}⚠ opencode binary nahi mila.${R}"
    echo "  ${DIM}Agent features ke liye install karein:${R} ${C}curl -fsSL https://opencode.ai/install | bash${R}"
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
# Har session: H1 scope APIs se sync karo. Test-cred/password YAHAN kabhi nahi.
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
  [ -f "$tdir/SCOPE.md" ] || cat > "$tdir/SCOPE.md" <<MD
# $handle — Program Scope

> launcher ne naya target folder banaya. Pehle kaam: H1 scope + exclusions verify,
> yahan roots/excluded fill karo, phir session shuru.
MD
  [ -f "$tdir/NOTES.md" ] || echo "# $handle — Hunt Progress" > "$tdir/NOTES.md"
}

# =============================================================================
# Pre-Flight Diagnostics
# =============================================================================
diagnostics_check() {
  clear
  title_box " PRE-FLIGHT SYSTEM DIAGNOSTICS "
  echo ""
  echo "  ${B}1. Core Security Tools:${R}"
  local tools=("subfinder" "dnsx" "httpx" "gau" "katana" "nuclei" "ffuf" "dalfox" "sqlmap" "jadx")
  for t in "${tools[@]}"; do
    if command -v "$t" >/dev/null 2>&1; then
      printf "    ${G}✓${R} %-12s ${DIM}%s${R}\n" "$t" "$(command -v "$t")"
    else
      printf "    ${RED}✗${R} %-12s ${RED}NOT FOUND${R}\n" "$t"
    fi
  done

  echo ""
  echo "  ${B}2. Services & Environment:${R}"
  if docker info >/dev/null 2>&1; then
    printf "    ${G}✓${R} %-12s ${DIM}running${R}\n" "Docker"
  else
    printf "    ${Y}⚠${R} %-12s ${DIM}stopped (sudo systemctl start docker)${R}\n" "Docker"
  fi

  if command -v "$OPCODE_BIN" >/dev/null 2>&1 || [ -x "$OPCODE_BIN" ]; then
    printf "    ${G}✓${R} %-12s ${DIM}%s${R}\n" "OpenCode" "$OPCODE_BIN"
  else
    printf "    ${Y}⚠${R} %-12s ${DIM}not installed (curl -fsSL https://opencode.ai/install | bash)${R}\n" "OpenCode"
  fi

  echo ""
  echo "  ${B}3. HackerOne API Credentials:${R}"
  if [ -n "${H1_USERNAME:-}" ]; then
    printf "    ${G}✓${R} %-14s ${DIM}%s${R}\n" "H1_USERNAME" "${H1_USERNAME:0:3}***"
  else
    printf "    ${Y}⚠${R} %-14s ${DIM}not set in environment${R}\n" "H1_USERNAME"
  fi
  if [ -n "${H1_API_TOKEN:-}" ]; then
    printf "    ${G}✓${R} %-14s ${DIM}configured (hidden)${R}\n" "H1_API_TOKEN"
  else
    printf "    ${Y}⚠${R} %-14s ${DIM}not set in environment${R}\n" "H1_API_TOKEN"
  fi

  echo ""
  read -r -p "  Press Enter to return..."
}

# =============================================================================
# Recon Diff Engine
# =============================================================================
target_diff() {
  local target="$1"
  local sfile="$WS/$target/scope.yaml"
  local afile="$WS/recon/data/$target/assets.json"

  if [ ! -f "$sfile" ]; then
    echo "  ${RED}scope.yaml nahi mila: $sfile${R}"
    read -r -p "  Press Enter..."
    return
  fi

  echo ""
  title_box " RECON DIFF ENGINE: $target "
  echo ""
  echo "  ${DIM}Extracting in-scope roots from scope.yaml...${R}"

  local roots
  roots=$(python3 -c "import yaml; s = yaml.safe_load(open('$sfile')); print('\n'.join(s.get('roots', [])))" 2>/dev/null)

  if [ -z "$roots" ]; then
    echo "  ${Y}Roots khali hain scope.yaml me.${R}"
    read -r -p "  Press Enter..."
    return
  fi

  echo "  Roots: $(echo "$roots" | tr '\n' ' ')"
  echo ""
  echo "  ${Y}◌${R} Running fast passive subdomain discovery..."

  local raw_dir="$WS/recon/data/$target/raw"
  mkdir -p "$raw_dir"
  local tmp_current="$raw_dir/diff_current.txt"
  rm -f "$tmp_current"
  while IFS= read -r r; do
    [ -n "$r" ] && subfinder -d "$r" -silent 2>/dev/null >> "$tmp_current"
  done <<< "$roots"

  if [ ! -f "$tmp_current" ] || [ ! -s "$tmp_current" ]; then
    echo "  ${Y}Koi subdomain return nahi hua.${R}"
    read -r -p "  Press Enter..."
    return
  fi

  sort -u -o "$tmp_current" "$tmp_current"
  local total_now
  total_now=$(wc -l < "$tmp_current")
  echo "  ${G}✓${R} Live subdomains found now: ${B}$total_now${R}"

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
      echo "  ${G}${B}🚨 NAYE SUBDOMAINS MIL GAYE (New Attack Surface):${R}"
      while IFS= read -r sub; do
        printf "    ${G}+ %s${R}\n" "$sub"
      done <<< "$new_subs"
    else
      echo "  ${DIM}Koi naya subdomain nahi mila (Attack surface unchanged).${R}"
    fi
  else
    echo "  ${DIM}Pehle ka assets.json nahi mila (Pehli baar recon chalaayein).${R}"
  fi

  rm -f "$tmp_current" "$tmp_known"
  echo ""
  read -r -p "  Press Enter to return..."
}

# =============================================================================
# Target Action Sub-Menu
# =============================================================================
target_menu() {
  local target="$1"
  while true; do
    clear
    title_box " MISSION CONTROL: $target "
    echo ""
    echo "  Target:  ${B}${C}$target${R}"
    echo "  Status:  $(target_stats "$target")"
    echo ""
    sep
    echo "  ${B}Target Actions:${R}"
    opt "1" "Interactive Shell / Session" "Terminal hunting session"
    opt "2" "Full Recon Pipeline"         "subfinder → httpx → gau → js_miner"
    opt "3" "Deep JS Miner (Katana)"     "client-side routes & secret extraction"
    opt "4" "Safe Vulnerability Scan"    "Nuclei rate-limited prober"
    opt "5" "View Candidate Report"      "Top-40 scored findings queue"
    opt "6" "Recon Diff Engine"          "Check for newly deployed subdomains"
    opt "7" "View Scope & Notes"         "SCOPE.md & NOTES.md"
    opt "0" "Back to Main Menu"          ""
    echo ""
    sep
    read -r -p "  ${B}Action for [$target]${R} [0-7]: " act

    case "$act" in
      1)
        cd "$WS/$target"
        if check_opencode; then
          echo ""
          echo "  [1] OpenCode AI Session  [2] Interactive Bash Shell"
          read -r -p "  Choice [1-2]: " sc
          if [ "$sc" = "1" ]; then
            exec "$OPCODE_BIN"
          else
            PS1="[bug-bounty:$target]\$ " bash --norc -i
          fi
        else
          PS1="[bug-bounty:$target]\$ " bash --norc -i
        fi
        ;;
      2)
        echo ""
        python3 "$WS/recon/recon_pipeline.py" --program "$target"
        echo ""
        read -r -p "  Recon complete. Press Enter to continue..."
        ;;
      3)
        echo ""
        echo "  [1] Dry-run safe check  [2] Live JS Crawl"
        read -r -p "  Choice [1-2]: " jc
        if [ "$jc" = "2" ]; then
          python3 "$WS/recon/js_miner.py" --program "$target"
        else
          python3 "$WS/recon/js_miner.py" --program "$target" --dry-run
        fi
        echo ""
        read -r -p "  JS Miner complete. Press Enter to continue..."
        ;;
      4)
        echo ""
        echo "  [1] Dry-run safe check  [2] Live Nuclei scan"
        read -r -p "  Choice [1-2]: " nc
        if [ "$nc" = "1" ]; then
          python3 "$WS/recon/scanner.py" --program "$target" --dry-run
        else
          python3 "$WS/recon/scanner.py" --program "$target"
        fi
        echo ""
        read -r -p "  Scan complete. Press Enter to continue..."
        ;;
      5)
        echo ""
        local rep="$WS/recon/data/$target/candidate_report.md"
        if [ -f "$rep" ]; then
          clear
          cat "$rep"
        else
          echo "  ${Y}candidate_report.md nahi mila. Abhi intelligence run karein? [Y/n]${R}"
          read -r -p "  Choice: " ir
          if [[ ! "$ir" =~ ^[nN]$ ]]; then
            python3 "$WS/recon/intelligence.py" --program "$target" --top 40
            [ -f "$rep" ] && cat "$rep"
          fi
        fi
        echo ""
        read -r -p "  Press Enter to return..."
        ;;
      6)
        target_diff "$target"
        ;;
      7)
        clear
        echo "=== $target/SCOPE.md ==="
        [ -f "$WS/$target/SCOPE.md" ] && cat "$WS/$target/SCOPE.md"
        echo ""
        echo "=== $target/NOTES.md ==="
        [ -f "$WS/$target/NOTES.md" ] && cat "$WS/$target/NOTES.md"
        echo ""
        read -r -p "  Press Enter to return..."
        ;;
      0)
        return
        ;;
      *)
        echo "  ${RED}Invalid choice.${R}"; sleep 1
        ;;
    esac
  done
}

# =============================================================================
# Flow 1 — Start NEW scan (agent-driven target discovery)
# =============================================================================
new_scan() {
  echo ""
  title_box " START NEW SCAN "
  echo ""
  check_opencode || return
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

  local candidates=() line handle name
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
    local cand="${candidates[$((sel-1))]}"
    local handle="${cand%% | *}"
    local prog_name="${cand#* | }"
    local fname dup
    fname="$(normalize_name "$handle")"
    dup=""
    while IFS= read -r t; do
      [ "$(normalize_name "$t")" = "$fname" ] && dup="$t" && break
    done < <(existing_targets)
    if [ -n "$dup" ]; then
      echo ""
      echo "  ${Y}⚠ '$fname' ka folder already hai ($dup).${R}"
      read -r -p "  Usi me open karun? [${G}y${R}/${DIM}N${R}]: " ans
      if [[ "$ans" =~ ^[yY]$ ]]; then
        target_menu "$dup"
      fi
      return
    fi
    create_target_folder "$fname" "$prog_name"
    echo ""
    echo "  ${G}✓${R} ${B}Target folder banaya: ${C}$fname/${R}"
    target_menu "$fname"
  else
    echo "  ${Y}Cancelled.${R}"
  fi
  return
}

# =============================================================================
# Splash Screen
# =============================================================================
splash() {
  clear
  echo ""
  center_block "██████╗  ██████╗ 
██╔══██╗██╔══██╗
██████╔╝██████╔╝
██╔══██╗██╔══██╗
██████╔╝██████╔╝
╚═════╝ ╚═════╝" "${C}"
  echo ""
  center "${B}${C}BUG BOUNTY — MISSION CONTROL${R}"
  echo ""
  center "${DIM}Workspace:${R}  $WS"
  center "${DIM}Targets:${R}    $(existing_targets | grep -c .) active"
  center "${DIM}Pipeline:${R}   recon → scanner → js_miner → intelligence"
  echo ""
  center "${LINE}──────────────────────────────────────────────${R}"
  center "${DIM}Legal first: SIRF in-scope authorized targets.${R}"
  echo ""
  if [ "${BASH_LAUNCHER_SKIP_SPLASH:-0}" != "1" ]; then
    center "Press Enter to enter Mission Control..."
    read -r -s -n1
  fi
}

# =============================================================================
# Main Menu
# =============================================================================
main_menu() {
  while true; do
    clear
    title_box " BUG BOUNTY — MISSION CONTROL "
    echo ""
    echo "  ${B}Main Actions:${R}"
    opt "N" "Start NEW scan"       "discover new HackerOne target"
    opt "D" "System Diagnostics"   "tools, APIs & environment audit"
    opt "Q" "Quit"                 "exit mission control"
    echo ""
    sep
    echo "  ${D}── ACTIVE TARGETS ($(existing_targets | grep -c .)) ──────────────────────────────────────${R}"
    local targets=() t n=0
    while IFS= read -r t; do
      [ -z "$t" ] && continue
      n=$((n+1))
      targets+=("$t")
      local stats
      stats=$(target_stats "$t")
      printf "   ${G}%2d${R}  ${B}%-12s${R} %s\n" "$n" "$t" "$stats"
    done < <(existing_targets)
    [ "$n" -eq 0 ] && echo "     ${DIM}(koi target nahi — pehle [N] se naya scan start karein)${R}"
    echo ""
    read -r -p "  ${B}Select Target [1-$n] or Action [N/D/Q]:${R} " choice

    case "$choice" in
      [nN]*) new_scan ;;
      [dD]*) diagnostics_check ;;
      [qQ]*) echo "  Happy hunting. Bye!"; exit 0 ;;
      *)
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$n" ]; then
          local picked="${targets[$((choice-1))]}"
          target_menu "$picked"
        else
          echo "  ${RED}Invalid choice.${R}"; sleep 1
        fi
        ;;
    esac
  done
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  splash
  main_menu
fi

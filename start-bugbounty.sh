#!/usr/bin/env bash
# =============================================================================
# Bug Bounty — Mission Control & Autonomous Hunting Launcher
# High-Performance Terminal Suite for Authorized HackerOne Engagements.
# Features:
# - Live multi-step HackerOne program discovery (Cash Bounty vs All filter)
# - End-to-End Autonomous Hunt pipeline (Recon → JS Miner → Triage → Pre-filled Agent)
# - Real-time target metrics, pre-flight diagnostics, and recon diff engine.
# =============================================================================
set -uo pipefail

WS="$HOME/Desktop/projects/bug-bounty"

# ---- Load HackerOne Credentials (.env.h1) ----
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

# ---- Desktop Auto-Wrap ----
if [ ! -t 1 ] && [ "${BASH_LAUNCHER_NOTTY:-0}" != "1" ]; then
  exec xfce4-terminal --title="Bug Bounty — Mission Control" \
    --geometry=120x36 --working-directory="$WS" \
    -e "bash -lc 'exec \"$0\"'"
fi

cd "$WS" || exit 1

# =============================================================================
# UI Primitives & Centered Responsive Framing
# =============================================================================
W=82   # Frame width
PAD=0
P=""

update_geom() {
  local cols=""
  if [ -n "${COLUMNS:-}" ] && [ "$COLUMNS" -gt 0 ] 2>/dev/null; then
    cols="$COLUMNS"
  elif command -v tput >/dev/null 2>&1; then
    cols="$(tput cols 2>/dev/null || true)"
  fi
  if [ -z "$cols" ] || [ "$cols" -le 0 ] 2>/dev/null; then
    cols=80
  fi

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

sep() {
  update_geom
  printf "%s${LINE}%s${R}\n" "$P" "$(printf '─%.0s' $(seq 1 "$W"))"
}

title_box() {
  update_geom
  local title="$1" subtitle="${2:-}" pad pad2 inner_w=$W
  local clean_title clean_sub
  clean_title="$(printf '%s' "$title" | sed 's/\x1b\[[0-9;]*m//g')"
  pad=$(( (inner_w - ${#clean_title}) / 2 ))
  [ "$pad" -lt 0 ] && pad=0
  local rpad=$(( inner_w - pad - ${#clean_title} ))
  [ "$rpad" -lt 0 ] && rpad=0

  printf "%s${BORDER}╭%s╮${R}\n" "$P" "$(printf '─%.0s' $(seq 1 "$inner_w"))"
  printf "%s${BORDER}│${R}%*s${B}${CYAN}%s${R}%*s${BORDER}│${R}\n" "$P" "$pad" "" "$title" "$rpad" ""
  if [ -n "$subtitle" ]; then
    clean_sub="$(printf '%s' "$subtitle" | sed 's/\x1b\[[0-9;]*m//g')"
    pad2=$(( (inner_w - ${#clean_sub}) / 2 ))
    [ "$pad2" -lt 0 ] && pad2=0
    local rpad2=$(( inner_w - pad2 - ${#clean_sub} ))
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
  w="$(tput cols 2>/dev/null || true)"
  [ -z "$w" ] || [ "$w" -le 0 ] 2>/dev/null && w="${COLUMNS:-80}"
  clean="$(printf '%s' "$txt" | sed 's/\x1b\[[0-9;]*m//g')"
  len="${#clean}"
  local ind=$(( (w - len) / 2 ))
  [ "$ind" -lt 0 ] && ind=0
  printf "%*s%s\n" "$ind" "" "$txt"
}

center_block() {
  local block="$1" color="$2" w max=0 len line lines=()
  w="$(tput cols 2>/dev/null || true)"
  [ -z "$w" ] || [ "$w" -le 0 ] 2>/dev/null && w="${COLUMNS:-80}"
  while IFS= read -r line; do
    len="${#line}"
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
  sep
  echo "${P}  ${MUTED}[0] ↩ Back to Main Menu${R}"
  echo ""
  read -r -p "${P}  Press Enter or [0] to return... " _
}

# =============================================================================
# Recon Diff Engine
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

# =============================================================================
# COMPLETE AUTONOMOUS SCAN & HUNT PIPELINE (Recon → JS → Triage → AI Agent)
# =============================================================================
run_complete_hunt() {
  local target="$1"
  clear
  title_box " 🚀 COMPLETE AUTONOMOUS SCAN & HUNT " "$target"
  echo ""
  echo "${P}  ${B}Target:${R} ${CYAN}${B}$target${R}"
  echo "${P}  ${MUTED}Starting multi-phase automated surface discovery & agent handoff...${R}"
  echo ""
  sep

  # Step 1: Recon Pipeline (Fast check / run)
  echo "${P}  ${B}${BLUE}◈ [Phase 1/4]${R} ${B}Subdomain Enumeration & Alive Probing (httpx)...${R}"
  local efile="$WS/recon/data/$target/endpoints.json"
  if [ -s "$efile" ]; then
    local n_urls
    n_urls=$(grep -c '"url":' "$efile" 2>/dev/null || echo 0)
    echo "${P}    ${GREEN}✓${R} Recon endpoints already mapped: ${B}$n_urls URLs${R}"
  else
    python3 "$WS/recon/recon_pipeline.py" --program "$target"
  fi
  echo ""

  # Step 2: Deep JS Miner & Secret Extraction
  echo "${P}  ${B}${BLUE}◈ [Phase 2/4]${R} ${B}Deep JS-Mining & Client-side Route Extraction (Katana)...${R}"
  python3 "$WS/recon/js_miner.py" --program "$target"
  echo ""

  # Step 3: Intelligence Triage & Ranking
  echo "${P}  ${B}${BLUE}◈ [Phase 3/4]${R} ${B}Intelligence Triage & Scoring (candidate_findings)...${R}"
  python3 "$WS/recon/intelligence.py" --program "$target" --top 40
  echo ""

  # Step 4: Autonomous Hunt Prompt Generation
  echo "${P}  ${B}${BLUE}◈ [Phase 4/4]${R} ${B}Generating Pre-Filled Autonomous Hunting Prompt...${R}"
  local prompt_file="$WS/$target/AUTONOMOUS_HUNT_PROMPT.md"
  python3 "$WS/recon/h1_client.py" --prompt "$target" >/dev/null 2>&1

  if [ -f "$prompt_file" ]; then
    echo "${P}    ${GREEN}✓${R} Pre-filled hunting prompt generated: ${B}${CYAN}$prompt_file${R}"
  fi
  echo ""
  sep
  echo ""

  # Step 5: Launch OpenCode or Interactive Shell
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
        exec "$OPCODE_BIN"
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
    opt "C" "🚀 COMPLETE AUTONOMOUS SCAN & HUNT" "Recon → JS Miner → Triage → Pre-filled AI Agent"
    echo ""
    echo "${P}  ${B}Individual Pipeline Modules:${R}"
    opt "1" "Interactive Shell / Session"        "Terminal hunting session"
    opt "2" "Recon Pipeline Only"               "subfinder → httpx → gau"
    opt "3" "Deep JS Miner (Katana)"            "client-side routes & secret extraction"
    opt "4" "Safe Vulnerability Scan"           "Nuclei rate-limited prober"
    opt "5" "View Candidate Report"             "Top-40 scored findings queue"
    opt "6" "Recon Diff Engine"                 "Check for newly deployed subdomains"
    opt "7" "View Scope & Notes"                "SCOPE.md & NOTES.md"
    opt "0" "↩ Back to Main Menu"               "return to mission control"
    echo ""
    sep
    local act
    read -r -p "${P}  ${B}Action for [$target]${R} [C/0-7, or B to return]: " act

    case "$act" in
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
            exec "$OPCODE_BIN"
          elif [ "$sc" = "2" ]; then
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
        sep
        read -r -p "${P}  Recon complete. Press Enter or [0] to continue..." _
        ;;
      3)
        echo ""
        echo "${P}  [1] Dry-run safe check   [2] Live JS Crawl   [0] Back"
        local jc
        read -r -p "${P}  Choice [1-2, or 0 to cancel]: " jc
        if [ "$jc" = "2" ]; then
          python3 "$WS/recon/js_miner.py" --program "$target"
        elif [ "$jc" = "1" ]; then
          python3 "$WS/recon/js_miner.py" --program "$target" --dry-run
        else
          continue
        fi
        echo ""
        sep
        read -r -p "${P}  JS Miner complete. Press Enter or [0] to continue..." _
        ;;
      4)
        echo ""
        echo "${P}  [1] Dry-run safe check   [2] Live Nuclei scan   [0] Back"
        local nc
        read -r -p "${P}  Choice [1-2, or 0 to cancel]: " nc
        if [ "$nc" = "2" ]; then
          python3 "$WS/recon/scanner.py" --program "$target"
        elif [ "$nc" = "1" ]; then
          python3 "$WS/recon/scanner.py" --program "$target" --dry-run
        else
          continue
        fi
        echo ""
        sep
        read -r -p "${P}  Scan complete. Press Enter or [0] to continue..." _
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
    opt "0" "↩ Back to Main Menu"           "return to mission control"
    echo ""
    sep
    local s_mode
    read -r -p "${P}  ${B}Select Scan Type [0-3, or B to return]:${R} " s_mode

    case "$s_mode" in
      0|[bB]*|[qQ]*)
        return
        ;;
      1|2)
        local bounty_flag=""
        local scan_title="ALL HACKERONE PROGRAMS"
        if [ "$s_mode" = "1" ]; then
          bounty_flag="--bounty-only"
          scan_title="PAID CASH BOUNTY PROGRAMS"
        fi

        if [ -z "${H1_USERNAME:-}" ] || [ -z "${H1_API_TOKEN:-}" ]; then
          echo ""
          echo "${P}  ${RED}⚠ H1_USERNAME ya H1_API_TOKEN set nahi hain.${R}"
          echo "${P}  ${MUTED}Auto-discovery ke liye credentials zaroori hain:${R}"
          echo "${P}    export H1_USERNAME=\"...\" && export H1_API_TOKEN=\"...\""
          echo ""
          read -r -p "${P}  Manual handle enter karna chahte hain? [Y/n]: " mh
          if [[ ! "$mh" =~ ^[nN]$ ]]; then
            new_scan_manual
            return
          fi
          continue
        fi

        echo ""
        echo "${P}  ${B}${CYAN}⚡ INITIATING LIVE HACKERONE DISCOVERY...${R}"
        echo ""

        # Live scanning with verbose progress steps visible to user
        local raw_json
        raw_json=$(python3 "$WS/recon/h1_client.py" --list $bounty_flag --verbose --json)

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
data = json.loads('''$raw_json''')
for p in data:
    b = '💰 Bounty' if p.get('offers_bounties') else 'ℹ VDP'
    print(f\"{p['handle']}|{p['name']}|{b}\")
")

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
  clear
  echo ""
  center_block "
  ██████╗ ██╗   ██╗ ██████╗     ██████╗  ██████╗ ██╗   ██╗███╗   ██╗████████╗██╗   ██╗
  ██╔══██╗██║   ██║██╔════╝     ██╔══██╗██╔═══██╗██║   ██║████╗  ██║╚══██╔══╝╚██╗ ██╔╝
  ██████╔╝██║   ██║██║  ███╗    ██████╔╝██║   ██║██║   ██║██╔██╗ ██║   ██║    ╚████╔╝ 
  ██╔══██╗██║   ██║██║   ██║    ██╔══██╗██║   ██║██║   ██║██║╚██╗██║   ██║     ╚██╔╝  
  ██████╔╝╚██████╔╝╚██████╔╝    ██████╔╝╚██████╔╝╚██████╔╝██║ ╚████║   ██║      ██║   
  ╚═════╝  ╚═════╝  ╚═════╝     ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝   ╚═╝      ╚═╝   
" "${CYAN}"
  echo ""
  center "${B}${CYAN}MISSION CONTROL — AUTONOMOUS BUG BOUNTY SUITE${R}"
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
  fi
}

# =============================================================================
# Main Menu
# =============================================================================
main_menu() {
  while true; do
    update_geom
    clear
    title_box " ⚡ BUG BOUNTY — MISSION CONTROL " "HackerOne Hunting & Attack Surface Suite"
    echo ""
    echo "${P}  ${B}Mission Actions:${R}"
    opt "N" "⚡ Start NEW Scan"          "discover new HackerOne targets (Cash Bounty / All)"
    opt "D" "🔍 System Diagnostics"      "tools, APIs, Docker & environment audit"
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
    read -r -p "${P}  ${B}Select Target [1-$n] or Action [N/D/Q]:${R} " choice

    case "$choice" in
      [nN]*) new_scan ;;
      [dD]*) diagnostics_check ;;
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
  splash
  main_menu
fi

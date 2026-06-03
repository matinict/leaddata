#!/usr/bin/env bash
# ============================================================
# CF2 Resource Manager
# - KILL   : all media players
# - PROTECT: IDEs (kiro, code, cursor, atom, etc.)
# - NICE+19: everything else (lowest priority, NOT killed)
# ~/cf2_resource_manager.sh.
# ============================================================

set -euo pipefail

# ── Terminal colors ──────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log_kill()    { echo -e "${RED}   💀 KILL${RESET}    $*"; }
log_protect() { echo -e "${GREEN}   🛡  PROTECT${RESET} $*"; }
log_nice()    { echo -e "${YELLOW}   🐢 NICE+19${RESET} $*"; }
log_skip()    { echo -e "${CYAN}   ⏭  SKIP${RESET}    $*"; }

echo -e "\n${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║     CF2 Resource Manager             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}\n"

# ── 1. KILL LIST — media players only ───────────────────────
KILL_PROCS=(
    vlc cvlc nvlc qvlc svlc
    mpv mplayer mplayer2 smplayer
    totem
    rhythmbox
    banshee
    clementine
    strawberry
    audacious
    deadbeef
    quodlibet
    lollypop
    gnome-music
    parole
    celluloid
    haruna
    ffplay
    xine
    kaffeine
    dragon
    kmplayer
)

echo -e "${BOLD}── Killing media players ────────────────${RESET}"
_killed=0
for name in "${KILL_PROCS[@]}"; do
    mapfile -t pids < <(pgrep -x "$name" 2>/dev/null || true)
    for pid in "${pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log_kill "$name (PID $pid)"
            kill -SIGTERM "$pid" 2>/dev/null || true
            sleep 0.3
            kill -0 "$pid" 2>/dev/null && kill -SIGKILL "$pid" 2>/dev/null || true
            _killed=$((_killed + 1))
        fi
    done
done
[[ $_killed -eq 0 ]] && echo "   (none running)"

# ── 2. PROTECT LIST — IDEs, pipeline runners ────────────────
# These processes will NOT be touched at all
PROTECT_PROCS=(
    kiro
    code
    "code-oss"
    cursor
    atom
    subl
    sublime_text
    idea
    "idea.sh"
    pycharm
    "pycharm.sh"
    webstorm
    clion
    goland
    rubymine
    rider
    eclipse
    netbeans
    zed
    lapce
    helix
    nvim
    vim
    gvim
    emacs
    gedit
    kate
    # CF2 pipeline itself
    python3
    python
    uvicorn
    crewai
    kickoff
    ffmpeg           # active renders — don't starve them
    ffprobe
)

# Build a fast lookup set from PROTECT_PROCS
declare -A PROTECT_MAP
for p in "${PROTECT_PROCS[@]}"; do
    PROTECT_MAP["$p"]=1
done

_is_protected() {
    local name="$1"
    # Exact match
    [[ -n "${PROTECT_MAP[$name]+_}" ]] && return 0
    # Prefix match: kiro, code, python*, cursor*
    for pat in kiro code cursor python ffmpeg; do
        [[ "$name" == "$pat"* ]] && return 0
    done
    return 1
}

# ── 3. SKIP LIST — kernel/system processes ──────────────────
SKIP_PROCS=(
    systemd kernel kthreadd migration kworker ksoftirqd
    watchdog cpuhp irq kdevtmpfsd kauditd scsi_eh
    jbd2 ext4 xfs btrfs
    sshd gdm lightdm sddm
    dbus-daemon
    NetworkManager
    pulseaudio pipewire wireplumber
    Xorg Xwayland
    gnome-shell mutter
    xdg-permission-store xdg-document-portal xdg-desktop-portal
)
declare -A SKIP_MAP
for p in "${SKIP_PROCS[@]}"; do SKIP_MAP["$p"]=1; done

_is_skip() {
    local name="$1"
    [[ -n "${SKIP_MAP[$name]+_}" ]] && return 0
    [[ "$name" == "["* ]] && return 0   # kernel threads like [kworker/...]
    return 1
}

# ── 4. NICE+19 everything else ───────────────────────────────
echo -e "\n${BOLD}── Setting other processes to nice +19 ──${RESET}"

_niced=0
_protected=0
_skipped=0

# Iterate all PIDs owned by current user
while IFS= read -r pid; do
    # Get process name
    name=$(cat /proc/"$pid"/comm 2>/dev/null || true)
    [[ -z "$name" ]] && continue

    if _is_skip "$name"; then
        log_skip "$name (PID $pid) — system"
        _skipped=$((_skipped + 1))
        continue
    fi

    if _is_protected "$name"; then
        log_protect "$name (PID $pid)"
        _protected=$((_protected + 1))
        continue
    fi

    # Get current nice value
    current_nice=$(ps -o ni= -p "$pid" 2>/dev/null | tr -d ' ' || echo "?")

    if renice +19 -p "$pid" > /dev/null 2>&1; then
        ionice -c 3 -p "$pid" 2>/dev/null || true
        log_nice "$name (PID $pid)  [was nice=$current_nice → 19, ionice=idle]"
        _niced=$((_niced + 1))
    fi

done < <(ps -u "$(id -u)" -o pid= 2>/dev/null)

# ── Summary ──────────────────────────────────────────────────
echo -e "\n${BOLD}── Summary ─────────────────────────────${RESET}"
echo -e "  ${RED}Killed${RESET}    : $_killed media player process(es)"
echo -e "  ${GREEN}Protected${RESET} : $_protected IDE/pipeline process(es)"
echo -e "  ${YELLOW}Niced +19${RESET} : $_niced process(es) set to lowest priority"
echo -e "  ${CYAN}Skipped${RESET}   : $_skipped system process(es)\n"
echo -e "${BOLD}✅ Done. IDEs and pipeline untouched.${RESET}\n"

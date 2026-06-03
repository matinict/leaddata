#!/usr/bin/env bash
# ── Auto version: runs silently on login, logs to ~/cf2_resource.log ──
LOG="$HOME/cf2_resource.log"
sleep 20   # wait for desktop apps to fully start
echo "[$(date '+%Y-%m-%d %H:%M:%S')] CF2 Resource Manager running…" >> "$LOG"
bash "$HOME/cf2_resource_manager.sh" >> "$LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG"

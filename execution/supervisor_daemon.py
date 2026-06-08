#!/usr/bin/env python3
"""Supervisor daemon per winbet_email_handler.py - riavvio automatico"""
import subprocess
import time
import os
import signal
import sys
from datetime import datetime

PIDFILE = "/tmp/winbet_email_supervisor.pid"
LOGFILE = "/mnt/c/Users/angel/WinBet/logs/winbet_email_supervisor_daemon.log"
SCRIPT = "/mnt/c/Users/angel/WinBet/execution/winbet_email_handler.py"
PYTHON = "/mnt/c/Users/angel/WinBet/venv/bin/python"
INTERVAL = 300

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [SUPERVISOR] {msg}\n"
    print(line, end="")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line)

def get_monitor_pid():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "winbet_email_handler.py monitor"],
            capture_output=True, text=True
        )
        pids = [p for p in result.stdout.strip().split("\n") if p]
        return int(pids[0]) if pids else None
    except Exception:
        return None

def start_monitor():
    log("Avvio winbet_email_handler.py monitor...")
    proc = subprocess.Popen(
        [PYTHON, SCRIPT, "monitor", "--interval", str(INTERVAL)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd="/mnt/c/Users/angel/WinBet",
        start_new_session=True
    )
    log(f"Monitor avviato con PID {proc.pid}")
    return proc.pid

def main():
    # Scrive PID del supervisore
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    
    log("Supervisor avviato.")
    
    # Controlla se monitor è già attivo
    pid = get_monitor_pid()
    if pid:
        log(f"Monitor già attivo con PID {pid}, supervisione iniziata.")
    else:
        start_monitor()
    
    while True:
        time.sleep(60)
        pid = get_monitor_pid()
        if pid is None:
            log("Monitor NON in esecuzione. Riavvio...")
            start_monitor()
        else:
            # Silenzioso: check ok
            pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Supervisor terminato da keyboard interrupt.")
        sys.exit(0)
    except Exception as e:
        log(f"ERRORE supervisor: {e}")
        sys.exit(1)

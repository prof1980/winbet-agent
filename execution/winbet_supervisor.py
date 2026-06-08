#!/usr/bin/env python3
"""
Supervisore del monitor email WinBet.
Verifica ogni 60 secondi che il monitor sia attivo; se non lo è, lo riavvia.
Si daemonizza automaticamente (double fork) per sopravvivere alla shell padre.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path("/mnt/c/Users/angel/WinBet")
PYTHON = PROJECT / "venv/bin/python"
SCRIPT = PROJECT / "execution/winbet_email_handler.py"
PID_FILE = PROJECT / "execution/.winbet_email_handler.pid"
LOG_FILE = PROJECT / "execution/.winbet_email_handler.log"
SUPERVISOR_LOG = PROJECT / "execution/.winbet_supervisor.log"
INTERVAL = 300

CHECK_INTERVAL = 60

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(SUPERVISOR_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def is_monitor_running():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "winbet_email_handler.py monitor"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and result.stdout.strip()
    except Exception:
        return False

def start_monitor():
    log("Riavvio monitor WinBet...")
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    with open(LOG_FILE, "a") as logf:
        proc = subprocess.Popen(
            [str(PYTHON), str(SCRIPT), "monitor", "--interval", str(INTERVAL)],
            stdout=logf,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT),
            start_new_session=True,
        )
    log(f"Monitor avviato con PID {proc.pid}")
    return proc.pid

def daemonize():
    """Double-fork per diventare un vero daemon indipendente."""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 fallito: {e}\n")
        sys.exit(1)

    os.chdir(str(PROJECT))
    os.setsid()
    os.umask(0)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 fallito: {e}\n")
        sys.exit(1)

    # Redirect stdio
    sys.stdout.flush()
    sys.stderr.flush()
    si = open("/dev/null", "r")
    so = open(SUPERVISOR_LOG, "a+")
    se = open(SUPERVISOR_LOG, "a+")
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    # Scrivi PID supervisore
    (PROJECT / "execution/.winbet_supervisor.pid").write_text(str(os.getpid()))

def main():
    log("Supervisore WinBet avviato.")
    while True:
        if not is_monitor_running():
            log("Monitor WinBet NON in esecuzione!")
            start_monitor()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--foreground":
        main()
    else:
        daemonize()
        main()

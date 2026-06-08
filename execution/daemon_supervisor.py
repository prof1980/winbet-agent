#!/usr/bin/env python3
"""
Daemon supervisor per winbet_email_handler.py monitor.
Fa doppio fork per sopravvivere alla fine della sessione.
Loop di supervisione: ogni 10s controlla se il monitor è vivo, altrimenti lo riavvia.
"""
import os
import signal
import subprocess
import sys
import time

BASEDIR = "/mnt/c/Users/angel/WinBet"
PYTHON = f"{BASEDIR}/venv/bin/python"
HANDLER = f"{BASEDIR}/execution/winbet_email_handler.py"
INTERVAL = 300
LOGFILE = f"{BASEDIR}/logs/daemon_supervisor.log"


def log(msg):
    with open(LOGFILE, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        f.flush()


def is_running():
    try:
        output = subprocess.check_output(
            ["pgrep", "-f", "winbet_email_handler.py monitor"], text=True
        ).strip()
        return bool(output)
    except subprocess.CalledProcessError:
        return False


def start_monitor():
    return subprocess.Popen(
        [PYTHON, HANDLER, "monitor", "--interval", str(INTERVAL)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def daemonize():
    # Fork 1: termina il genitore
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.setsid()  # Nuova sessione
    # Fork 2: termina il session leader per evitare zombie session
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    # Reindirizza stdio
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "r") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(LOGFILE, "a+") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def main():
    daemonize()
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    log("=" * 60)
    log("Daemon supervisor avviato")
    log("=" * 60)
    monitor = None
    while True:
        if monitor is None or monitor.poll() is not None:
            if is_running():
                log("Monitor già in esecuzione — skip avvio")
            else:
                monitor = start_monitor()
                log(f"Monitor avviato PID {monitor.pid}")
        time.sleep(10)


if __name__ == "__main__":
    main()

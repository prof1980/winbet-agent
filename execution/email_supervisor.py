#!/usr/bin/env python3
"""
WinBet Email Supervisor — Persistent background monitor.
Keeps winbet_email_handler.py running. If it exits, restarts it.
Double-fork daemon so it survives parent death.
"""
import subprocess, sys, os, time, signal, logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

BASE_DIR = Path("/mnt/c/Users/angel/WinBet")
LOG_FILE = BASE_DIR / "logs/email_supervisor.log"
MONITOR_LOG = BASE_DIR / "logs/winbet_email_monitor.log"
PID_FILE = BASE_DIR / ".tmp/email_supervisor.pid"
MONITOR_PID_FILE = BASE_DIR / "execution" / ".winbet_email_handler.pid"
PYTHON = str(BASE_DIR / "venv/bin/python")
SCRIPT = str(BASE_DIR / "execution/winbet_email_handler.py")
INTERVAL = 300
CHECK_INTERVAL = 60

def _daemonize():
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"fork #1 failed: {e}\n")
        sys.exit(1)
    os.chdir("/")
    os.setsid()
    os.umask(0)
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"fork #2 failed: {e}\n")
        sys.exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "r") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open("/dev/null", "a+") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())

def _setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log = logging.getLogger("email_supervisor")
    log.setLevel(logging.INFO)
    log.addHandler(h)
    return log

def is_monitor_running():
    """Check if the monitor process is actually running via pgrep."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "winbet_email_handler.py monitor"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False

def start_monitor(log):
    # Always clear stale PID file before starting
    try:
        MONITOR_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    env = os.environ.copy()
    cmd = [PYTHON, SCRIPT, "monitor", "--interval", str(INTERVAL)]
    log.info(f"Launching monitor: {' '.join(cmd)}")

    MONITOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(MONITOR_LOG, "a") as logf:
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    log.info(f"Monitor started, PID {proc.pid}")
    return proc

def alive(proc):
    return proc.poll() is None

def main():
    log = _setup_logging()

    # Check if monitor is already running before starting a new one
    if is_monitor_running():
        log.info("Monitor already running. Supervisor entering watch mode.")
        proc = None
    else:
        proc = start_monitor(log)

    log.info("Supervisor started. Health-check every {}s.".format(CHECK_INTERVAL))
    check_counter = 0

    while True:
        time.sleep(CHECK_INTERVAL)
        check_counter += 1

        if proc is not None and alive(proc):
            if check_counter % 10 == 0:
                log.info(f"Monitor alive (PID {proc.pid}) — {check_counter} health checks")
            else:
                log.debug(f"Monitor alive (PID {proc.pid})")
            continue

        # Monitor process object shows dead OR we never started one (found existing)
        if not is_monitor_running():
            if proc is not None:
                log.warning(f"Monitor died (exit code {proc.poll()}). Restarting...")
            else:
                log.warning("Monitor not found. Starting...")
            proc = start_monitor(log)
        else:
            if check_counter % 10 == 0:
                log.info(f"Monitor alive (detected via pgrep) — {check_counter} health checks")
            else:
                log.debug("Monitor alive (detected via pgrep)")

if __name__ == "__main__":
    _daemonize()
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    main()

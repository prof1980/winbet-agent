#!/usr/bin/env python3
import subprocess
import time
import signal
import sys
import os

LOG_FILE = "/mnt/c/Users/angel/WinBet/logs/supervisor_hermes_20260607.log"
CMD = ["/mnt/c/Users/angel/WinBet/venv/bin/python", "/mnt/c/Users/angel/WinBet/execution/winbet_email_handler.py", "monitor", "--interval", "300"]
RESTART_DELAY = 10
MONITOR_INTERVAL = 60

def log(msg):
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

def find_monitor_pid():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "winbet_email_handler.py monitor"],
            capture_output=True, text=True, timeout=5
        )
        pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        # Exclude the current process (supervisor) if it's somehow matching
        own_pid = str(os.getpid())
        pids = [p for p in pids if p != own_pid]
        return pids
    except Exception:
        return []

def is_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False

def start_monitor():
    try:
        proc = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"Monitor avviato con PID {proc.pid}")
        return proc.pid
    except Exception as e:
        log(f"Errore avvio monitor: {e}")
        return None

def kill_existing():
    pids = find_monitor_pid()
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
            log(f"Inviato SIGTERM a PID {pid}")
            time.sleep(2)
            if is_alive(pid):
                os.kill(int(pid), signal.SIGKILL)
                log(f"Inviato SIGKILL a PID {pid}")
        except Exception:
            pass

if __name__ == "__main__":
    import datetime
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log("Supervisore Hermes avviato")

    while True:
        try:
            pids = find_monitor_pid()
            active_pids = [p for p in pids if is_alive(p)]

            if len(active_pids) == 0:
                log("Monitor non attivo. Riavvio...")
                start_monitor()
            elif len(active_pids) > 1:
                log(f"Trovati {len(active_pids)} monitor attivi ({active_pids}). Kill e riavvio unico...")
                kill_existing()
                time.sleep(2)
                start_monitor()
            else:
                log(f"Monitor attivo (PID {active_pids[0]}). Tutto OK.")

            time.sleep(MONITOR_INTERVAL)
        except KeyboardInterrupt:
            log("Supervisore terminato")
            sys.exit(0)
        except Exception as e:
            log(f"Errore nel loop: {e}")
            time.sleep(MONITOR_INTERVAL)
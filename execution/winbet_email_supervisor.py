#!/usr/bin/env python3
"""
Supervisore per WinBet Email Monitor.
Garantisce che winbet_email_handler.py monitor sia sempre attivo.
"""
import subprocess
import sys
import time
import os
import signal
from pathlib import Path

PROJECT_ROOT = Path("/mnt/c/Users/angel/WinBet")
PID_FILE = PROJECT_ROOT / "execution" / ".winbet_email_handler.pid"
LOG_FILE = PROJECT_ROOT / "logs" / "winbet_email_supervisor.log"
PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"
SCRIPT = PROJECT_ROOT / "execution" / "winbet_email_handler.py"
CMD = [str(PYTHON), str(SCRIPT), "monitor", "--interval", "300"]

def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [SUPERVISOR] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")

def get_handler_pids():
    try:
        result = subprocess.run(["pgrep", "-f", "winbet_email_handler.py monitor"],
                                capture_output=True, text=True, timeout=5)
        pids = []
        for line in result.stdout.strip().splitlines():
            pid = int(line.strip())
            # Escludi il supervisore stesso se matcha (improbabile)
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmdline = f.read().decode("utf-8", errors="replace")
                if "monitor" in cmdline:
                    pids.append(pid)
            except (OSError, ValueError):
                pass
        return pids
    except Exception as e:
        log(f"Errore get_handler_pids: {e}")
        return []

def kill_all_handlers():
    for pid in get_handler_pids():
        try:
            os.kill(pid, signal.SIGTERM)
            log(f"Inviato SIGTERM a PID {pid}")
        except OSError:
            pass
    time.sleep(2)
    # SIGKILL ai sopravvissuti
    for pid in get_handler_pids():
        try:
            os.kill(pid, signal.SIGKILL)
            log(f"Inviato SIGKILL a PID {pid}")
        except OSError:
            pass

def start_handler():
    # Pulisci PID file
    PID_FILE.unlink(missing_ok=True)
    proc = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          cwd=str(PROJECT_ROOT))
    time.sleep(3)
    pids = get_handler_pids()
    log(f"Avviato handler, PIDs: {pids}")
    return pids

def main():
    # Dissocia da eventuale sessione terminale (cron/WSL)
    try:
        os.setsid()
        log("Dissociato in nuova sessione (setsid)")
    except OSError:
        pass
    log("=" * 50)
    log("Avvio supervisore WinBet Email Monitor")
    log(f"CMD: {' '.join(CMD)}")
    
    # Stato iniziale
    pids = get_handler_pids()
    log(f"Handler attivi all'avvio: {pids}")
    
    # Se ce n'è più di uno, killa tutti e avviane uno solo
    if len(pids) > 1:
        log(f"Trovati {len(pids)} handler — killo tutti e ne avvio uno")
        kill_all_handlers()
        start_handler()
    elif len(pids) == 0:
        log("Nessun handler attivo — avvio")
        start_handler()
    else:
        log(f"Handler già attivo (PID {pids[0]}) — supervisione")
    
    # Loop supervisione
    while True:
        time.sleep(60)
        pids = get_handler_pids()
        if len(pids) == 0:
            log("⚠️ Handler morto! Riavvio...")
            start_handler()
        elif len(pids) > 1:
            log(f"⚠️ Trovati {len(pids)} handler — killo tutti e ne avvio uno")
            kill_all_handlers()
            start_handler()
        else:
            # Tutto OK, log silenzioso ogni 5 min
            pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrotto da utente")
        sys.exit(0)
    except Exception as e:
        log(f"Errore fatale: {e}")
        raise

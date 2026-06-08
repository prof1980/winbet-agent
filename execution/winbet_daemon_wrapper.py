#!/usr/bin/env python3
"""
WinBet Monitor Daemon Wrapper — Disaccoppia il supervisore da Hermes
creando una nuova sessione (setsid), così il processo sopravvive alla
chiusura della sessione agent.
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "winbet_monitor_supervisor.sh"
LOG    = Path(__file__).resolve().parent / ".winbet_email_handler.log"
PID_FILE = Path(__file__).resolve().parent / ".winbet_email_handler.pid"

def main():
    if not SCRIPT.exists():
        print(f"❌ {SCRIPT} non trovato", file=sys.stderr)
        sys.exit(1)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "a")
    log.write(f"\n[{Path(__file__).name}] Avvio supervisore in nuova sessione...\n")
    log.flush()

    p = subprocess.Popen(
        ["bash", str(SCRIPT)],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )

    PID_FILE.write_text(str(p.pid))
    log.write(f"Supervisore avviato (PID {p.pid}), nuova sessione.\n")
    log.flush()
    print(f"✅ WinBet supervisor avviato in nuova sessione (PID {p.pid})")

if __name__ == "__main__":
    main()

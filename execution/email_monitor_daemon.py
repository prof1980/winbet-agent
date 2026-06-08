#!/usr/bin/env python3
"""
WinBet Email Monitor Daemon — keep-alive wrapper.
Riavvia automaticamente il monitor se il processo termina.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_DIR = Path("/mnt/c/Users/angel/WinBet")
_PYTHON = _PROJECT_DIR / "venv/bin/python"
_HANDLER = _PROJECT_DIR / "execution/winbet_email_handler.py"
_LOG = _PROJECT_DIR / "logs/winbet_email_monitor.log"
_INTERVAL = 300


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def _load_env() -> None:
    env_path = _PROJECT_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def main() -> None:
    _load_env()
    _log("Daemon avviato — keep-alive wrapper (PID: " + str(os.getpid()) + ")")

    while True:
        _log("Avvio monitor Python...")
        proc = subprocess.Popen(
            [str(_PYTHON), str(_HANDLER), "monitor", "--interval", str(_INTERVAL)],
            cwd=str(_PROJECT_DIR),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log(f"Monitor avviato (PID: {proc.pid})")
        code = proc.wait()
        _log(f"Monitor terminato con exit code {code}. Riavvio tra 10s...")
        time.sleep(10)


if __name__ == "__main__":
    main()

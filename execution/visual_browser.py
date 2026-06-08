#!/usr/bin/env python3
"""WinBet Visual Browser Agent — Navigazione visibile con intercettazione API."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path("/mnt/c/Users/angel/WinBet/.tmp")

def start_chrome_on_display(url: str, display: str = ":1"):
    """Avvia Chrome reale sul display virtuale."""
    cmd = [
        "google-chrome-stable",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--no-first-run",
        "--disable-default-apps",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--disable-features=IsolateOrigins,site-per-process",
        f"--user-data-dir={OUTPUT_DIR / 'chrome_profile'}",
        "--remote-debugging-port=9222",
        url,
    ]
    env = {"DISPLAY": display, "LANG": "it_IT.UTF-8"}
    
    print(f"🚀 Avvio Chrome su display {display}...")
    print(f"🌐 URL: {url}")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc

async def capture_network():
    """Cattura richieste di rete via Chrome DevTools Protocol."""
    import aiohttp
    
    ws_url = None
    # Ottieni il WebSocket endpoint da /json/version
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("http://localhost:9222/json/version") as resp:
                version = await resp.json()
                ws_url = version.get("webSocketDebuggerUrl")
                print(f"   DevTools WS: {ws_url}")
        except Exception as e:
            print(f"   DevTools non disponibile: {e}")
            return
    
    if not ws_url:
        return
    
    captured = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url) as ws:
            # Abilita Network domain
            await ws.send_str(json.dumps({"id": 1, "method": "Network.enable"}))
            
            print("   🕸️  Intercettazione attiva... aspetto 30 secondi")
            for _ in range(60):  # 30 secondi
                try:
                    msg = await ws.receive(timeout=0.5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("method", "").startswith("Network."):
                            params = data.get("params", {})
                            req = params.get("request", {})
                            url = req.get("url", "")
                            if any(k in url.lower() for k in ["api", "json", "event", "match", "odd", "quota", "sport", "bet"]):
                                captured.append({
                                    "type": data["method"],
                                    "url": url,
                                    "headers": req.get("headers", {}),
                                })
                                print(f"   🎯 API: {url[:100]}")
                except asyncio.TimeoutError:
                    pass
            
            # Disabilita
            await ws.send_str(json.dumps({"id": 2, "method": "Network.disable"}))
    
    with open(OUTPUT_DIR / "captured_api.json", "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2, ensure_ascii=False)
    print(f"   💾 Salvate {len(captured)} richieste API in captured_api.json")

def take_screenshot(path: str, display: str = ":1"):
    """Screenshot del desktop virtuale."""
    cmd = ["import", "-window", "root", path]
    env = {"DISPLAY": display}
    subprocess.run(cmd, env=env, check=False)
    print(f"   📸 Screenshot: {path}")

async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.snai.it"
    
    print("=" * 60)
    print(" WINBET — Visual Browser Agent")
    print("=" * 60)
    
    proc = start_chrome_on_display(url)
    print(f"   Chrome PID: {proc.pid}")
    
    # Aspetta che Chrome si avvii e carichi
    await asyncio.sleep(8)
    
    # Screenshot iniziale
    take_screenshot(str(OUTPUT_DIR / "screenshot_1_start.png"))
    
    # Cattura rete via DevTools
    await capture_network()
    
    # Screenshot dopo navigazione
    await asyncio.sleep(5)
    take_screenshot(str(OUTPUT_DIR / "screenshot_2_loaded.png"))
    
    print("\n✅ Navigazione completata. Guarda i risultati:")
    print(f"   - Screenshot: {OUTPUT_DIR / 'screenshot_*.png'}")
    print(f"   - API catturate: {OUTPUT_DIR / 'captured_api.json'}")
    print(f"\n👁️  Per vedere in diretta: apri il browser su http://localhost:18789")
    print("   Password VNC: winbet")
    
    # Non uccidiamo Chrome, lasciamo aperto
    print("\n⏳ Chrome rimane aperto. Premi Ctrl+C per chiudere.")
    await asyncio.sleep(3600)  # Rimane aperto 1 ora

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Chrome DevTools Protocol — Network Interceptor"""
import asyncio
import json
from pathlib import Path

OUTPUT = Path("/mnt/c/Users/angel/WinBet/.tmp")
WS_URL = "ws://localhost:9222/devtools/browser/f5cf246d-a981-405c-935b-9653d7df49aa"

async def main():
    import websockets
    
    captured = []
    print("🔗 Connessione a Chrome DevTools...")
    
    async with websockets.connect(WS_URL) as ws:
        # 1. Ottieni lista tab
        await ws.send(json.dumps({"id": 1, "method": "Target.getTargets"}))
        resp = json.loads(await ws.recv())
        targets = resp.get("result", {}).get("targetInfos", [])
        
        print(f"   {len(targets)} tab trovati")
        page_target = None
        for t in targets:
            print(f"      - {t.get('type')} {t.get('title', 'N/A')[:40]}")
            if t.get("type") == "page":
                page_target = t["targetId"]
        
        if not page_target:
            print("   ❌ Nessuna pagina trovata")
            return
        
        # 2. Attacca alla pagina
        await ws.send(json.dumps({
            "id": 2,
            "method": "Target.attachToTarget",
            "params": {"targetId": page_target, "flatten": True}
        }))
        resp = json.loads(await ws.recv())
        session_id = resp.get("result", {}).get("sessionId")
        print(f"   📎 Sessione: {session_id}")
        
        # 3. Abilita Network nella sessione
        await ws.send(json.dumps({
            "id": 3,
            "method": "Target.sendMessageToTarget",
            "params": {
                "message": json.dumps({"id": 1, "method": "Network.enable"}),
                "sessionId": session_id,
            }
        }))
        
        # 4. Naviga verso Serie A (proviamo URL diretto)
        target_url = "https://www.snai.it/scommesse-sportive/calcio/italia/serie-a"
        print(f"   🌐 Navigo verso: {target_url}")
        await ws.send(json.dumps({
            "id": 4,
            "method": "Target.sendMessageToTarget",
            "params": {
                "message": json.dumps({
                    "id": 2,
                    "method": "Page.navigate",
                    "params": {"url": target_url}
                }),
                "sessionId": session_id,
            }
        }))
        
        # 5. Ascolta eventi per 30 secondi
        print("   🕸️  Intercettazione rete per 30 secondi...")
        end = asyncio.get_event_loop().time() + 30
        
        while asyncio.get_event_loop().time() < end:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(msg)
                
                # Eventi Network
                if data.get("method", "").startswith("Network."):
                    params = data.get("params", {})
                    req = params.get("request", {})
                    url = req.get("url", "")
                    
                    # Filtra solo API interessanti
                    keywords = ["api", "json", "event", "match", "odd", "quota", 
                               "sport", "bet", "market", "feed", "prematch"]
                    if any(k in url.lower() for k in keywords):
                        captured.append({
                            "method": data["method"],
                            "url": url,
                            "headers": req.get("headers", {}),
                            "timestamp": asyncio.get_event_loop().time(),
                        })
                        print(f"   🎯 {data['method']}: {url[:90]}")
                
                # Log navigazione completata
                if data.get("method") == "Page.loadEventFired":
                    print("   ✅ Pagina caricata")
                    
            except asyncio.TimeoutError:
                pass
        
        # Salva
        with open(OUTPUT / "captured_api.json", "w", encoding="utf-8") as f:
            json.dump(captured, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Salvate {len(captured)} richieste API")
        print(f"   File: {OUTPUT / 'captured_api.json'}")

if __name__ == "__main__":
    asyncio.run(main())

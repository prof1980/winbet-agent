#!/usr/bin/env python3
"""WinBet Unified Scraper — Multi-bookmaker con surebet detection.

Strategie per bookmaker:
  • SNAI: API flutterseatech.it (curl_cffi)
  • Eurobet: Next.js SSR via Playwright non-headless
  • (Altri bookmaker: estendibili)

Uso:
    python3 scrape_unified.py --bookmakers snai,eurobet --store-db
    python3 scrape_unified.py --all --store-db --notify
"""

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = "/mnt/c/Users/angel/WinBet/winbet.db"
OUTPUT_DIR = Path("/mnt/c/Users/angel/WinBet/.tmp")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# SNAI config
SNAI_API = "https://betting-snai.flutterseatech.it"
SNAI_HEADERS = {
    "Referer": "https://www.snai.it/",
    "Origin": "https://www.snai.it",
    "bet-locale": "it_IT",
    "bet-brand": "391",
    "bet-offer": "0",
    "user_data": '{"accountId": null, "token": null, "tokenJWT": null, "locale": "it_IT", "loggedIn": false, "channel": 62, "brandId": 391, "offerId": 0, "clientType": "WEB"}',
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Eurobet config
EUROBET_URL = "https://www.eurobet.it/it/scommesse/calcio"


# ---------------------------------------------------------------------------
# SNAI scraper (curl_cffi - funzionante)
# ---------------------------------------------------------------------------

def scrape_snai() -> list[dict]:
    """Scrapa SNAI tramite API flutterseatech.it."""
    print("\n📊 === SNAI ===")
    url = SNAI_API + "/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0"
    
    try:
        resp = requests.get(url, headers=SNAI_HEADERS, impersonate="chrome136", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        events = []
        avvenimenti = data.get("avvenimentoFeList", [])
        scommessa_map = data.get("scommessaMap", {})
        info_map = data.get("infoAggiuntivaMap", {})
        
        # Mappa discipline
        discipline = {d["codiceDisciplina"]: d.get("descrizione", "") for d in data.get("disciplinaList", [])}
        
        for avv in avvenimenti:
            pal = str(avv["codicePalinsesto"])
            avv_code = str(avv["codiceAvvenimento"])
            disc_code = avv.get("codiceDisciplina", 0)
            
            desc = avv.get("descrizione", "")
            home, away = "", ""
            if " - " in desc:
                parts = desc.split(" - ", 1)
                home, away = parts[0].strip(), parts[1].strip()
            
            markets = []
            prefix = f"{pal}-{avv_code}-"
            for sk in [k for k in scommessa_map.keys() if k.startswith(prefix)]:
                sc = scommessa_map[sk]
                codice_sc = str(sc.get("codiceScommessa", ""))
                info_keys = [k for k in info_map.keys() if k.startswith(f"{pal}-{avv_code}-{codice_sc}-")]
                
                selections = []
                for ik in info_keys:
                    info = info_map[ik]
                    for esito in info.get("esitoList", []):
                        quota_raw = esito.get("quota", 0)
                        selections.append({
                            "name": str(esito.get("descrizione", "")),
                            "label": str(esito.get("descrizione", "")),
                            "odds": round(quota_raw / 100.0, 2) if quota_raw else 0.0,
                            "raw_odds": quota_raw,
                        })
                
                if selections:
                    markets.append({
                        "market_type": normalize_market(sc.get("descrizione", "")),
                        "market_name": sc.get("descrizione", ""),
                        "selections": selections,
                    })
            
            if markets:
                events.append({
                    "source": "snai",
                    "event_id": f"snai-{pal}-{avv_code}",
                    "home_team": home,
                    "away_team": away,
                    "discipline": discipline.get(disc_code, ""),
                    "discipline_code": disc_code,
                    "start_time": avv.get("data", ""),
                    "is_live": avv.get("live", False),
                    "markets": markets,
                })
        
        print(f"   ✅ {len(events)} eventi estratti")
        return events
    
    except Exception as e:
        print(f"   ❌ Errore SNAI: {e}")
        return []


# ---------------------------------------------------------------------------
# Eurobet scraper (Playwright non-headless)
# ---------------------------------------------------------------------------

async def scrape_eurobet() -> list[dict]:
    """Scrapa Eurobet tramite Playwright non-headless + Next.js SSR."""
    print("\n📊 === EUROBET ===")
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("   ❌ Playwright non installato. Skippato.")
        return []
    
    events = []
    
    async with async_playwright() as p:
        # Determina se usare headless (se DISPLAY non è disponibile)
        display = os.environ.get("DISPLAY", "")
        headless = not bool(display)
        if headless:
            print("   ⚠️  DISPLAY non trovato, uso headless (potrebbe fallire)")
        
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page(
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        
        try:
            await page.goto(EUROBET_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)  # Attendi render
            
            # Estrai __NEXT_DATA__
            html = await page.content()
            match = re.search(r'window\.__NEXT_DATA__\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
            
            if match:
                data = json.loads(match.group(1))
                events = parse_eurobet_data(data)
                print(f"   ✅ {len(events)} eventi da __NEXT_DATA__")
            else:
                print("   ⚠️  Nessun __NEXT_DATA__ trovato")
            
            # Screenshot per debug
            await page.screenshot(path=str(OUTPUT_DIR / "eurobet_last.png"))
        
        except Exception as e:
            print(f"   ❌ Errore Playwright: {e}")
        finally:
            await browser.close()
    
    return events


def parse_eurobet_data(data: dict) -> list[dict]:
    """Parsa Next.js data di Eurobet."""
    events = []
    page_props = data.get("props", {}).get("pageProps", {})
    
    def walk(obj, depth=0):
        if depth > 12:
            return
        if isinstance(obj, dict):
            home = obj.get("home") or obj.get("homeTeam") or obj.get("team1")
            away = obj.get("away") or obj.get("awayTeam") or obj.get("team2")
            if home and away and ("odds" in str(obj).lower() or "quota" in str(obj).lower()):
                ev = parse_eurobet_event(obj)
                if ev:
                    events.append(ev)
                return
            for key in ["events", "matches", "data", "items", "fixtures", "results"]:
                if key in obj and isinstance(obj[key], list):
                    for item in obj[key]:
                        if isinstance(item, dict):
                            ev = parse_eurobet_event(item)
                            if ev:
                                events.append(ev)
                            else:
                                walk(item, depth+1)
                    return
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v, depth+1)
        elif isinstance(obj, list):
            for item in obj[:50]:
                if isinstance(item, dict):
                    ev = parse_eurobet_event(item)
                    if ev:
                        events.append(ev)
                    else:
                        walk(item, depth+1)
    
    walk(page_props)
    return events


def parse_eurobet_event(item: dict) -> dict | None:
    """Parsa singolo evento Eurobet."""
    home = item.get("home") or item.get("homeTeam") or item.get("team1")
    away = item.get("away") or item.get("awayTeam") or item.get("team2")
    if not home or not away:
        return None
    
    event_id = item.get("id", f"eurobet-{str(home).lower()}-{str(away).lower()}")
    markets = []
    
    # 1X2 diretto
    odds_1 = item.get("odds1") or item.get("quota1")
    odds_x = item.get("oddsX") or item.get("quotaX")
    odds_2 = item.get("odds2") or item.get("quota2")
    if odds_1 and odds_x and odds_2:
        sels = []
        for name, val, label in [("1", odds_1, str(home)), ("X", odds_x, "Pareggio"), ("2", odds_2, str(away))]:
            try:
                o = float(val)
                if o > 1.0:
                    sels.append({"name": name, "label": label, "odds": round(o, 2)})
            except:
                pass
        if sels:
            markets.append({"market_type": "1x2", "market_name": "1X2", "selections": sels})
    
    # Mercati nested
    for mk_key in ["markets", "odds", "scommesse", "bets"]:
        mkts = item.get(mk_key)
        if isinstance(mkts, list):
            for m in mkts:
                if not isinstance(m, dict):
                    continue
                sels = []
                outcomes = m.get("outcomes", m.get("selections", m.get("esiti", [])))
                for o in (outcomes if isinstance(outcomes, list) else []):
                    if isinstance(o, dict):
                        quota = o.get("odds", o.get("quota", o.get("price", 0)))
                        try:
                            odds = float(quota)
                            if odds > 1.0:
                                sels.append({
                                    "name": str(o.get("name", o.get("label", ""))),
                                    "label": str(o.get("label", o.get("name", ""))),
                                    "odds": round(odds, 2),
                                })
                        except:
                            pass
                if sels:
                    markets.append({
                        "market_type": normalize_market(str(m.get("name", m.get("type", "")))),
                        "market_name": str(m.get("name", "")),
                        "selections": sels,
                    })
            break
    
    if not markets:
        return None
    
    return {
        "source": "eurobet",
        "event_id": event_id,
        "home_team": str(home),
        "away_team": str(away),
        "discipline": "Calcio",
        "discipline_code": 1,
        "start_time": item.get("startTime", item.get("date", "")),
        "is_live": item.get("live", False),
        "markets": markets,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_market(desc: str) -> str:
    d = desc.upper()
    if "1X2" in d or "ESITO FINALE" in d:
        return "1x2"
    if "GOAL" in d and "NOGOAL" in d:
        return "gol_nogol"
    if "DOPPIA CHANCE" in d:
        return "doppia_chance"
    if "UNDER" in d and "OVER" in d:
        return "over_under"
    if "PARI" in d and "DISPARI" in d:
        return "pari_dispari"
    if "HANDICAP" in d:
        return "handicap"
    if "RISULTATO ESATTO" in d:
        return "risultato_esatto"
    if "MARCATORE" in d:
        return "marcatore"
    if "CORNER" in d:
        return "corner"
    return "other"


# ---------------------------------------------------------------------------
# Surebet detection
# ---------------------------------------------------------------------------

def detect_surebets(all_events: list[dict]) -> list[dict]:
    """Trova surebet confrontando quote tra bookmaker."""
    surebets = []
    
    # Raggruppa per partita normalizzata
    matches = {}
    for ev in all_events:
        key = f"{ev['home_team'].lower()}|{ev['away_team'].lower()}"
        if key not in matches:
            matches[key] = []
        matches[key].append(ev)
    
    for match_key, ev_list in matches.items():
        if len(ev_list) < 2:
            continue
        
        # Confronta 1X2
        best = {"1": None, "X": None, "2": None}
        sources = {"1": [], "X": [], "2": []}
        
        for ev in ev_list:
            for mkt in ev.get("markets", []):
                if mkt["market_type"] == "1x2":
                    for sel in mkt["selections"]:
                        name = sel["name"]
                        odds = sel["odds"]
                        src = ev["source"]
                        if name in best:
                            sources[name].append({"bookmaker": src, "odds": odds})
                            if not best[name] or odds > best[name]["odds"]:
                                best[name] = {"odds": odds, "bookmaker": src}
        
        if all(best[k] for k in best):
            margin = sum(1.0 / best[k]["odds"] for k in best)
            if margin < 1.0:
                profit = round((1.0 - margin) * 100, 2)
                surebets.append({
                    "match": match_key.replace("|", " vs ").title(),
                    "margin": round(margin, 4),
                    "profit_percent": profit,
                    "best_combination": best,
                    "all_sources": sources,
                })
    
    return surebets


# ---------------------------------------------------------------------------
# Database store
# ---------------------------------------------------------------------------

def store_events(events: list[dict], db_path: str = DB_PATH) -> tuple[int, int]:
    """Salva eventi nel database WinBet."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    events_count = 0
    odds_count = 0
    
    for ev in events:
        match_id = ev["event_id"]
        home = ev["home_team"]
        away = ev["away_team"]
        
        # Parse data
        match_date, match_time = "", ""
        start = ev.get("start_time", "")
        if start and "T" in start:
            parts = start.split("T")
            match_date = parts[0]
            match_time = parts[1][:5] if len(parts[1]) >= 5 else parts[1]
        
        c.execute("""
            INSERT INTO matches (match_id, league_id, home_team, away_team, match_date, match_time, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                match_date=excluded.match_date,
                match_time=excluded.match_time,
                updated_at=excluded.updated_at
        """, (match_id, ev.get("competition", ""), home, away, match_date, match_time, "scheduled", now))
        events_count += 1
        
        for mkt in ev.get("markets", []):
            for sel in mkt["selections"]:
                c.execute("""
                    INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (match_id, ev["source"], mkt["market_type"], sel["name"], sel["odds"], now))
                
                c.execute("""
                    INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO UPDATE SET
                        odds_value=excluded.odds_value,
                        odds_decimal=excluded.odds_decimal,
                        scraped_at=excluded.scraped_at,
                        updated_at=excluded.updated_at
                """, (match_id, ev["source"], mkt["market_type"], sel["name"], sel.get("label", ""), sel["odds"], sel["odds"], now, now))
                odds_count += 1
    
    conn.commit()
    conn.close()
    return events_count, odds_count


def store_surebets(surebets: list[dict], db_path: str = DB_PATH):
    """Salva surebets rilevate nel database."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    for sb in surebets:
        # Cerca match_id
        match_name = sb["match"]
        c.execute("SELECT match_id FROM matches WHERE home_team || ' vs ' || away_team = ?", (match_name,))
        row = c.fetchone()
        match_id = row[0] if row else ""
        
        selections_json = json.dumps(sb.get("best_combination", {}), ensure_ascii=False)
        
        c.execute("""
            INSERT INTO surebets (match_id, market_type, selections, profit_percent, total_implied_prob, detected_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO UPDATE SET
                selections=excluded.selections,
                profit_percent=excluded.profit_percent,
                total_implied_prob=excluded.total_implied_prob,
                detected_at=excluded.detected_at,
                status='active'
        """, (match_id, "1x2", selections_json, sb["profit_percent"], sb["margin"], now, "active"))
    
    conn.commit()
    conn.close()
    print(f"   💾 {len(surebets)} surebet salvate nel DB")


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

def send_notification(message: str):
    """Invia notifica via hermes send se disponibile."""
    try:
        import subprocess
        result = subprocess.run(
            ["hermes", "send", message],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"   📨 Notifica inviata")
        else:
            print(f"   ⚠️  hermes send fallito: {result.stderr[:100]}")
    except Exception as e:
        print(f"   ℹ️  Notifica non inviata (hermes non disponibile): {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="WinBet Unified Scraper")
    parser.add_argument("--bookmakers", default="snai,eurobet", help="Bookmaker da scrapare, separati da virgola")
    parser.add_argument("--output", "-o", default="/tmp/winbet_unified.json", help="File JSON di output")
    parser.add_argument("--store-db", action="store_true", help="Salva nel database SQLite")
    parser.add_argument("--notify", action="store_true", help="Invia notifica surebet")
    parser.add_argument("--all", action="store_true", help="Scarica tutti i bookmaker configurati")
    
    args = parser.parse_args()
    
    print("═" * 65)
    print("  WinBet Unified Scraper — Multi-bookmaker + Surebet Detection")
    print("═" * 65)
    
    bookmakers = [b.strip().lower() for b in args.bookmakers.split(",")]
    if args.all:
        bookmakers = ["snai", "eurobet"]
    
    all_events = []
    
    # Scrapa ogni bookmaker
    for bm in bookmakers:
        if bm == "snai":
            events = scrape_snai()
        elif bm == "eurobet":
            events = await scrape_eurobet()
        else:
            print(f"\n⚠️ Bookmaker '{bm}' non supportato")
            continue
        
        all_events.extend(events)
    
    # Surebet detection
    print("\n🔍 === SUREBET DETECTION ===")
    surebets = detect_surebets(all_events)
    if surebets:
        print(f"   🚨 {len(surebets)} SUREBET TROVATE!")
        for sb in surebets[:5]:
            print(f"   💰 {sb['match']}: profitto {sb['profit_percent']}%")
            for sel, data in sb["best_combination"].items():
                print(f"      {sel}: {data['odds']} @ {data['bookmaker']}")
    else:
        print("   ℹ️ Nessuna surebet rilevata")
    
    # Output JSON
    result = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "bookmakers": bookmakers,
        "total_events": len(all_events),
        "events": all_events,
        "surebets": surebets,
    }
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    # Store DB
    if args.store_db:
        print("\n💾 === DATABASE ===")
        ev_count, od_count = store_events(all_events)
        print(f"   {ev_count} partite, {od_count} quote salvate")
        if surebets:
            store_surebets(surebets)
    
    # Notify
    if args.notify and surebets:
        msg = f"🚨 WinBet: {len(surebets)} surebet rilevate!\n"
        for sb in surebets[:3]:
            msg += f"• {sb['match']}: +{sb['profit_percent']}%\n"
        send_notification(msg)
    
    print(f"\n📊 Totale: {len(all_events)} eventi da {len(bookmakers)} bookmaker(s)")
    print(f"💾 Output: {args.output}")
    print("✅ Completato")


if __name__ == "__main__":
    asyncio.run(main())

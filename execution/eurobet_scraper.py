#!/usr/bin/env python3
"""WinBet Eurobet Scraper — Estrazione quote da API eurobet.it

Usa curl_cffi con TLS impersonation per bypassare i blocchi.
Strategia: API discovery + JSON parsing.

Uso:
    python3 eurobet_scraper.py --output /tmp/eurobet.json
    python3 eurobet_scraper.py --output /tmp/eurobet.json --store-db
"""

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

API_BASE = "https://www.eurobet.it"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

DB_PATH = "/mnt/c/Users/angel/WinBet/winbet.db"


def fetch_page(url: str) -> str:
    """Scarica pagina HTML con TLS impersonation."""
    resp = requests.get(url, headers=HEADERS, impersonate="chrome136", timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_next_data(html: str) -> dict | None:
    """Estrae il JSON __NEXT_DATA__ dalla pagina Next.js."""
    match = re.search(r'window\.__NEXT_DATA__\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def parse_eurobet_events(data: dict) -> list[dict]:
    """Parsa i dati Eurobet Next.js in eventi normalizzati."""
    events = []
    
    # Struttura tipica: props.pageProps.data o simili
    page_props = data.get("props", {}).get("pageProps", {})
    
    # Cerca eventi in diverse strutture possibili
    def search_events(obj, depth=0):
        if depth > 12:
            return
        if isinstance(obj, dict):
            # Cerca chiavi tipiche evento
            if all(k in obj for k in ["home", "away", "odds"]) or \
               all(k in obj for k in ["homeTeam", "awayTeam", "markets"]):
                ev = parse_single_event(obj)
                if ev:
                    events.append(ev)
                return
            # Cerca liste di eventi
            for key in ["events", "matches", "partite", "data", "items", "results", "fixtures", "meetings", "avvenimenti"]:
                if key in obj and isinstance(obj[key], list):
                    for item in obj[key]:
                        if isinstance(item, dict):
                            ev = parse_single_event(item)
                            if ev:
                                events.append(ev)
                            else:
                                search_events(item, depth + 1)
                    return
            # Ricorsione
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    search_events(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:50]:  # limita per performance
                if isinstance(item, dict):
                    ev = parse_single_event(item)
                    if ev:
                        events.append(ev)
                    else:
                        search_events(item, depth + 1)
    
    search_events(page_props)
    return events


def parse_single_event(item: dict) -> dict | None:
    """Prova a parsare un singolo evento dal dizionario."""
    # Cerca nomi squadre
    home = item.get("home") or item.get("homeTeam") or item.get("team1") or item.get("squadraCasa")
    away = item.get("away") or item.get("awayTeam") or item.get("team2") or item.get("squadraTrasferta")
    
    if not home or not away:
        return None
    
    # Genera ID
    event_id = item.get("id", "")
    if not event_id:
        event_id = f"eurobet-{home.lower().replace(' ', '')}-{away.lower().replace(' ', '')}"
    
    # Estrai mercati
    markets = []
    
    # 1X2 diretto
    odds_1 = item.get("odds1") or item.get("quota1") or item.get("odd1")
    odds_x = item.get("oddsX") or item.get("quotaX") or item.get("oddX")
    odds_2 = item.get("odds2") or item.get("quota2") or item.get("odd2")
    
    if odds_1 and odds_x and odds_2:
        selections = []
        for name, val, label in [("1", odds_1, str(home)), ("X", odds_x, "Pareggio"), ("2", odds_2, str(away))]:
            try:
                odds = float(val)
                if odds > 1.0:
                    selections.append({"name": name, "label": label, "odds": round(odds, 2), "raw_odds": int(odds * 100)})
            except (ValueError, TypeError):
                pass
        if selections:
            markets.append({
                "market_type": "1x2",
                "market_name": "1X2 Esito Finale",
                "market_code": "1",
                "selections": selections,
            })
    
    # Mercati nested
    for mk_key in ["markets", "odds", "mercati", "bets", "scommesse"]:
        mkts = item.get(mk_key)
        if isinstance(mkts, list):
            for m in mkts:
                if not isinstance(m, dict):
                    continue
                mtype = str(m.get("type", m.get("marketType", "")))
                mname = str(m.get("name", m.get("marketName", mtype)))
                sels = []
                outcomes = m.get("outcomes", m.get("selections", m.get("esiti", [])))
                if isinstance(outcomes, list):
                    for o in outcomes:
                        if isinstance(o, dict):
                            quota = o.get("odds", o.get("quota", o.get("price", 0)))
                            try:
                                odds = float(quota)
                                if odds > 1.0:
                                    sels.append({
                                        "name": str(o.get("name", o.get("label", ""))),
                                        "label": str(o.get("label", o.get("name", ""))),
                                        "odds": round(odds, 2),
                                        "raw_odds": int(odds * 100),
                                    })
                            except (ValueError, TypeError):
                                pass
                if sels:
                    markets.append({
                        "market_type": normalize_market_type(mname),
                        "market_name": mname,
                        "market_code": "",
                        "selections": sels,
                    })
            break
    
    if not markets:
        return None
    
    return {
        "source": "eurobet",
        "event_id": event_id,
        "match_code": event_id,
        "home_team": str(home),
        "away_team": str(away),
        "competition": item.get("competition", item.get("league", item.get("competizione", ""))),
        "discipline": "Calcio",
        "discipline_code": 1,
        "start_time": item.get("startTime", item.get("date", "")),
        "is_live": item.get("live", False),
        "markets": markets,
    }


def normalize_market_type(desc: str) -> str:
    """Normalizza il tipo di mercato."""
    desc_upper = desc.upper()
    if "1X2" in desc_upper or "ESITO FINALE" in desc_upper:
        return "1x2"
    if "GOAL/NOGOAL" in desc_upper or "GOL/NOGOL" in desc_upper:
        return "gol_nogol"
    if "DOPPIA CHANCE" in desc_upper:
        return "doppia_chance"
    if "UNDER/OVER" in desc_upper or "OVER/UNDER" in desc_upper:
        return "over_under"
    if "PARI/DISPARI" in desc_upper:
        return "pari_dispari"
    if "HANDICAP" in desc_upper:
        return "handicap"
    if "RISULTATO ESATTO" in desc_upper:
        return "risultato_esatto"
    if "MARCATORE" in desc_upper:
        return "marcatore"
    if "CORNER" in desc_upper:
        return "corner"
    return "other"


def scrape_eurobet(sport: str = "calcio", competition: str | None = None) -> list[dict]:
    """Scrape Eurobet per uno sport/competizione."""
    
    # URL per calcio generico
    url = f"{API_BASE}/it/scommesse/{sport}"
    if competition:
        url = f"{API_BASE}/it/scommesse/{sport}/{competition}"
    
    print(f"📡 GET {url}")
    html = fetch_page(url)
    print(f"   ✅ HTML ricevuto: {len(html):,} bytes")
    
    # Estrai Next.js data
    data = extract_next_data(html)
    if not data:
        print("   ⚠️  Nessun __NEXT_DATA__ trovato")
        # Fallback: cerca dati JSON inline
        scripts = re.findall(r'\u003cscript[^\u003e]*\u003e([\s\S]*?)\u003c/script\u003e', html)
        for s in scripts:
            if len(s) > 5000 and ("odds" in s.lower() or "quota" in s.lower() or "event" in s.lower()):
                # Prova a trovare oggetti evento
                events = re.findall(r'\{[^}]*"home[^}]*\}', s)
                print(f"   Fallback: trovati {len(events)} oggetti evento in script")
                break
        return []
    
    print(f"   ✅ __NEXT_DATA__ estratto")
    
    # Parsa eventi
    events = parse_eurobet_events(data)
    print(f"   ✅ {len(events)} eventi parsati")
    
    return events


def store_in_db(events: list[dict], db_path: str = DB_PATH):
    """Salva eventi e quote nel database WinBet."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    inserted_events = 0
    inserted_odds = 0
    
    for ev in events:
        match_id = ev["event_id"]
        league_id = ev.get("competition", "")
        home_team = ev["home_team"]
        away_team = ev["away_team"]
        match_date = ""
        match_time = ""
        start = ev.get("start_time", "")
        if start and "T" in start:
            parts = start.split("T")
            match_date = parts[0]
            match_time = parts[1][:5] if len(parts[1]) >= 5 else parts[1]
        
        c.execute("""
            INSERT INTO matches (match_id, league_id, home_team, away_team, match_date, match_time, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                league_id=excluded.league_id,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                match_date=excluded.match_date,
                match_time=excluded.match_time,
                updated_at=excluded.updated_at
        """, (match_id, league_id, home_team, away_team, match_date, match_time, "scheduled", now))
        inserted_events += 1
        
        for mkt in ev.get("markets", []):
            for sel in mkt["selections"]:
                c.execute("""
                    INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (match_id, "eurobet", mkt["market_type"], sel["name"], sel["odds"], now))
                
                c.execute("""
                    INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO UPDATE SET
                        odds_value=excluded.odds_value,
                        odds_decimal=excluded.odds_decimal,
                        scraped_at=excluded.scraped_at,
                        updated_at=excluded.updated_at
                """, (match_id, "eurobet", mkt["market_type"], sel["name"], sel["label"], sel["odds"], sel["odds"], now, now))
                inserted_odds += 1
    
    c.execute("""
        INSERT INTO scrape_log (bookmaker_id, league_id, matches_found, odds_found, started_at, completed_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("eurobet", "ALL", inserted_events, inserted_odds, now, now, "success"))
    
    conn.commit()
    conn.close()
    print(f"\n💾 Database: {inserted_events} partite, {inserted_odds} quote salvate")
    return inserted_events, inserted_odds


def main():
    parser = argparse.ArgumentParser(description="WinBet Eurobet Scraper")
    parser.add_argument("--output", "-o", default="/tmp/eurobet_scraped.json", help="File JSON di output")
    parser.add_argument("--store-db", action="store_true", help="Salva nel database SQLite")
    parser.add_argument("--sport", default="calcio", help="Sport (default: calcio)")
    parser.add_argument("--competition", default=None, help="Competizione (es. italia-serie-a)")
    
    args = parser.parse_args()
    
    print("═" * 60)
    print("  WinBet Eurobet Scraper")
    print("═" * 60)
    
    events = scrape_eurobet(args.sport, args.competition)
    
    result = {
        "bookmaker": "eurobet",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(events),
        "events": events,
    }
    
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Risultato: {len(events)} eventi")
    for ev in events[:5]:
        mkt_1x2 = None
        for m in ev["markets"]:
            if m["market_type"] == "1x2":
                mkt_1x2 = m
                break
        if mkt_1x2:
            q = " | ".join([f"{s['name']}={s['odds']}" for s in mkt_1x2["selections"]])
            print(f"   • {ev['home_team']} vs {ev['away_team']}: {q}")
    
    if args.store_db and events:
        store_in_db(events)
    
    print(f"\n💾 Output: {args.output}")
    print("✅ Completato")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""WinBet Scraper — Raccolta quote ogni ora.

In DEMO mode: simula variazioni di quote nel database esistente.
In LIVE mode: usa the-odds-api.com (richiede API key).
"""

import sqlite3
import json
import random
from datetime import datetime
from pathlib import Path

DB_PATH = "/mnt/c/Users/angel/WinBet/winbet.db"
CONFIG_PATH = "/mnt/c/Users/angel/WinBet/winbet_config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def demo_scrape():
    """Simula variazioni realistiche delle quote esistenti."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Ottieni tutte le quote attuali
    c.execute("SELECT id, match_id, bookmaker_id, market_type, selection_name, odds_value FROM odds")
    rows = c.fetchall()
    
    updated = 0
    for row in rows:
        # Variazione casuale: -5% a +5%
        change = random.uniform(0.95, 1.05)
        new_odds = round(row["odds_value"] * change, 2)
        new_odds = max(1.01, min(20.0, new_odds))  # clamp
        
        # Salva in history
        c.execute("""
            INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (row["match_id"], row["bookmaker_id"], row["market_type"], row["selection_name"], row["odds_value"], datetime.now().isoformat()))
        
        # Aggiorna odds attuale
        c.execute("""
            UPDATE odds SET odds_value=?, odds_decimal=?, updated_at=?
            WHERE id=?
        """, (new_odds, new_odds, datetime.now().isoformat(), row["id"]))
        updated += 1
    
    # Log scrape
    c.execute("""
        INSERT INTO scrape_log (bookmaker_id, league_id, matches_found, odds_found, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("DEMO", "ALL", len(set(r["match_id"] for r in rows)), updated, datetime.now().isoformat(), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    return updated

def live_scrape_theoddsapi(cfg):
    """Usa the-odds-api.com per dati reali."""
    import requests
    
    api_key = cfg.get("api_key_theoddsapi", "")
    if not api_key:
        print("❌ API key mancante per the-odds-api.com")
        return 0
    
    regions = ",".join(cfg["scrape"]["theoddsapi_regions"])
    markets = ",".join(cfg["scrape"]["markets"])
    
    updated = 0
    for league in cfg["leagues"]:
        if not league["enabled"]:
            continue
        
        # Mappa league_id a sport key the-odds-api
        sport_key = {
            "serie-a": "soccer_italy_serie_a",
            "serie-b": "soccer_italy_serie_b",
            "premier-league": "soccer_epl",
            "la-liga": "soccer_spain_la_liga",
            "bundesliga": "soccer_germany_bundesliga",
            "ligue-1": "soccer_france_ligue_one",
            "champions-league": "soccer_uefa_champs_league",
            "europa-league": "soccer_uefa_europa_league",
        }.get(league["id"], "soccer")
        
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        
        try:
            r = requests.get(url, params=params, timeout=30)
            data = r.json()
            
            if r.status_code != 200:
                print(f"⚠️  {league['id']}: API error {r.status_code}")
                continue
            
            # Inserisci/aggiorna nel DB
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            for event in data:
                match_id = f"{league['id']}_{event['id']}"
                home = event["home_team"]
                away = event["away_team"]
                start = event["commence_time"]
                
                # Inserisci partita
                c.execute("""
                    INSERT OR IGNORE INTO matches (match_id, league_id, home_team, away_team, match_date, match_time, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'scheduled')
                """, (match_id, league["id"], home, away, start[:10], start[11:16]))
                
                # Inserisci quote per ogni bookmaker
                for bm in event.get("bookmakers", []):
                    bm_key = bm["key"].lower().replace(" ", "").replace("_", "")
                    for mkt in bm.get("markets", []):
                        mkt_key = mkt["key"]
                        for outcome in mkt.get("outcomes", []):
                            c.execute("""
                                INSERT OR REPLACE INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (match_id, bm_key, mkt_key, outcome["name"], outcome.get("label", outcome["name"]), outcome["price"], outcome["price"], datetime.now().isoformat()))
                            updated += 1
            
            conn.commit()
            conn.close()
            print(f"✅ {league['id']}: {len(data)} eventi")
            
        except Exception as e:
            print(f"❌ {league['id']}: {e}")
    
    return updated

def main():
    cfg = load_config()
    
    if cfg["mode"] == "DEMO":
        print("🎲 DEMO MODE: simulazione variazioni quote...")
        updated = demo_scrape()
    else:
        print("🌐 LIVE MODE: scraping da the-odds-api.com...")
        updated = live_scrape_theoddsapi(cfg)
    
    print(f"✅ Scraping completato. Quote aggiornate: {updated}")
    
    # Dopo lo scraping, rileva surebet
    import subprocess
    result = subprocess.run(["python3", str(Path(__file__).parent / "surebet_detector.py")], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

if __name__ == "__main__":
    main()

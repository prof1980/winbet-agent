#!/usr/bin/env python3
"""WinBet SNAI Scraper — Estrazione quote da API flutterseatech.it

Endpoint documentato: /api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match
Formato quote: centesimi (108 = 1.08)

Uso:
    python3 snai_scraper.py --output /tmp/snai.json
    python3 snai_scraper.py --output /tmp/snai.json --store-db
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from curl_cffi import requests

# ---------------------------------------------------------------------------
# Configurazione API SNAI
# ---------------------------------------------------------------------------

API_BASE = "https://betting-snai.flutterseatech.it"
ENDPOINT_TOP_MATCH = "/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0"
ENDPOINT_HOT_BETS = "/api/lettura-palinsesto-sport/palinsesto/prematch/hot-bets?offerId=0"
ENDPOINT_MONOQUOTA = "/api/lettura-palinsesto-sport/monoquota?offerId=0"

HEADERS = {
    "Referer": "https://www.snai.it/",
    "Origin": "https://www.snai.it",
    "bet-locale": "it_IT",
    "bet-brand": "391",
    "bet-offer": "0",
    "user_data": '{"accountId": null, "token": null, "tokenJWT": null, "locale": "it_IT", "loggedIn": false, "channel": 62, "brandId": 391, "offerId": 0, "clientType": "WEB"}',
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

DB_PATH = "/mnt/c/Users/angel/WinBet/winbet.db"

# ---------------------------------------------------------------------------
# Fetch API
# ---------------------------------------------------------------------------

def fetch_top_match() -> dict:
    """Scarica dati prematch da SNAI API."""
    url = API_BASE + ENDPOINT_TOP_MATCH
    print(f"📡 GET {url}")
    
    resp = requests.get(url, headers=HEADERS, impersonate="chrome136", timeout=20)
    resp.raise_for_status()
    
    data = resp.json()
    print(f"   ✅ JSON ricevuto: {len(resp.content):,} bytes")
    return data


def fetch_all_endpoints() -> dict:
    """Scarica da top-match + hot-bets + monoquota e unifica."""
    results = {}
    
    for name, path in [
        ("top_match", ENDPOINT_TOP_MATCH),
        ("hot_bets", ENDPOINT_HOT_BETS),
        ("monoquota", ENDPOINT_MONOQUOTA),
    ]:
        url = API_BASE + path
        print(f"\n📡 GET {name}: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, impersonate="chrome136", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                results[name] = data
                # Conta eventi
                events = data.get("avvenimentoFeList", [])
                print(f"   ✅ {len(events)} eventi")
            else:
                print(f"   ⚠️  HTTP {resp.status_code}")
        except Exception as e:
            print(f"   ❌ Errore: {e}")
    
    return results

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_snai_data(data: dict) -> list[dict]:
    """Parsa la risposta SNAI in eventi normalizzati."""
    events = []
    
    avvenimenti = data.get("avvenimentoFeList", [])
    scommessa_map = data.get("scommessaMap", {})
    info_map = data.get("infoAggiuntivaMap", {})
    
    # Mappa disciplina ID -> nome
    discipline = {}
    for d in data.get("disciplinaList", []):
        discipline[d["codiceDisciplina"]] = d.get("descrizione", "Sconosciuta")
    
    for avv in avvenimenti:
        pal = str(avv["codicePalinsesto"])
        avv_code = str(avv["codiceAvvenimento"])
        disc_code = avv.get("codiceDisciplina", 0)
        
        event = {
            "source": "snai",
            "event_id": f"snai-{pal}-{avv_code}",
            "match_code": f"{pal}-{avv_code}",
            "home_team": "",
            "away_team": "",
            "competition": "",
            "competition_code": avv.get("codiceManifestazione"),
            "discipline": discipline.get(disc_code, "Sconosciuta"),
            "discipline_code": disc_code,
            "start_time": avv.get("data", ""),
            "is_live": avv.get("live", False),
            "markets": [],
        }
        
        # Nomi squadre dalla descrizione (formato "Casa - Trasferta")
        desc = avv.get("descrizione", "")
        if " - " in desc:
            parts = desc.split(" - ", 1)
            event["home_team"] = parts[0].strip()
            event["away_team"] = parts[1].strip()
        else:
            event["home_team"] = desc
        
        # Estrai TUTTI i mercati per questo avvenimento
        markets = extract_markets_for_event(pal, avv_code, scommessa_map, info_map)
        event["markets"] = markets
        
        events.append(event)
    
    return events


def extract_markets_for_event(pal: str, avv: str, scommessa_map: dict, info_map: dict) -> list[dict]:
    """Estrae tutti i mercati/quote per un singolo avvenimento."""
    markets = []
    
    # Cerca tutte le scommesse che appartengono a questo avvenimento
    # Key formato: palinsesto-avvenimento-codiceScommessa
    prefix = f"{pal}-{avv}-"
    matching_keys = [k for k in scommessa_map.keys() if k.startswith(prefix)]
    
    for sk in matching_keys:
        sc = scommessa_map[sk]
        codice_scommessa = str(sc.get("codiceScommessa", ""))
        
        # Cerca infoAggiuntiva corrispondente
        # Key formato: palinsesto-avvenimento-scommessa-infoAggiuntiva
        # infoAggiuntiva di default è 0
        info_keys = [k for k in info_map.keys() if k.startswith(f"{pal}-{avv}-{codice_scommessa}-")]
        
        selections = []
        for ik in info_keys:
            info = info_map[ik]
            for esito in info.get("esitoList", []):
                quota_raw = esito.get("quota", 0)
                quota_dec = quota_raw / 100.0 if quota_raw else 0.0
                selections.append({
                    "name": str(esito.get("descrizione", "")),
                    "label": str(esito.get("descrizione", "")),
                    "odds": round(quota_dec, 2),
                    "raw_odds": quota_raw,
                    "esito_code": esito.get("codiceEsito"),
                    "status": esito.get("stato", 1),
                })
        
        if selections:
            market_type = normalize_market_type(sc.get("descrizione", ""), sc.get("codiceScommessa"))
            markets.append({
                "market_type": market_type,
                "market_name": sc.get("descrizione", ""),
                "market_code": codice_scommessa,
                "selections": selections,
            })
    
    return markets


def normalize_market_type(desc: str, code: int | None) -> str:
    """Normalizza il tipo di mercato in una chiave standard."""
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
    if "CARTELLINI" in desc_upper:
        return "cartellini"
    
    return f"market_{code}"

# ---------------------------------------------------------------------------
# Database store
# ---------------------------------------------------------------------------

# Mappatura codici manifestazione SNAI -> nome lega leggibile
# Aggiornare quando SNAI introduce nuove leghe calcio
SNAI_COMPETITION_MAP = {
    # Calcio (codiceDisciplina=1)
    (1, 765): "Amichevoli Internazionali",
    (1, 766): "Qualificazioni Mondiali",
    (1, 767): "Qualificazioni Europei",
    (1, 768): "Serie A",
    (1, 769): "Serie B",
    (1, 770): "Champions League",
    (1, 771): "Europa League",
    (1, 772): "Conference League",
    (1, 773): "Premier League",
    (1, 774): "La Liga",
    (1, 775): "Bundesliga",
    (1, 776): "Ligue 1",
    # Basket (codiceDisciplina=2)
    (2, 1200): "Basket Italia",
    (2, 1246): "WNBA",
    # Tennis (codiceDisciplina=3)
    (3, 1679): "Tennis ATP",
    (3, 1866): "Tennis ATP",
    # Ciclismo (codiceDisciplina=11)
    (11, 2793): "Ciclismo su strada",
}


def resolve_competition_name(discipline_code: int, competition_code) -> str:
    """Mappa (disciplina, manifestazione) SNAI in nome lega leggibile.

    Se il codice non è nella mappa, ritorna un fallback basato sulla disciplina.
    """
    if competition_code is None:
        return ""
    try:
        dc = int(discipline_code)
        cc = int(competition_code)
    except (TypeError, ValueError):
        return ""

    # Cerca mappatura esatta
    name = SNAI_COMPETITION_MAP.get((dc, cc))
    if name:
        return name

    # Fallback per disciplina calcio
    if dc == 1:
        return f"Calcio (manifestazione {cc})"
    elif dc == 2:
        return f"Basket (manifestazione {cc})"
    elif dc == 3:
        return f"Tennis (manifestazione {cc})"
    elif dc == 11:
        return f"Ciclismo (manifestazione {cc})"
    return f"Disciplina {dc} (manifestazione {cc})"


def store_in_db(events: list[dict], db_path: str = DB_PATH):
    """Salva eventi e quote nel database WinBet."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    inserted_events = 0
    inserted_odds = 0

    for ev in events:
        # Mappa campi evento -> schema DB
        # match_id nel DB = event_id della fonte (snai-pal-avv)
        match_id = ev["event_id"]
        # Prova prima la mappatura da codice manifestazione
        league_id = resolve_competition_name(
            ev.get("discipline_code"),
            ev.get("competition_code"),
        )
        # Fallback al campo competition se popolato
        if not league_id:
            league_id = ev.get("competition", "")
        home_team = ev["home_team"]
        away_team = ev["away_team"]
        # Parse start_time in date/time se presente
        match_date = ""
        match_time = ""
        start = ev.get("start_time", "")
        if start and "T" in start:
            parts = start.split("T")
            match_date = parts[0]
            match_time = parts[1][:5] if len(parts[1]) >= 5 else parts[1]
        
        # Inserisci/aggiorna partita (match_id = chiave esterna)
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
        
        # Inserisci/aggiorna quote per ogni mercato
        for mkt in ev.get("markets", []):
            for sel in mkt["selections"]:
                # Salva in odds_history
                c.execute("""
                    INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (match_id, "snai", mkt["market_type"], sel["name"], sel["odds"], now))
                
                # Upsert in odds attuale (match_id + bookmaker + market + selection)
                c.execute("""
                    INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO UPDATE SET
                        odds_value=excluded.odds_value,
                        odds_decimal=excluded.odds_decimal,
                        scraped_at=excluded.scraped_at,
                        updated_at=excluded.updated_at
                """, (match_id, "snai", mkt["market_type"], sel["name"], sel["label"], sel["odds"], sel["odds"], now, now))
                inserted_odds += 1
    
    # Log scrape
    c.execute("""
        INSERT INTO scrape_log (bookmaker_id, league_id, matches_found, odds_found, started_at, completed_at, errors)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("snai", "ALL", inserted_events, inserted_odds, now, now, None))
    
    conn.commit()
    conn.close()
    print(f"\n💾 Database: {inserted_events} partite, {inserted_odds} quote salvate")
    return inserted_events, inserted_odds


# ---------------------------------------------------------------------------
# Surebet detection (cross-bookmaker)
# ---------------------------------------------------------------------------

def detect_surebets(all_events: list[dict]) -> list[dict]:
    """Rileva surebet confrontando quote tra bookmaker."""
    surebets = []
    
    # Raggruppa per match normalizzato
    matches = {}
    for ev in all_events:
        key = f"{ev.get('home_team','').lower()}|{ev.get('away_team','').lower()}"
        if key not in matches:
            matches[key] = []
        matches[key].append(ev)
    
    for match_key, ev_list in matches.items():
        if len(ev_list) < 2:
            continue
        
        # Confronta mercati 1x2
        best_odds = {"1": {}, "X": {}, "2": {}}
        
        for ev in ev_list:
            for mkt in ev.get("markets", []):
                if mkt["market_type"] == "1x2":
                    for sel in mkt["selections"]:
                        name = sel["name"]
                        odds = sel["odds"]
                        source = ev["source"]
                        if name in best_odds and (not best_odds[name] or odds > best_odds[name]["odds"]):
                            best_odds[name] = {"odds": odds, "source": source, "bookmaker": source}
        
        # Calcola margine
        if all(best_odds[k] for k in best_odds):
            margin = sum(1.0 / best_odds[k]["odds"] for k in best_odds)
            if margin < 1.0:
                profit = (1.0 - margin) * 100
                surebets.append({
                    "match": match_key.replace("|", " vs "),
                    "margin": round(margin, 4),
                    "profit_pct": round(profit, 2),
                    "best_odds": best_odds,
                })
    
    return surebets

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="WinBet SNAI Scraper")
    parser.add_argument("--output", "-o", default="/tmp/snai_scraped.json", help="File JSON di output")
    parser.add_argument("--store-db", action="store_true", help="Salva nel database SQLite")
    parser.add_argument("--all-endpoints", action="store_true", help="Scarica da tutti gli endpoint (top-match + hot-bets + monoquota)")
    parser.add_argument("--discipline", default="calcio", help="Filtra per disciplina (calcio, tennis, basket, all)")
    
    args = parser.parse_args()
    
    print("═" * 60)
    print("  WinBet SNAI Scraper — Quote da flutterseatech.it")
    print("═" * 60)
    
    # Fetch dati
    if args.all_endpoints:
        raw_data = fetch_all_endpoints()
        # Unifica eventi da tutti gli endpoint
        all_events_raw = []
        for name, data in raw_data.items():
            if data:
                events = parse_snai_data(data)
                all_events_raw.extend(events)
        # Deduplica per event_id
        seen = set()
        all_events = []
        for ev in all_events_raw:
            if ev["event_id"] not in seen:
                seen.add(ev["event_id"])
                all_events.append(ev)
    else:
        data = fetch_top_match()
        all_events = parse_snai_data(data)
    
    # Filtra per disciplina
    if args.discipline != "all":
        disc_filter = args.discipline.lower()
        all_events = [ev for ev in all_events if disc_filter in ev["discipline"].lower()]
    
    # Risultato
    result = {
        "bookmaker": "snai",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": "top-match" if not args.all_endpoints else "multi-endpoint",
        "total_events": len(all_events),
        "events": all_events,
    }
    
    # Scrivi JSON
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Risultato: {len(all_events)} eventi estratti")
    
    # Stampa riepilogo
    disc_counts = {}
    for ev in all_events:
        d = ev["discipline"]
        disc_counts[d] = disc_counts.get(d, 0) + 1
    print(f"   Per disciplina: {disc_counts}")
    
    # Stampa prime partite calcio
    calcio = [ev for ev in all_events if "calcio" in ev["discipline"].lower()]
    if calcio:
        print(f"\n⚽ Prime partite calcio:")
        for ev in calcio[:5]:
            mkt_1x2 = None
            for m in ev["markets"]:
                if m["market_type"] == "1x2":
                    mkt_1x2 = m
                    break
            if mkt_1x2:
                q = " | ".join([f"{s['name']}={s['odds']}" for s in mkt_1x2["selections"]])
                print(f"   • {ev['home_team']} vs {ev['away_team']}: {q}")
            else:
                print(f"   • {ev['home_team']} vs {ev['away_team']} (no 1X2)")
    
    # Store DB
    if args.store_db:
        try:
            store_in_db(all_events)
        except Exception as e:
            print(f"\n❌ Errore database: {e}")
    
    print(f"\n💾 Output JSON: {args.output}")
    print("✅ Completato")


if __name__ == "__main__":
    main()

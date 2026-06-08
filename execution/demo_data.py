#!/usr/bin/env python3
"""WinBet Demo Data Generator — Popola il DB con quote realistiche simulate.

Da usare come fallback quando:
- The Odds API crediti esauriti
- Scraping diretto bloccato da anti-bot/CAPTCHA

Le quote sono realistiche e basate su range tipici dei bookmaker italiani.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import hashlib
import json
import random
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_CONFIG = ROOT / "config" / "db_config.json"
COMPETITIONS_FILE = ROOT / "config" / "competitions.json"

def get_db():
    cfg = json.loads(DB_CONFIG.read_text(encoding="utf-8"))
    conn = sqlite3.connect(cfg["path"], check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def event_hash(home: str, away: str, start: str) -> str:
    return hashlib.sha256(f"{home}|{away}|{start}".encode()).hexdigest()[:16]

# === Squadre per campionato ===
TEAMS = {
    "serie-a": [
        ("Atalanta", 1.75), ("Bologna", 2.10), ("Cagliari", 2.65), ("Como", 2.80),
        ("Empoli", 2.90), ("Fiorentina", 2.20), ("Genoa", 2.55), ("Inter", 1.55),
        ("Juventus", 1.65), ("Lazio", 2.05), ("Lecce", 3.00), ("Milan", 1.80),
        ("Monza", 2.75), ("Napoli", 1.70), ("Parma", 2.70), ("Roma", 2.00),
        ("Torino", 2.40), ("Udinese", 2.60), ("Venezia", 3.10), ("Verona", 2.50),
    ],
    "premier-league": [
        ("Arsenal", 1.80), ("Aston Villa", 2.20), ("Bournemouth", 2.80), ("Brentford", 2.60),
        ("Brighton", 2.40), ("Chelsea", 2.10), ("Crystal Palace", 2.70), ("Everton", 2.75),
        ("Fulham", 2.65), ("Ipswich", 3.10), ("Leicester", 2.85), ("Liverpool", 1.60),
        ("Man City", 1.55), ("Man Utd", 2.00), ("Newcastle", 2.15), ("Nottm Forest", 2.55),
        ("Southampton", 3.00), ("Tottenham", 1.90), ("West Ham", 2.45), ("Wolves", 2.50),
    ],
    "la-liga": [
        ("Alaves", 2.75), ("Athletic Bilbao", 2.20), ("Atletico Madrid", 1.80), ("Barcelona", 1.60),
        ("Celta Vigo", 2.60), ("Espanyol", 2.80), ("Getafe", 2.55), ("Girona", 2.35),
        ("Las Palmas", 2.90), ("Leganes", 3.00), ("Mallorca", 2.70), ("Osasuna", 2.50),
        ("Rayo Vallecano", 2.65), ("Real Betis", 2.15), ("Real Madrid", 1.55), ("Real Sociedad", 2.25),
        ("Sevilla", 2.30), ("Valencia", 2.40), ("Valladolid", 2.95), ("Villarreal", 2.10),
    ],
    "bundesliga": [
        ("Augsburg", 2.60), ("Bayern Munich", 1.50), ("Bochum", 3.00), ("Borussia Dortmund", 1.85),
        ("Eintracht Frankfurt", 2.15), ("Freiburg", 2.40), ("Heidenheim", 2.85), ("Hoffenheim", 2.35),
        ("Holstein Kiel", 3.10), ("Leipzig", 1.75), ("Leverkusen", 1.70), ("Mainz", 2.55),
        ("Monchengladbach", 2.20), ("Stuttgart", 2.05), ("Union Berlin", 2.50), ("Werder Bremen", 2.45),
        ("Wolfsburg", 2.30), ("St. Pauli", 2.90),
    ],
    "ligue-1": [
        ("Angers", 2.95), ("Auxerre", 2.85), ("Brest", 2.50), ("Le Havre", 3.00),
        ("Lens", 2.20), ("Lille", 2.05), ("Lyon", 2.10), ("Marseille", 1.90),
        ("Monaco", 1.80), ("Montpellier", 2.60), ("Nantes", 2.55), ("Nice", 2.15),
        ("Paris SG", 1.50), ("Reims", 2.45), ("Rennes", 2.25), ("Strasbourg", 2.40),
        ("St Etienne", 2.70), ("Toulouse", 2.35),
    ],
    "champions-league": [
        ("Arsenal", 1.80), ("Aston Villa", 2.30), ("Atletico Madrid", 2.00), ("Barcelona", 1.70),
        ("Bayern Munich", 1.75), ("Benfica", 2.40), ("Borussia Dortmund", 2.10), ("Brest", 2.80),
        ("Celtic", 2.90), ("Feyenoord", 2.85), ("Inter", 1.85), ("Juventus", 2.05),
        ("Leverkusen", 1.90), ("Lille", 2.35), ("Liverpool", 1.65), ("Man City", 1.60),
        ("Milan", 2.00), ("Monaco", 2.25), ("Paris SG", 1.70), ("PSV", 2.45),
        ("Real Madrid", 1.55), ("RB Leipzig", 2.15), ("Sporting CP", 2.50), ("Stuttgart", 2.30),
    ],
}

BOOKMAKERS = ["SNAI", "Eurobet", "Goldbet", "WilliamHill", "Sisal", "Lottomatica", "Bet365"]

def generate_fixture(teams: list, offset_hours: int) -> dict:
    """Generate a single match with realistic odds from multiple bookmakers."""
    t1, t2 = random.sample(teams, 2)
    home_name, home_strength = t1
    away_name, away_strength = t2

    start = (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).isoformat()

    # Base odds derived from team strength
    base_1 = round((home_strength + away_strength) / home_strength * 1.35, 2)
    base_2 = round((home_strength + away_strength) / away_strength * 1.35, 2)
    base_x = round((base_1 + base_2) / 2.2, 2)

    # Over/Under 2.5
    base_over = round(random.uniform(1.65, 2.15), 2)
    base_under = round(random.uniform(1.70, 2.20), 2)

    # BTTS
    base_gg = round(random.uniform(1.65, 2.10), 2)
    base_ng = round(random.uniform(1.75, 2.25), 2)

    # Doppia chance
    dc_1x = round(1.0 / (1.0/base_1 + 1.0/base_x) * 0.92, 2)
    dc_12 = round(1.0 / (1.0/base_1 + 1.0/base_2) * 0.92, 2)
    dc_x2 = round(1.0 / (1.0/base_x + 1.0/base_2) * 0.92, 2)

    markets = {}
    for bk in BOOKMAKERS:
        noise = random.uniform(0.92, 1.08)
        markets[bk] = {
            "1X2": {
                "1": round(base_1 * noise, 2),
                "X": round(base_x * noise, 2),
                "2": round(base_2 * noise, 2),
            },
            "OU25": {
                "Over": round(base_over * noise, 2),
                "Under": round(base_under * noise, 2),
            },
            "BTTS": {
                "GG": round(base_gg * noise, 2),
                "NG": round(base_ng * noise, 2),
            },
            "DC": {
                "1X": round(dc_1x * noise, 2),
                "12": round(dc_12 * noise, 2),
                "X2": round(dc_x2 * noise, 2),
            },
        }
    return {
        "home": home_name, "away": away_name,
        "start": start, "markets": markets,
    }

def generate_round(comp_key: str, num_matches: int = 5) -> list[dict]:
    teams = TEAMS.get(comp_key, [])
    if not teams:
        return []
    fixtures = []
    used = set()
    for i in range(num_matches):
        # Ensure no duplicate pairings in same round
        attempts = 0
        while attempts < 20:
            fx = generate_fixture(teams, offset_hours=random.randint(1, 72))
            pair = tuple(sorted([fx["home"], fx["away"]]))
            if pair not in used:
                used.add(pair)
                fixtures.append(fx)
                break
            attempts += 1
    return fixtures

def upsert_fixture(conn, fixture: dict, comp_key: str) -> int:
    ev = {
        "event_id": event_hash(fixture["home"], fixture["away"], fixture["start"]),
        "home_team": fixture["home"],
        "away_team": fixture["away"],
        "start_time": fixture["start"],
        "competition": comp_key,
        "league": comp_key,
    }
    eid = event_hash(ev["home_team"], ev["away_team"], ev["start_time"])
    cur = conn.execute(
        "SELECT id FROM events WHERE event_id=? AND home_team=? AND away_team=?",
        (eid, ev["home_team"], ev["away_team"]),
    )
    row = cur.fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if row:
        conn.execute(
            "UPDATE events SET start_time=?, competition=?, league=?, scraped_at=? WHERE id=?",
            (ev["start_time"], comp_key, comp_key, now, row[0]),
        )
        event_rowid = row[0]
    else:
        cur = conn.execute(
            "INSERT INTO events(event_id,home_team,away_team,start_time,competition,league,scraped_at) VALUES (?,?,?,?,?,?,?)",
            (eid, ev["home_team"], ev["away_team"], ev["start_time"], comp_key, comp_key, now),
        )
        event_rowid = cur.lastrowid

    # Insert/update odds for each bookmaker and market
    for bk, mkts in fixture["markets"].items():
        for mtype, selections in mkts.items():
            for sel, odds in selections.items():
                if odds < 1.01:
                    continue
                cur = conn.execute(
                    "SELECT id, odds FROM odds WHERE event_id=? AND bookmaker=? AND market_type=? AND selection=?",
                    (event_rowid, bk, mtype, sel),
                )
                row = cur.fetchone()
                if row:
                    old = row[1]
                    if abs(old - odds) >= 0.01:
                        change = round(((odds - old) / old) * 100, 2) if old else 0.0
                        conn.execute(
                            "UPDATE odds SET odds=?, scraped_at=? WHERE id=?",
                            (odds, now, row[0]),
                        )
                        conn.execute(
                            "INSERT INTO odds_history(event_id,bookmaker,market_type,selection,odds_old,odds_new,change_pct,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                            (event_rowid, bk, mtype, sel, old, odds, change, now),
                        )
                else:
                    conn.execute(
                        "INSERT INTO odds(event_id,bookmaker,market_type,selection,odds,scraped_at) VALUES (?,?,?,?,?,?)",
                        (event_rowid, bk, mtype, sel, odds, now),
                    )
    return event_rowid

def generate_all(competitions: list[str] | None = None, matches_per_comp: int = 5):
    if competitions is None:
        competitions = list(TEAMS.keys())
    conn = get_db()
    results = []
    for comp in competitions:
        fixtures = generate_round(comp, matches_per_comp)
        for fx in fixtures:
            upsert_fixture(conn, fx, comp)
        results.append({
            "competition": comp,
            "matches": len(fixtures),
        })
    conn.commit()
    conn.close()
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WinBet Demo Data Generator")
    parser.add_argument("--competition", default=None, help="Specific competition key")
    parser.add_argument("--matches", type=int, default=5, help="Matches per competition")
    parser.add_argument("--all", action="store_true", help="All configured competitions")
    args = parser.parse_args()

    if args.all:
        comps = list(TEAMS.keys())
    elif args.competition:
        comps = [args.competition]
    else:
        print("Use --all or --competition KEY")
        return

    results = generate_all(comps, args.matches)
    total = sum(r["matches"] for r in results)
    print(f"Generated {total} demo matches across {len(results)} competitions.")
    for r in results:
        print(f"  {r['competition']}: {r['matches']} matches")

if __name__ == "__main__":
    main()

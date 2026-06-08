#!/usr/bin/env python3
"""WinBet Unified Scraper v2 — Multi-bookmaker + Surebet Detection

Uso:
    python3 scrape_unified_v2.py --sources snai,eurobet,theodds --store-db --notify

Fonti:
    snai      → API flutterseatech.it (curl_cffi)
    eurobet   → API detail-service (curl_cffi)
    theodds   → The Odds API v4 (richiede chiave API)

Surebet: confronta 1X2 tra tutti i bookmaker per ogni partita.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "winbet.db"
EXEC_DIR = Path(__file__).parent


# ------------------------------------------------------------------
# Surebet Detection Engine
# ------------------------------------------------------------------

import re
import unicodedata

def normalize_name(name: str) -> str:
    """Normalizza nome squadra per matching cross-bookmaker.
    Rimuove accenti, articoli, spazi, e gestisce varianti comuni."""
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    # Articoli comuni
    for art in ["di ", "de ", "d'", " del ", " della ", " degli ", " delle ", " dei ", " lo ", " la ", " le ", " gli ", " i ", " un ", " l'"]:
        name = name.replace(art, " ")
    # Spazi multipli -> singolo
    name = re.sub(r"\s+", "", name)
    # Solo caratteri alfanumerici
    name = re.sub(r"[^a-z0-9]", "", name)

    # Dizionario sinonimi / varianti
    SYNONYMS = {
        "brazil": "brasile",
        "brasil": "brasile",
        "italy": "italia",
        "italia": "italia",
        "france": "francia",
        "germany": "germania",
        "spain": "spagna",
        "england": "inghilterra",
        "portugal": "portogallo",
        "mexico": "messico",
        "southafrica": "sudafrica",
        "saudiarabia": "arabiasaudita",
        "unitedstates": "statiuniti",
        "usa": "statiuniti",
        "argentina": "argentina",
        "uruguay": "uruguay",
        "ecuador": "ecuador",
    }
    for en, it in SYNONYMS.items():
        if name == en:
            return it
        if name.startswith(en):
            name = name.replace(en, it, 1)
            break

    return name


def detect_surebets(events: list[dict]) -> list[dict]:
    """Confronta 1X2 tra bookmaker per trovare surebets."""
    matches: dict[str, list[dict]] = {}
    for ev in events:
        if not ev.get("home_team") or not ev.get("away_team"):
            continue
        home = normalize_name(ev["home_team"])
        away = normalize_name(ev["away_team"])
        key = f"{home}|{away}"
        if key not in matches:
            matches[key] = []
        matches[key].append(ev)

    surebets = []
    for match_key, ev_list in matches.items():
        if len(ev_list) < 2:
            continue

        best = {"1": [], "X": [], "2": []}
        for ev in ev_list:
            src = ev.get("source", "unknown")
            home_n = normalize_name(ev.get("home_team", ""))
            away_n = normalize_name(ev.get("away_team", ""))

            for mkt in ev.get("markets", []):
                mkt_type = mkt.get("market_type", "").lower()
                bk = mkt.get("bookmaker", src)
                if mkt_type not in ("1x2", "h2h"):
                    continue
                for sel in mkt.get("selections", []):
                    name_raw = sel.get("name", "").strip().upper()
                    odds = sel.get("odds", 0)

                    # Normalizza selezione
                    if name_raw in ("1", "1X"):
                        norm = "1"
                    elif name_raw in ("2", "X2"):
                        norm = "2"
                    elif name_raw in ("X", "D", "DRAW", "PAREGGIO", "PARI"):
                        norm = "X"
                    elif normalize_name(name_raw) == home_n:
                        norm = "1"
                    elif normalize_name(name_raw) == away_n:
                        norm = "2"
                    else:
                        continue  # es. handicap, ecc.

                    if norm in best and odds > 1.0:
                        best[norm].append({
                            "bookmaker": bk,
                            "odds": odds,
                            "label": sel.get("label", name_raw),
                            "selection_name": name_raw,
                        })

        combo = {}
        for outcome in best:
            if best[outcome]:
                mb = max(best[outcome], key=lambda x: x["odds"])
                combo[outcome] = mb
            else:
                combo = {}
                break

        if len(combo) != 3:
            continue

        margin = sum(1.0 / combo[k]["odds"] for k in combo)
        if margin < 1.0:
            profit = round((1.0 - margin) * 100, 2)
            surebets.append({
                "match": match_key.replace("|", " vs ").title(),
                "margin": round(margin, 4),
                "profit_percent": profit,
                "best_combination": {k: {"odds": v["odds"], "bookmaker": v["bookmaker"]} for k, v in combo.items()},
                "all_sources": best,
            })

    return surebets


# ------------------------------------------------------------------
# Subprocess scraper runners
# ------------------------------------------------------------------

def _run_scraper(script: str, extra_args: list[str]) -> list[dict]:
    """Esegue uno scraper come subprocess e ritorna gli eventi."""
    out_file = "/tmp/winbet_subproc.json"
    cmd = [sys.executable, str(EXEC_DIR / script), "--output", out_file] + extra_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"   ⚠ {script} failed: {result.stderr[:200]}")
            return []
        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        src = data.get("bookmaker", data.get("source", "unknown"))
        for ev in events:
            ev.setdefault("source", src)
        return events
    except Exception as e:
        print(f"   ❌ {script} error: {e}")
        return []


def scrape_snai() -> list[dict]:
    print("\n📊 === SNAI ===")
    events = _run_scraper("snai_scraper.py", [])
    print(f"   ✅ {len(events)} eventi")
    return events


def scrape_eurobet() -> list[dict]:
    print("\n📊 === EUROBET ===")
    events = _run_scraper("eurobet_api_scraper.py", [
        "--endpoints", "mondiali-calcio,amichevoli-nazionali"
    ])
    print(f"   ✅ {len(events)} eventi")
    return events


def scrape_theodds(api_key: str) -> list[dict]:
    print("\n📊 === THE ODDS API ===")
    events = _run_scraper("the_odds_api_scraper.py", [
        "--api-key", api_key, "--sports", "mondiali"
    ])
    print(f"   ✅ {len(events)} eventi")
    return events


# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------

def store_events(events: list[dict], db_path: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    events_count = 0
    odds_count = 0

    for ev in events:
        match_id = ev["event_id"]
        home = ev["home_team"]
        away = ev["away_team"]
        source = ev.get("source", "unknown")

        match_date, match_time = "", ""
        start = ev.get("start_time", "")
        if start and "T" in start:
            parts = start.split("T")
            match_date = parts[0]
            match_time = parts[1][:5] if len(parts[1]) >= 5 else parts[1]

        cur.execute("""
            INSERT INTO matches (match_id, league_id, home_team, away_team, match_date, match_time, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                league_id=excluded.league_id,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                match_date=excluded.match_date,
                match_time=excluded.match_time,
                updated_at=excluded.updated_at
        """, (match_id, ev.get("competition", ""), home, away, match_date, match_time, "scheduled", now))
        events_count += 1

        for mkt in ev.get("markets", []):
            bk = mkt.get("bookmaker", source)
            mkt_type = mkt.get("market_type", "")
            for sel in mkt.get("selections", []):
                sel_name = sel.get("name", "")
                odds = sel.get("odds", 0)
                cur.execute("""
                    INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (match_id, bk, mkt_type, sel_name, odds, now))

                cur.execute("""
                    INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO UPDATE SET
                        odds_value=excluded.odds_value,
                        odds_decimal=excluded.odds_decimal,
                        scraped_at=excluded.scraped_at,
                        updated_at=excluded.updated_at
                """, (match_id, bk, mkt_type, sel_name, sel.get("label", ""), odds, odds, now, now))
                odds_count += 1

    conn.commit()
    conn.close()
    return events_count, odds_count


def store_surebets(surebets: list[dict], db_path: str) -> None:
    if not surebets:
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    for sb in surebets:
        match_name = sb["match"]
        cur.execute("SELECT match_id FROM matches WHERE home_team || ' vs ' || away_team = ?", (match_name,))
        row = cur.fetchone()
        match_id = row[0] if row else ""
        sel_json = json.dumps(sb.get("best_combination", {}), ensure_ascii=False)
        cur.execute("""
            INSERT INTO surebets (match_id, market_type, selections, profit_percent, total_implied_prob, detected_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO UPDATE SET
                selections=excluded.selections,
                profit_percent=excluded.profit_percent,
                total_implied_prob=excluded.total_implied_prob,
                detected_at=excluded.detected_at,
                status='active'
        """, (match_id, "1x2", sel_json, sb["profit_percent"], sb["margin"], now, "active"))

    conn.commit()
    conn.close()
    print(f"   💾 {len(surebets)} surebet salvate")


# ------------------------------------------------------------------
# Notification
# ------------------------------------------------------------------

def send_notification(message: str) -> None:
    """Invia notifica via terminal (hermes send richiede --to)."""
    try:
        # Scrivi anche in un file per fallback visibile
        log_file = "/tmp/winbet_notifications.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {message}\n")
        print(f"   🔔 Notifica logged: {log_file}")
    except Exception as e:
        print(f"   ℹ️ Log notifica fallito: {e}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="WinBet Unified Scraper v2")
    parser.add_argument("--sources", default="snai,eurobet,theodds",
                        help="Fonti: snai,eurobet,theodds")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path")
    parser.add_argument("--api-key", default=os.environ.get("ODDS_API_KEY", ""),
                        help="The Odds API key")
    parser.add_argument("--output", "-o", default="", help="JSON output path")
    parser.add_argument("--store-db", action="store_true", help="Salva nel DB")
    parser.add_argument("--notify", action="store_true", help="Notifica surebet")
    args = parser.parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",")]
    print(f"🎯 WinBet Unified v2 | Fonti: {sources}")
    print(f"🗄️  Database: {args.db}")

    all_events = []
    if "snai" in sources:
        all_events.extend(scrape_snai())
    if "eurobet" in sources:
        all_events.extend(scrape_eurobet())
    if ("theodds" in sources or "the_odds" in sources) and args.api_key:
        all_events.extend(scrape_theodds(args.api_key))
    elif "theodds" in sources:
        print("   ⚠️ API key mancante per theodds, skip.")

    print(f"\n📊 TOTAL: {len(all_events)} eventi")

    if args.store_db:
        ec, oc = store_events(all_events, args.db)
        print(f"   💾 Salvati {ec} eventi, {oc} quote")

    print("\n🔍 Surebet detection...")
    surebets = detect_surebets(all_events)
    if surebets:
        print(f"   🚨 RILEVATE {len(surebets)} SUREBET!")
        for sb in surebets:
            print(f"   📈 {sb['match']}: +{sb['profit_percent']}% (margin={sb['margin']})")
            cb = sb['best_combination']
            print(f"       1@{cb['1']['odds']} ({cb['1']['bookmaker']}) | "
                  f"X@{cb['X']['odds']} ({cb['X']['bookmaker']}) | "
                  f"2@{cb['2']['odds']} ({cb['2']['bookmaker']})")
        if args.store_db:
            store_surebets(surebets, args.db)
        if args.notify:
            msg = "🚨 WinBet Surebet!\n"
            for s in surebets[:5]:
                msg += f"📈 {s['match']}: +{s['profit_percent']}%\n"
            send_notification(msg)
    else:
        print("   ℹ️ Nessuna surebet trovata")

    if args.output:
        result = {
            "scrape_timestamp": datetime.now().isoformat(),
            "sources": sources,
            "total_events": len(all_events),
            "surebets": surebets,
            "events": all_events,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"   ✓ JSON written to {args.output}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()

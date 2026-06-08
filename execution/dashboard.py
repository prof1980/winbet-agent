#!/usr/bin/env python3
"""WinBet Dashboard — Server Flask con visualizzazione quote e surebet."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR.parent / "winbet.db"
CONFIG_PATH = APP_DIR.parent / "winbet_config.json"

app = Flask(__name__, template_folder=str(APP_DIR / "templates"), static_folder=str(APP_DIR / "static"))

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/leagues")
def api_leagues():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT league_id, COUNT(*) as matches FROM matches WHERE status='scheduled' GROUP BY league_id")
    leagues = [{"id": row["league_id"], "matches": row["matches"]} for row in c.fetchall()]
    conn.close()
    return jsonify(leagues)

@app.route("/api/matches/<league_id>")
def api_matches(league_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM matches
        WHERE league_id = ? AND status = 'scheduled'
        ORDER BY match_date, match_time
    """, (league_id,))
    rows = c.fetchall()
    matches = []
    for r in rows:
        # Ottieni TUTTE le quote per questa partita, raggruppate per (market, selection)
        c.execute("""
            SELECT bookmaker_id, market_type, selection_name, selection_label, odds_decimal
            FROM odds
            WHERE match_id = ?
            ORDER BY market_type, selection_name, odds_decimal DESC
        """, (r["match_id"],))
        all_odds = c.fetchall()

        # Calcola best_odds per (market, selection) e bookmaker
        best_per_sel = {}
        for o in all_odds:
            key = (o["market_type"], o["selection_name"])
            if key not in best_per_sel or o["odds_decimal"] > best_per_sel[key]["odds"]:
                best_per_sel[key] = {"odds": o["odds_decimal"], "bookmaker": o["bookmaker_id"]}

        # Costruisci struttura: { market: [{ selection, label, odds, bookmaker, is_best, all_bookmakers: [...] }, ...] }
        # Ogni "selezione" ora include TUTTI i bookmaker come all_bookmakers
        sel_map = {}
        for o in all_odds:
            key = (o["market_type"], o["selection_name"])
            if key not in sel_map:
                sel_map[key] = {
                    "market_type": o["market_type"],
                    "selection_name": o["selection_name"],
                    "selection_label": o["selection_label"],
                    "all_bookmakers": []  # lista di {bookmaker, odds}
                }
            sel_map[key]["all_bookmakers"].append({
                "bookmaker": o["bookmaker_id"],
                "odds": o["odds_decimal"]
            })

        # Trasforma in struttura per template
        odds = {}
        for key, info in sel_map.items():
            mt = info["market_type"]
            if mt not in odds:
                odds[mt] = []
            best_info = best_per_sel[key]
            # Formatta selezione: best_bookmaker + lista completa
            odds[mt].append({
                "selection": info["selection_name"],
                "label": info["selection_label"],
                "odds": best_info["odds"],   # quota migliore (per compatibilità con template esistente)
                "bookmaker": best_info["bookmaker"],  # bookmaker migliore
                "all_bookmakers": info["all_bookmakers"]  # TUTTI i bookmaker per questa selezione
            })

        matches.append({
            "id": r["match_id"],
            "home": r["home_team"],
            "away": r["away_team"],
            "league_id": r["league_id"],
            "league": r["league_id"],
            "date": r["match_date"],
            "time": r["match_time"],
            "odds": odds
        })
    conn.close()
    return jsonify(matches)

@app.route("/api/odds/<match_id>")
def api_match_odds(match_id):
    """Tutte le quote di tutti i bookmaker per una partita."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT bookmaker_id, market_type, selection_name, selection_label, odds_value, updated_at
        FROM odds
        WHERE match_id = ?
        ORDER BY market_type, selection_name, odds_value DESC
    """, (match_id,))
    rows = c.fetchall()
    
    result = {}
    for r in rows:
        mt = r["market_type"]
        if mt not in result:
            result[mt] = {}
        sel = r["selection_name"]
        if sel not in result[mt]:
            result[mt][sel] = {"label": r["selection_label"], "bookmakers": []}
        result[mt][sel]["bookmakers"].append({
            "bookmaker": r["bookmaker_id"],
            "odds": r["odds_value"],
            "updated": r["updated_at"]
        })
    conn.close()
    return jsonify(result)

@app.route("/api/surebets")
def api_surebets():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT s.*, m.home_team, m.away_team, m.match_date, m.match_time
        FROM surebets s
        JOIN matches m ON s.match_id = m.match_id
        WHERE s.status = 'active'
        ORDER BY s.profit_percent DESC
    """)
    rows = c.fetchall()
    surebets = []
    for r in rows:
        surebets.append({
            "id": r["id"],
            "match": f"{r['home_team']} vs {r['away_team']}",
            "date": r["match_date"],
            "time": r["match_time"],
            "market": r["market_type"],
            "selections": json.loads(r["selections"]),
            "profit": round(r["profit_percent"], 2),
            "detected": r["detected_at"]
        })
    conn.close()
    return jsonify(surebets)

@app.route("/api/stats")
def api_stats():
    conn = get_db()
    c = conn.cursor()
    stats = {}
    c.execute("SELECT COUNT(*) FROM matches"); stats["total_matches"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM odds"); stats["total_odds"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surebets WHERE status='active'"); stats["active_surebets"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM notifications"); stats["notifications_sent"] = c.fetchone()[0]
    c.execute("SELECT MAX(scraped_at) FROM odds"); stats["last_update"] = c.fetchone()[0] or "N/A"
    conn.close()
    return jsonify(stats)


@app.route("/api/matches_finished_count")
def api_matches_finished_count():
    """Conta le partite con data+ora passata rispetto a now()."""
    conn = get_db()
    c = conn.cursor()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Combina match_date + match_time, paragona con adesso
    c.execute("""
        SELECT COUNT(*) FROM matches
        WHERE (match_date || ' ' || COALESCE(match_time, '23:59')) < ?
    """, (now_iso,))
    count = c.fetchone()[0]
    conn.close()
    return jsonify({"finished_count": count, "now": now_iso})


@app.route("/api/cleanup_finished", methods=["POST", "GET", "DELETE"])
def api_cleanup_finished():
    """Elimina partite con data+ora passata (più quote, history, surebet correlate)."""
    conn = get_db()
    c = conn.cursor()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Trova match_id delle partite terminate
    c.execute("""
        SELECT match_id FROM matches
        WHERE (match_date || ' ' || COALESCE(match_time, '23:59')) < ?
    """, (now_iso,))
    finished_ids = [row[0] for row in c.fetchall()]

    if not finished_ids:
        conn.close()
        return jsonify({"deleted_matches": 0, "deleted_odds": 0, "deleted_history": 0, "deleted_surebets": 0, "now": now_iso})

    # Conta prima di eliminare
    placeholders = ",".join("?" * len(finished_ids))
    c.execute(f"SELECT COUNT(*) FROM odds WHERE match_id IN ({placeholders})", finished_ids)
    odds_count = c.fetchone()[0]
    c.execute(f"SELECT COUNT(*) FROM odds_history WHERE match_id IN ({placeholders})", finished_ids)
    history_count = c.fetchone()[0]
    c.execute(f"SELECT COUNT(*) FROM surebets WHERE match_id IN ({placeholders})", finished_ids)
    surebets_count = c.fetchone()[0]

    # Elimina tutto (cascade manuale)
    c.execute(f"DELETE FROM odds WHERE match_id IN ({placeholders})", finished_ids)
    c.execute(f"DELETE FROM odds_history WHERE match_id IN ({placeholders})", finished_ids)
    c.execute(f"DELETE FROM surebets WHERE match_id IN ({placeholders})", finished_ids)
    c.execute(f"DELETE FROM matches WHERE match_id IN ({placeholders})", finished_ids)
    conn.commit()
    conn.close()

    return jsonify({
        "deleted_matches": len(finished_ids),
        "deleted_odds": odds_count,
        "deleted_history": history_count,
        "deleted_surebets": surebets_count,
        "now": now_iso,
        "match_ids": finished_ids[:10],  # prime 10 per preview
    })

if __name__ == "__main__":
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    dash = cfg["dashboard"]
    print(f"🚀 WinBet Dashboard: http://{dash['host']}:{dash['port']}")
    app.run(host=dash["host"], port=dash["port"], debug=False)

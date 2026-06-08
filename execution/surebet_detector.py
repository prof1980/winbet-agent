#!/usr/bin/env python3
"""WinBet SureBet Detector — Trova arbitraggi nelle quote.

Calcola la probabilità implicita totale per ogni mercato/partita.
Se la somma delle probabilità implicite è < 1.0, c'è un arbitraggio.

P(profit) = 1 - somma(1 / best_odds_per_selection)
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "/mnt/c/Users/angel/WinBet/winbet.db"
CONFIG_PATH = "/mnt/c/Users/angel/WinBet/winbet_config.json"

with open(CONFIG_PATH) as f:
    cfg = json.load(f)

MIN_PROFIT = cfg["notifications"]["min_surebet_profit"] / 100.0

def detect_surebets():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Per ogni partita e mercato, trova la miglior quota per selezione
    c.execute("""
        SELECT match_id, market_type, selection_name, selection_label,
               MAX(odds_value) as best_odds,
               (SELECT bookmaker_id FROM odds AS o2 
                WHERE o2.match_id = o.match_id AND o2.market_type = o.market_type AND o2.selection_name = o.selection_name
                ORDER BY o2.odds_value DESC LIMIT 1) as best_bookmaker
        FROM odds o
        GROUP BY match_id, market_type, selection_name
    """)
    
    # Raggruppa per partita/mercato
    markets = {}
    for row in c.fetchall():
        key = (row["match_id"], row["market_type"])
        if key not in markets:
            markets[key] = []
        markets[key].append({
            "selection": row["selection_name"],
            "label": row["selection_label"],
            "odds": row["best_odds"],
            "bookmaker": row["best_bookmaker"]
        })
    
    surebets_found = []
    
    for (match_id, market_type), selections in markets.items():
        # Calcola probabilità implicita totale
        total_implied = sum(1.0 / s["odds"] for s in selections)
        
        if total_implied < 1.0:
            profit = (1.0 - total_implied) * 100  # percentuale
            if profit >= cfg["notifications"]["min_surebet_profit"]:
                # Verifica se già esiste
                c.execute("SELECT id FROM surebets WHERE match_id=? AND market_type=? AND status='active'", (match_id, market_type))
                existing = c.fetchone()
                
                selections_json = json.dumps(selections)
                
                if existing:
                    c.execute("""
                        UPDATE surebets 
                        SET profit_percent=?, total_implied_prob=?, selections=?, detected_at=CURRENT_TIMESTAMP
                        WHERE id=?
                    """, (profit, total_implied, selections_json, existing["id"]))
                    surebets_found.append({"id": existing["id"], "profit": profit, "updated": True})
                else:
                    c.execute("""
                        INSERT INTO surebets (match_id, market_type, selections, profit_percent, total_implied_prob, status)
                        VALUES (?, ?, ?, ?, ?, 'active')
                    """, (match_id, market_type, selections_json, profit, total_implied))
                    new_id = c.lastrowid
                    surebets_found.append({"id": new_id, "profit": profit, "new": True})
    
    # Invalida surebet vecchie non più valide
    c.execute("""
        UPDATE surebets SET status='expired'
        WHERE status='active' AND detected_at < datetime('now', '-2 hours')
    """)
    
    conn.commit()
    conn.close()
    return surebets_found

if __name__ == "__main__":
    found = detect_surebets()
    if found:
        print(f"🎯 SureBet trovate/aggiornate: {len(found)}")
        for sb in found:
            tag = "[NUOVA]" if sb.get("new") else "[AGGIORNATA]"
            print(f"   {tag} ID={sb['id']} Profit={sb['profit']:.2f}%")
    else:
        print("🔍 Nessuna surebet attiva al momento.")

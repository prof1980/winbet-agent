#!/usr/bin/env python3
"""
WinBet Match Dedup & Merge — Unisce partite duplicate da fonti diverse.

Quando più bookmaker (SNAI, Eurobet, The Odds API) salvano la stessa partita
con match_id diversi, leghe scritte in modo differente, e nomi squadra
localizzati (italiano/inglese), questo script le fonde in un unico record
mantenendo tutte le quote e selezionando la quota migliore in caso di conflitto.

Uso:
    python3 execution/dedupe_matches.py [--dry-run] [--backup]
"""
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Configurazione
DB_PATH = Path("/mnt/c/Users/angel/WinBet/winbet.db")
BACKUP_PATH = Path("/tmp/winbet_pre_merge.db")

LEAGUE_EQUIVALENCES = {
    "Amichevoli Internazionali": "Amichevoli Nazionali",
    "Amichevoli Nazionali": "Amichevoli Nazionali",
    "Mondiali 2026": "FIFA World Cup",
    "FIFA World Cup": "FIFA World Cup",
}

TEAM_NORMALIZE = {
    "messico": "mexico", "sudafrica": "south africa", "sud africa": "south africa",
    "repubblica di corea": "south korea", "corea del sud": "south korea",
    "repubblica ceca": "czech republic", "bosnia-erzegovina": "bosnia & herzegovina",
    "bosnia ed erzegovina": "bosnia & herzegovina", "bosnia erzegovina": "bosnia & herzegovina",
    "stati uniti": "usa", "emirati": "united arab emirates",
    "emirati arabi uniti": "united arab emirates", "arabia saudita": "saudi arabia",
    "capo verde": "cabo verde", "costa d'avorio": "ivory coast",
    "costa avorio": "ivory coast", "germania": "germany", "curacao": "curacao",
    "curaçao": "curacao", "olanda": "netherlands", "paesi bassi": "netherlands",
    "giappone": "japan", "turchia": "turkey", "brasile": "brazil", "marocco": "morocco",
    "haiti": "haiti", "scozia": "scotland", "qatar": "qatar", "svizzera": "switzerland",
    "inghilterra": "england", "francia": "france", "italia": "italy", "spagna": "spain",
    "portogallo": "portugal", "algeria": "algeria", "austria": "austria",
    "canada": "canada", "colombia": "colombia", "uzbekistan": "uzbekistan",
    "irlanda": "ireland", "irlanda del nord": "northern ireland", "galles": "wales",
    "camerun": "cameroon", "senegal": "senegal", "tunisia": "tunisia",
    "egipto": "egypt", "nuova zelanda": "new zealand", "cina": "china",
    "hong kong": "hong kong", "filippine": "philippines", "indonesia": "indonesia",
    "tailandia": "thailand", "myanmar": "myanmar", "cambogia": "cambodia",
    "india": "india", "tagikistan": "tajikistan", "armenia": "armenia",
    "moldova": "moldova", "ungheria": "hungary", "kazakistan": "kazakhstan",
    "angola": "angola", "repubblica centrafricana": "central african republic",
    "repubblica democratica del congo": "dr congo", "cile": "chile",
    "australia": "australia", "ghana": "ghana", "panama": "panama",
    "uruguay": "uruguay", "cambogia u23": "cambodia u23",
    "belgio": "belgium", "svezia": "sweden", "ecuador": "ecuador",
    "iraq": "iraq", "norvegia": "norway", "giordania": "jordan",
    "croazia": "croatia", "iran": "iran", "cabo verde": "cabo verde",
    "perù": "peru", "peru": "peru",
}


def normalize_team(name: str) -> str:
    """Normalizza nome squadra per il matching cross-bookmaker."""
    n = name.strip().lower()
    n = n.replace("'", "").replace("'", "").replace("`", "")
    n = " ".join(n.split())
    return TEAM_NORMALIZE.get(n, n)


def find_duplicates(conn) -> dict:
    """Trova gruppi di partite con leghe e squadre normalizzate uguali."""
    c = conn.cursor()
    c.execute("""
        SELECT match_id, league_id, home_team, away_team, match_date, match_time
        FROM matches
    """)
    all_matches = c.fetchall()
    groups = defaultdict(list)
    for m in all_matches:
        h = normalize_team(m[2])
        a = normalize_team(m[3])
        league_canon = LEAGUE_EQUIVALENCES.get(m[1], m[1])
        key = (h, a, m[4], league_canon)
        groups[key].append(m)
    return {k: v for k, v in groups.items() if len(v) > 1}


def merge_group(c, matches: list) -> tuple:
    """Fonde un gruppo di partite. Ritorna (n_odds, n_deleted, canonical_id)."""
    # Conta quote
    counts = []
    for m in matches:
        c.execute("SELECT COUNT(*) FROM odds WHERE match_id = ?", (m[0],))
        counts.append((m[0], c.fetchone()[0], m))
    counts.sort(key=lambda x: -x[1])
    canonical_id, n_q, canonical_match = counts[0]
    canonical_league = LEAGUE_EQUIVALENCES.get(canonical_match[1], canonical_match[1])
    duplicates_ids = [x[0] for x in counts[1:]]

    if canonical_match[1] != canonical_league:
        c.execute("UPDATE matches SET league_id = ? WHERE match_id = ?",
                  (canonical_league, canonical_id))

    if not canonical_match[5]:
        for _, _, m in counts[1:]:
            if m[5]:
                c.execute("UPDATE matches SET match_time = ? WHERE match_id = ?",
                          (m[5], canonical_id))
                break

    n_odds = 0
    for dup_id in duplicates_ids:
        c.execute("""
            SELECT bookmaker_id, market_type, selection_name, selection_label,
                   odds_value, odds_decimal, scraped_at, updated_at
            FROM odds WHERE match_id = ?
        """, (dup_id,))
        for odd in c.fetchall():
            bookmaker, market, sel_name, sel_label, odds_val, odds_dec, scraped, updated = odd
            c.execute("""
                SELECT id, odds_decimal FROM odds
                WHERE match_id = ? AND bookmaker_id = ? AND market_type = ? AND selection_name = ?
            """, (canonical_id, bookmaker, market, sel_name))
            ex = c.fetchone()
            if ex:
                ex_id, ex_dec = ex
                if odds_dec and ex_dec and odds_dec > ex_dec:
                    c.execute("UPDATE odds SET odds_decimal = ? WHERE id = ?", (odds_dec, ex_id))
            else:
                c.execute("""
                    INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name,
                                     selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (canonical_id, bookmaker, market, sel_name, sel_label,
                      odds_val, odds_dec, scraped, updated))
                n_odds += 1

        # Elimina
        c.execute("DELETE FROM odds WHERE match_id = ?", (dup_id,))
        c.execute("DELETE FROM odds_history WHERE match_id = ?", (dup_id,))
        c.execute("DELETE FROM matches WHERE match_id = ?", (dup_id,))

    return n_odds, len(duplicates_ids), canonical_id


def main() -> int:
    parser = argparse.ArgumentParser(description="WinBet Match Dedup & Merge")
    parser.add_argument("--dry-run", action="store_true", help="Non modificare il DB")
    parser.add_argument("--backup", action="store_true", help="Crea backup prima del merge")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ Database non trovato: {DB_PATH}")
        return 1

    if args.backup and not args.dry_run:
        shutil.copy(DB_PATH, BACKUP_PATH)
        print(f"📦 Backup creato: {BACKUP_PATH}")

    print(f"📂 Apertura DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print("🔍 Ricerca partite duplicate...")
    duplicates = find_duplicates(conn)

    if not duplicates:
        print("✅ Nessuna partita duplicata trovata.")
        return 0

    print(f"📊 Trovati {len(duplicates)} gruppi di partite da fondere")
    if args.dry_run:
        for k, v in duplicates.items():
            print(f"  {k[0]} vs {k[1]} ({k[2]}) — {len(v)} record")
        print("\n(Dry run, nessuna modifica)")
        return 0

    total_odds = 0
    total_deleted = 0
    for key, matches in duplicates.items():
        try:
            n_odds, n_del, _ = merge_group(c, matches)
            total_odds += n_odds
            total_deleted += n_del
        except Exception as e:
            print(f"❌ Errore su {key}: {e}")
            conn.rollback()
            return 1

    conn.commit()
    conn.close()

    print(f"\n✅ Merge completato:")
    print(f"  Quote trasferite: {total_odds}")
    print(f"  Partite eliminate: {total_deleted}")
    print(f"  Gruppi fusi: {len(duplicates)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

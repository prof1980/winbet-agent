#!/usr/bin/env python3
"""WinBet Dashboard v4 — Layout 3 colonne user-friendly.

Colonne:
  Sinistra: lista campionati con conteggio partite + filtri bookmaker
  Centro: partite del campionato selezionato con tutte le quote
  Destra: Surebet rilevate + Sistemi di scommesse (multiple, sistemi integrali)
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).parent.parent / "winbet.db"


# ── DB helpers ────────────────────────────────────────────────────


def load_all(cur: sqlite3.Cursor) -> dict[str, Any]:
    """Carica tutti i dati in un dizionario organizzato."""
    # Matches
    cur.execute("""
        SELECT match_id, home_team, away_team, league_id, match_date, match_time, status
        FROM matches
    """)
    matches_raw = cur.fetchall()

    # Quote per ogni partita
    cur.execute("""
        SELECT match_id, bookmaker_id, market_type, selection_name, odds_value, scraped_at
        FROM odds
    """)
    odds_raw = cur.fetchall()

    # Surebets
    cur.execute("""
        SELECT match_id, selections, profit_percent, total_implied_prob, detected_at
        FROM surebets WHERE status='active' AND profit_percent >= 2.0
        ORDER BY profit_percent DESC LIMIT 25
    """)
    surebets_raw = cur.fetchall()

    # Organizza quote per match
    odds_by_match: dict[str, dict] = defaultdict(
        lambda: {"bookmakers": set(), "markets": set(), "data": {}}
    )
    for mid, bk, mkt, sel, odds, at in odds_raw:
        m = odds_by_match[mid]
        m["bookmakers"].add(bk)
        m["markets"].add(mkt)
        if bk not in m["data"]:
            m["data"][bk] = {}
        if mkt not in m["data"][bk]:
            m["data"][bk][mkt] = {}
        m["data"][bk][mkt][sel] = odds

    # Converti set in sorted list
    for mid, m in odds_by_match.items():
        m["bookmakers"] = sorted(m["bookmakers"])
        m["markets"] = sorted(m["markets"])

    # Matches organizzati
    matches = []
    for mid, home, away, league, date, time, status in matches_raw:
        matches.append({
            "id": mid,
            "home": home,
            "away": away,
            "league": league or "Altro",
            "date": date or "",
            "time": time or "",
            "status": status or "",
            "odds_data": odds_by_match.get(mid, {"bookmakers": [], "markets": [], "data": {}}),
        })

    # Raggruppa per campionato
    leagues = defaultdict(list)
    for m in matches:
        leagues[m["league"]].append(m)

    # Surebets processate
    surebets = []
    for mid, sels_json, profit, margin, dt in surebets_raw:
        try:
            sels = json.loads(sels_json) if sels_json else {}
        except Exception:
            sels = {}
        match_name = next(
            (f"{m['home']} vs {m['away']}" for m in matches if m["id"] == mid),
            mid.replace("_", " ").title(),
        )
        surebets.append({
            "match_id": mid,
            "match_name": match_name,
            "profit": round(profit, 2),
            "margin": round(margin, 4),
            "selections": sels,
        })

    return {
        "matches": matches,
        "leagues": dict(leagues),
        "surebets": surebets,
        "bookmakers": sorted({b for m in matches for b in m["odds_data"]["bookmakers"]}),
    }


def get_db_stats(cur: sqlite3.Cursor) -> dict:
    cur.execute("SELECT COUNT(*) FROM matches")
    total_matches = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM odds")
    total_odds = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM surebets WHERE status='active'")
    total_surebets = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT bookmaker_id) FROM odds")
    n_bk = cur.fetchone()[0]
    cur.execute("SELECT MAX(scraped_at) FROM odds")
    last_upd = cur.fetchone()[0] or "N/A"
    return {
        "matches": total_matches,
        "odds": total_odds,
        "surebets": total_surebets,
        "bookmakers": n_bk or 0,
        "last_update": last_upd,
    }


# ── HTML helpers ──────────────────────────────────────────────────


def esc(s: str) -> str:
    """Escape HTML in modo sicuro."""
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_leagues_html(leagues: dict) -> str:
    """Pannello sinistro: lista campionati con conteggio."""
    items = []
    total = sum(len(m) for m in leagues.values())
    items.append(
        f'<div class="lg-item active" data-league="__ALL__">'
        f'<span class="lg-icon">🌍</span>'
        f'<span class="lg-name">Tutti i campionati</span>'
        f'<span class="lg-count">{total}</span></div>'
    )
    # Ordina per numero partite
    for league, ms in sorted(leagues.items(), key=lambda x: -len(x[1])):
        items.append(
            f'<div class="lg-item" data-league="{esc(league)}">'
            f'<span class="lg-name">{esc(league)}</span>'
            f'<span class="lg-count">{len(ms)}</span></div>'
        )
    return "\n".join(items)


def build_matches_html(matches: list[dict]) -> str:
    """Pannello centrale: partite con tutte le quote per bookmaker."""
    cards = []
    for m in matches:
        mid = esc(m["id"])
        home = esc(m["home"])
        away = esc(m["away"])
        league = esc(m["league"])
        date = esc(m["date"])
        time = esc(m["time"])
        status = esc(m["status"])

        meta = f"{date} {time}".strip()
        if status:
            meta += f" · {status}"

        # Quote aggregate per mercato: {market: {selection: {bookmaker: odds}}}
        markets_data: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
        for bk, mks in m["odds_data"]["data"].items():
            for mkt, sels in mks.items():
                for sel, odds in sels.items():
                    markets_data[mkt][sel][bk] = odds

        # Per ogni mercato costruisci sezione con tutte le quote
        mkt_html = []
        for mkt_name, sels in list(markets_data.items())[:3]:
            # Header mercato
            mkt_html.append(f'<div class="match-mkt">')
            mkt_html.append(f'<div class="mkt-title">{esc(mkt_name)}</div>')

            for sel, bks in list(sels.items())[:3]:
                # Trova la migliore quota
                best_bk = max(bks, key=lambda b: bks[b])
                best_odds = bks[best_bk]

                # Quote di tutti i bookmaker
                all_quotes = []
                for bk in sorted(bks.keys()):
                    odds = bks[bk]
                    is_best = bk == best_bk
                    all_quotes.append(
                        f'<span class="q-cell {("best" if is_best else "")}">'
                        f'<span class="q-bk">{esc(bk)[:10]}</span>'
                        f'<span class="q-val">{odds}</span>'
                        f'</span>'
                    )
                mkt_html.append(
                    f'<div class="mkt-sel">'
                    f'<div class="sel-label">'
                    f'<span class="sel-name">{esc(sel)}</span>'
                    f'<span class="sel-best">max {best_odds} ({esc(best_bk)[:10]})</span>'
                    f'</div>'
                    f'<div class="sel-quotes">{"".join(all_quotes)}</div>'
                    f'</div>'
                )
            mkt_html.append("</div>")

        body_html = "".join(mkt_html) if mkt_html else '<div class="no-odds">Quote non disponibili</div>'
        cards.append(
            f'<div class="match-card" data-league="{league}" data-home="{esc(m["home"].lower())}" data-away="{esc(m["away"].lower())}">'
            f'<div class="match-head">'
            f'<div class="match-teams"><span class="home">{home}</span><span class="vs">vs</span><span class="away">{away}</span></div>'
            f'<div class="match-meta"><span class="lg-tag">{league}</span><span class="date-tag">{meta}</span></div>'
            f'</div>'
            f'<div class="match-body">{body_html}</div>'
            f'</div>'
        )
    return "\n".join(cards) if cards else '<div class="empty"><div class="empty-icon">📭</div>Nessuna partita</div>'


def build_surebets_html(surebets: list[dict]) -> str:
    items = []
    for sb in surebets[:15]:
        combo = sb["selections"]
        # Determina se è dict {outcome: {odds, bookmaker}} o lista di dict
        if isinstance(combo, dict):
            parts = []
            for k, v in combo.items():
                if isinstance(v, dict):
                    odds = v.get("odds", "?")
                    bk = v.get("bookmaker", "?")
                    parts.append(f"{k}@{odds} ({bk})")
                else:
                    parts.append(f"{k}={v}")
            combo_str = " · ".join(parts)
        elif isinstance(combo, list):
            parts = []
            for it in combo:
                if isinstance(it, dict):
                    sel = it.get("selection") or it.get("name", "?")
                    odds = it.get("odds", "?")
                    bk = it.get("bookmaker", "?")
                    parts.append(f"{sel}@{odds} ({bk})")
                else:
                    parts.append(str(it))
            combo_str = " · ".join(parts)
        else:
            combo_str = str(combo)[:120]
        items.append(
            f'<div class="sb-item">'
            f'<div class="sb-name">{esc(sb["match_name"])}</div>'
            f'<div class="sb-combo">{esc(combo_str)}</div>'
            f'<div class="sb-profit">+{sb["profit"]}%</div>'
            f'</div>'
        )
    return "\n".join(items) if items else '<div class="empty-mini">Nessuna surebet</div>'


def build_systems_html(matches: list[dict]) -> dict:
    """Calcola sistemi di scommesse: multipla 3, sistema 3/4, value bet.

    Restituisce un dict con:
      - multipla: lista di selezioni (top 3 value)
      - sistema_3_4: 3 partite con 2 selezioni ciascuna
      - value_bets: selezioni con quota migliore > media +15%
    """
    systems = {"multipla": [], "sistema_3_4": [], "value_bets": []}

    # Estrai tutte le selezioni 1X2 con la migliore quota
    all_sels = []
    for m in matches[:30]:  # limita per performance
        for bk, mks in m["odds_data"]["data"].items():
            for mkt, sels in mks.items():
                if mkt.lower() not in ("1x2", "h2h"):
                    continue
                for sel, odds in sels.items():
                    if odds > 1.1:
                        all_sels.append({
                            "match": f"{m['home']} vs {m['away']}",
                            "match_id": m["id"],
                            "market": mkt,
                            "selection": sel,
                            "odds": odds,
                            "bookmaker": bk,
                        })

    if not all_sels:
        return systems

    # 1. Multipla: top 3 selezioni con quote più alte
    by_match: dict[str, list] = defaultdict(list)
    for s in all_sels:
        by_match[s["match_id"]].append(s)

    # Prendi la quota migliore per ogni match
    best_per_match = {}
    for mid, sels in by_match.items():
        best = max(sels, key=lambda x: x["odds"])
        best_per_match[mid] = best

    # Top 3 partite con quote interessanti (non troppo basse)
    sorted_matches = sorted(
        best_per_match.values(),
        key=lambda x: -x["odds"],
    )
    multipla = sorted_matches[:3]
    systems["multipla"] = multipla
    if multipla:
        systems["multipla_total_odds"] = round(
            __import__("math").prod(s["odds"] for s in multipla), 2
        )

    # 2. Sistema 3/4: 3 partite con 2 selezioni ciascuna (6 in totale)
    # Prendi le 3 partite con più selezioni alternative
    rich_matches = sorted(
        by_match.values(), key=lambda v: -len(v)
    )[:3]

    sistema = []
    for ms in rich_matches:
        # Prendi le 2 quote migliori
        top2 = sorted(ms, key=lambda x: -x["odds"])[:2]
        for sel in top2:
            sistema.append(sel)
    systems["sistema_3_4"] = sistema
    if sistema:
        systems["sistema_3_4_odds"] = round(
            __import__("math").prod(s["odds"] for s in sistema), 2
        )

    # 3. Value bet: selezioni con quota superiore alla media del 15%
    by_sel: dict[tuple, list] = defaultdict(list)
    for s in all_sels:
        key = (s["market"], s["selection"])
        by_sel[key].append(s)

    value_bets = []
    for key, sels in by_sel.items():
        avg = sum(s["odds"] for s in sels) / len(sels)
        max_odds = max(s["odds"] for s in sels)
        if max_odds > avg * 1.15:
            best = max(sels, key=lambda x: x["odds"])
            value_bets.append({
                **best,
                "avg": round(avg, 2),
                "edge": round((best["odds"] - avg) / avg * 100, 1),
            })
    value_bets = sorted(value_bets, key=lambda x: -x["edge"])[:5]
    systems["value_bets"] = value_bets

    return systems


def render_systems_html(systems: dict) -> str:
    """Rende l'HTML per i sistemi di scommesse calcolati."""
    parts = []

    # Multipla
    if systems.get("multipla"):
        items = []
        for s in systems["multipla"]:
            items.append(
                f'<div class="sys-row">'
                f'<span class="sys-match">{esc(s["match"])[:30]}</span>'
                f'<span class="sys-sel">{esc(s["selection"])}</span>'
                f'<span class="sys-odds">{s["odds"]}</span>'
                f'</div>'
            )
        total = systems.get("multipla_total_odds", 0)
        parts.append(
            f'<div class="sys-block">'
            f'<div class="sys-title">🎯 Multipla 3 (Quote {total})</div>'
            f'{"".join(items)}'
            f'<div class="sys-note">Vincita potenziale: €10 → €{round(total*10, 2)}</div>'
            f'</div>'
        )

    # Sistema 3/4
    if systems.get("sistema_3_4"):
        items = []
        for s in systems["sistema_3_4"]:
            items.append(
                f'<div class="sys-row">'
                f'<span class="sys-match">{esc(s["match"])[:24]}</span>'
                f'<span class="sys-sel">{esc(s["selection"])}</span>'
                f'<span class="sys-odds">{s["odds"]}</span>'
                f'</div>'
            )
        total = systems.get("sistema_3_4_odds", 0)
        parts.append(
            f'<div class="sys-block">'
            f'<div class="sys-title">🔀 Sistema 3/4 (6 selezioni, quote totali {total})</div>'
            f'{"".join(items)}'
            f'<div class="sys-note">Vinci anche con 2 partite corrette su 3</div>'
            f'</div>'
        )

    # Value bet
    if systems.get("value_bets"):
        items = []
        for s in systems["value_bets"]:
            items.append(
                f'<div class="sys-row">'
                f'<span class="sys-match">{esc(s["match"])[:30]}</span>'
                f'<span class="sys-sel">{esc(s["selection"])}</span>'
                f'<span class="sys-odds">{s["odds"]}</span>'
                f'<span class="sys-edge">+{s["edge"]}%</span>'
                f'</div>'
            )
        parts.append(
            f'<div class="sys-block">'
            f'<div class="sys-title">💎 Value Bets (quota sopra media)</div>'
            f'{"".join(items)}'
            f'</div>'
        )

    return "\n".join(parts) if parts else '<div class="empty-mini">Sistemi non disponibili</div>'


# ── Main generator ────────────────────────────────────────────────


def generate(db_path: str, output_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    stats = get_db_stats(cur)
    data = load_all(cur)
    matches = data["matches"]
    leagues = data["leagues"]
    surebets = data["surebets"]
    bookmakers = data["bookmakers"]

    # Costruisci HTML per le tre colonne
    leagues_html = build_leagues_html(leagues)
    matches_html = build_matches_html(matches)
    surebets_html = build_surebets_html(surebets)
    systems = build_systems_html(matches)
    systems_html = render_systems_html(systems)

    # Filtri bookmaker
    bk_filters = "\n".join(
        f'<label class="bk-filter"><input type="checkbox" value="{esc(bk)}" checked onchange="applyBkFilter()"> {esc(bk)}</label>'
        for bk in bookmakers
    )

    # JSON embeddato per il client-side
    matches_json = json.dumps(
        [
            {
                "id": m["id"],
                "home": m["home"],
                "away": m["away"],
                "league": m["league"],
                "date": m["date"],
                "time": m["time"],
                "odds_data": {
                    k: v for k, v in m["odds_data"].items() if k != "data"
                }
                | {"data": {
                    bk: {
                        mkt: {sel: odds for sel, odds in sels.items()}
                        for mkt, sels in mks.items()
                    }
                    for bk, mks in m["odds_data"]["data"].items()
                }},
            }
            for m in matches
        ],
        ensure_ascii=False,
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="1800">
<title>WinBet Dashboard v4</title>
<style>
:root{{
  --bg:#0b1121;--card:#151e32;--card-h:#1a2642;--text:#e2e8f0;--muted:#94a3b8;
  --accent:#38bdf8;--accent2:#818cf8;--danger:#f87171;--success:#34d399;--warn:#fbbf24;
  --border:#1e293b;--hover:#1a2642
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;min-height:100vh}}
a{{color:var(--accent);text-decoration:none}}
button{{font-family:inherit}}

/* Header */
header{{
  background:linear-gradient(135deg,#0b1121,#1a2642);
  padding:14px 20px;border-bottom:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px
}}
header h1{{font-size:1.5em;color:var(--accent);display:flex;align-items:center;gap:10px}}
header .sub{{color:var(--muted);font-size:0.8em}}
.stats{{display:flex;gap:14px;flex-wrap:wrap}}
.stat{{background:var(--card);padding:6px 12px;border-radius:8px;font-size:0.8em;border:1px solid var(--border)}}
.stat .v{{color:var(--accent);font-weight:700}}
.stat .l{{color:var(--muted);margin-right:4px}}

/* Layout 3 colonne */
.main{{
  display:grid;grid-template-columns:260px 1fr 320px;gap:14px;padding:14px;
  height:calc(100vh - 70px)
}}
.col{{
  background:var(--card);border-radius:12px;border:1px solid var(--border);
  overflow:hidden;display:flex;flex-direction:column
}}
.col-header{{
  padding:12px 14px;background:var(--card-h);border-bottom:1px solid var(--border);
  font-weight:600;display:flex;align-items:center;justify-content:space-between;
  position:sticky;top:0;z-index:5
}}
.col-header h2{{font-size:0.95em;display:flex;align-items:center;gap:8px}}
.col-body{{overflow-y:auto;flex:1;padding:8px}}

/* Colonna sinistra: campionati */
.lg-item{{
  display:flex;align-items:center;justify-content:space-between;
  padding:9px 12px;border-radius:7px;cursor:pointer;
  font-size:0.88em;transition:all .15s;border:1px solid transparent
}}
.lg-item:hover{{background:var(--hover);border-color:var(--border)}}
.lg-item.active{{background:rgba(56,189,248,0.12);border-color:var(--accent);color:var(--accent)}}
.lg-name{{flex:1;font-weight:500}}
.lg-count{{
  background:var(--card-h);color:var(--muted);padding:2px 8px;border-radius:10px;
  font-size:0.85em;font-weight:600;min-width:28px;text-align:center
}}
.lg-item.active .lg-count{{background:var(--accent);color:#0f172a}}
.bk-filter{{
  display:flex;align-items:center;gap:6px;padding:5px 10px;
  font-size:0.8em;color:var(--muted);cursor:pointer;border-radius:5px
}}
.bk-filter:hover{{color:var(--text);background:var(--hover)}}
.bk-filter input{{accent-color:var(--accent);cursor:pointer}}
.bk-filters{{padding:6px;border-top:1px solid var(--border);max-height:140px;overflow-y:auto}}
.bk-filters h3{{font-size:0.7em;text-transform:uppercase;color:var(--muted);padding:8px 10px 4px;letter-spacing:.5px}}

/* Colonna centrale: partite */
.match-card{{
  background:var(--card-h);border-radius:9px;border:1px solid var(--border);
  margin-bottom:10px;overflow:hidden;transition:border-color .15s
}}
.match-card:hover{{border-color:var(--accent2)}}
.match-head{{padding:10px 14px;border-bottom:1px solid var(--border);background:rgba(15,23,42,0.3)}}
.match-teams{{font-size:1.02em;font-weight:700;margin-bottom:4px}}
.match-teams .vs{{color:var(--muted);margin:0 6px;font-weight:400}}
.match-teams .home{{color:var(--accent)}}
.match-teams .away{{color:var(--accent2)}}
.match-meta{{display:flex;gap:8px;flex-wrap:wrap;font-size:0.75em;color:var(--muted);align-items:center}}
.lg-tag{{background:rgba(129,140,248,0.12);color:var(--accent2);padding:1px 6px;border-radius:3px}}
.date-tag{{font-size:0.9em}}
.match-body{{padding:10px 14px}}
.match-mkt{{margin-bottom:8px}}
.mkt-title{{
  font-size:0.7em;color:var(--accent);text-transform:uppercase;
  letter-spacing:.5px;font-weight:700;margin-bottom:6px
}}
.mkt-sel{{
  background:rgba(15,23,42,0.4);border-radius:6px;padding:7px 10px;margin-bottom:4px;
  display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap
}}
.sel-label{{display:flex;flex-direction:column;gap:2px;min-width:100px}}
.sel-name{{font-weight:600;font-size:0.92em}}
.sel-best{{color:var(--success);font-size:0.75em;font-weight:600}}
.sel-quotes{{display:flex;gap:4px;flex-wrap:wrap}}
.q-cell{{
  background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.18);
  border-radius:5px;padding:3px 7px;font-size:0.78em;display:flex;flex-direction:column;align-items:center;min-width:60px
}}
.q-cell.best{{background:rgba(52,211,153,0.15);border-color:rgba(52,211,153,0.5)}}
.q-bk{{color:var(--muted);font-size:0.85em}}
.q-val{{color:var(--text);font-weight:700}}
.q-cell.best .q-val{{color:var(--success)}}
.no-odds{{color:var(--muted);font-size:0.85em;padding:10px;text-align:center}}
.empty{{text-align:center;padding:40px 20px;color:var(--muted)}}
.empty-icon{{font-size:2.5em;margin-bottom:8px}}
.empty-mini{{text-align:center;padding:14px;color:var(--muted);font-size:0.85em;font-style:italic}}

/* Colonna destra: surebet + sistemi */
.sb-item{{
  background:rgba(248,113,113,0.08);border:1px solid rgba(248,113,113,0.25);
  border-radius:7px;padding:9px 11px;margin-bottom:7px;
  display:flex;flex-direction:column;gap:3px
}}
.sb-name{{font-weight:600;font-size:0.9em}}
.sb-combo{{color:var(--muted);font-size:0.75em;word-break:break-all}}
.sb-profit{{
  background:linear-gradient(135deg,#34d399,#10b981);color:#fff;
  padding:3px 9px;border-radius:5px;font-weight:700;font-size:0.85em;align-self:flex-start;margin-top:3px
}}
.sys-block{{
  background:rgba(129,140,248,0.06);border:1px solid rgba(129,140,248,0.2);
  border-radius:8px;padding:10px 12px;margin-bottom:10px
}}
.sys-title{{
  font-size:0.82em;font-weight:700;color:var(--accent2);
  margin-bottom:7px;display:flex;align-items:center;gap:6px
}}
.sys-row{{
  display:flex;justify-content:space-between;align-items:center;
  padding:4px 0;border-bottom:1px dashed rgba(129,140,248,0.15);font-size:0.78em;gap:6px
}}
.sys-row:last-child{{border-bottom:none}}
.sys-match{{color:var(--text);min-width:100px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sys-sel{{color:var(--muted);font-weight:600;min-width:30px}}
.sys-odds{{color:var(--accent);font-weight:700;min-width:35px;text-align:right}}
.sys-edge{{
  background:var(--warn);color:#0f172a;padding:1px 5px;border-radius:3px;
  font-size:0.9em;font-weight:700;min-width:42px;text-align:center
}}
.sys-note{{
  margin-top:7px;padding-top:6px;border-top:1px dashed rgba(129,140,248,0.15);
  font-size:0.7em;color:var(--muted);font-style:italic
}}

.section-title{{
  font-size:0.78em;text-transform:uppercase;color:var(--muted);
  padding:10px 4px 6px;letter-spacing:.5px;font-weight:700
}}

/* Search */
.search-box{{padding:6px 10px;border-bottom:1px solid var(--border)}}
.search-box input{{
  width:100%;padding:6px 10px;border-radius:5px;
  border:1px solid var(--border);background:#0f172a;color:var(--text);font-size:0.85em
}}
.search-box input:focus{{outline:none;border-color:var(--accent)}}

/* Scrollbar */
.col-body::-webkit-scrollbar{{width:6px}}
.col-body::-webkit-scrollbar-track{{background:transparent}}
.col-body::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px}}
.col-body::-webkit-scrollbar-thumb:hover{{background:var(--hover)}}

/* Mobile */
@media(max-width:1100px){{
  .main{{grid-template-columns:1fr;height:auto}}
  .col{{max-height:500px}}
}}
</style>
</head>
<body>
<header>
  <div>
    <h1>⚽ WinBet</h1>
    <div class="sub">Quote live · Aggiornato: {timestamp}</div>
  </div>
  <div class="stats">
    <div class="stat"><span class="l">Partite</span><span class="v">{stats['matches']}</span></div>
    <div class="stat"><span class="l">Quote</span><span class="v">{stats['odds']}</span></div>
    <div class="stat"><span class="l">Surebet</span><span class="v">{len(surebets)}</span></div>
    <div class="stat"><span class="l">Bookmaker</span><span class="v">{stats['bookmakers']}</span></div>
  </div>
</header>

<div class="main">
  <!-- COLONNA SINISTRA: CAMPIONATI -->
  <div class="col">
    <div class="col-header">
      <h2>🏆 Campionati</h2>
      <span style="font-size:.78em;color:var(--muted)">{len(leagues)} attivi</span>
    </div>
    <div class="search-box">
      <input type="text" id="search-league" placeholder="🔍 Cerca campionato..." oninput="filterLeagues()">
    </div>
    <div class="col-body" id="leagues-list">
      {leagues_html}
    </div>
    <div class="bk-filters">
      <h3>📡 Bookmaker</h3>
      {bk_filters}
    </div>
  </div>

  <!-- COLONNA CENTRALE: PARTITE -->
  <div class="col">
    <div class="col-header">
      <h2>📋 Partite <span id="league-title" style="color:var(--accent);font-weight:400"></span></h2>
      <span id="matches-count" style="font-size:.78em;color:var(--muted)">{len(matches)} totali</span>
    </div>
    <div class="col-body" id="matches-list">
      {matches_html}
    </div>
  </div>

  <!-- COLONNA DESTRA: SUREBET + SISTEMI -->
  <div class="col">
    <div class="col-header">
      <h2>📊 Analisi</h2>
    </div>
    <div class="col-body">
      <div class="section-title">🚨 Surebet Rilevate</div>
      {surebets_html}

      <div class="section-title">🎰 Sistemi di Scommesse</div>
      {systems_html}
    </div>
  </div>
</div>

<script>
const MATCHES = {matches_json};
let currentLeague = '__ALL__';
let activeBookmakers = new Set(MATCHES.length ? Object.keys(MATCHES[0].odds_data.data) : []);

// Click su campionato
document.querySelectorAll('.lg-item').forEach(item => {{
  item.addEventListener('click', () => {{
    document.querySelectorAll('.lg-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
    currentLeague = item.dataset.league;
    document.getElementById('league-title').textContent =
      currentLeague === '__ALL__' ? '' : '· ' + currentLeague;
    renderMatches();
  }});
}});

function filterLeagues() {{
  const q = document.getElementById('search-league').value.toLowerCase();
  document.querySelectorAll('.lg-item').forEach(el => {{
    const name = el.querySelector('.lg-name').textContent.toLowerCase();
    el.style.display = name.includes(q) ? '' : 'none';
  }});
}}

function applyBkFilter() {{
  activeBookmakers = new Set();
  document.querySelectorAll('.bk-filter input').forEach(cb => {{
    if (cb.checked) activeBookmakers.add(cb.value);
  }});
  renderMatches();
}}

function renderMatches() {{
  const container = document.getElementById('matches-list');
  const filtered = MATCHES.filter(m => {{
    if (currentLeague !== '__ALL__' && m.league !== currentLeague) return false;
    return true;
  }});
  document.getElementById('matches-count').textContent = filtered.length + ' partite';

  if (!filtered.length) {{
    container.innerHTML = '<div class="empty"><div class="empty-icon">🔍</div>Nessuna partita in questo campionato</div>';
    return;
  }}

  container.innerHTML = filtered.map(m => {{
    // Costruisci quote aggregate
    const markets = {{}};
    for (const bk of Object.keys(m.odds_data.data || {{}})) {{
      if (!activeBookmakers.has(bk)) continue;
      for (const [mkt, sels] of Object.entries(m.odds_data.data[bk])) {{
        if (!markets[mkt]) markets[mkt] = {{}};
        for (const [sel, odds] of Object.entries(sels)) {{
          if (!markets[mkt][sel]) markets[mkt][sel] = {{}};
          markets[mkt][sel][bk] = odds;
        }}
      }}
    }}
    const mktKeys = Object.keys(markets).slice(0, 3);
    const mktHtml = mktKeys.length ? mktKeys.map(mk => {{
      const sels = markets[mk];
      return `<div class="match-mkt">
        <div class="mkt-title">${{mk}}</div>
        ${{Object.entries(sels).slice(0, 3).map(([sel, bks]) => {{
          const entries = Object.entries(bks);
          const bestBk = entries.reduce((a, b) => b[1] > a[1] ? b : a);
          return `<div class="mkt-sel">
            <div class="sel-label">
              <span class="sel-name">${{sel}}</span>
              <span class="sel-best">max ${{bestBk[1]}} (${{bestBk[0].slice(0,10)}})</span>
            </div>
            <div class="sel-quotes">
              ${{entries.sort().map(([bk, odds]) =>
                `<span class="q-cell ${{bk === bestBk[0] ? 'best' : ''}}">
                  <span class="q-bk">${{bk.slice(0,10)}}</span>
                  <span class="q-val">${{odds}}</span>
                </span>`).join('')}}
            </div>
          </div>`;
        }}).join('')}}
      </div>`;
    }}).join('') : '<div class="no-odds">Nessuna quota per i bookmaker selezionati</div>';

    const meta = [m.date, m.time].filter(Boolean).join(' ');
    return `<div class="match-card">
      <div class="match-head">
        <div class="match-teams">
          <span class="home">${{m.home}}</span>
          <span class="vs">vs</span>
          <span class="away">${{m.away}}</span>
        </div>
        <div class="match-meta">
          <span class="lg-tag">${{m.league}}</span>
          <span class="date-tag">${{meta}}</span>
        </div>
      </div>
      <div class="match-body">${{mktHtml}}</div>
    </div>`;
  }}).join('');
}}
</script>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    conn.close()
    print(f"✅ Dashboard v4 generata: {output_path}")
    print(f"   Layout 3 colonne | {len(leagues)} campionati | {len(matches)} partite | {len(surebets)} surebet")
    print(f"   Sistemi: {len(systems.get('multipla',[]))} multipla, {len(systems.get('sistema_3_4',[]))} selezioni 3/4, {len(systems.get('value_bets',[]))} value bet")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default="/mnt/c/Users/angel/WinBet/dashboard.html")
    args = parser.parse_args()
    generate(args.db, args.output)


if __name__ == "__main__":
    main()

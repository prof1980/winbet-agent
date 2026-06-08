#!/usr/bin/env python3
"""WinBet Dashboard Generator v3 — Dashboard professionale con 6 migliorie:
1. Nomi leggibili nelle surebets
2. Trend quote con variazioni percentuali
3. Tabella comparativa quote x bookmaker
4. Filtraggio profitto sicuro ≥2%
5. Alert su variazioni quote >10%
6. Esportazione CSV integrata
"""
import argparse
import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "winbet.db"

# ── Helpers ──────────────────────────────────────────────────────────


def get_db_stats(cur):
    cur.execute("SELECT COUNT(*) FROM matches")
    total_matches = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM odds")
    total_odds = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM surebets WHERE status='active'")
    total_surebets = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT bookmaker_id) FROM odds")
    n_bookmakers = cur.fetchone()[0]
    cur.execute("SELECT MAX(scraped_at) FROM odds")
    last_update = cur.fetchone()[0] or "N/A"
    return {
        "matches": total_matches,
        "odds": total_odds,
        "surebets": total_surebets,
        "bookmakers": n_bookmakers or 3,
        "last_update": last_update,
    }


def get_match_name(cur, match_id: str) -> str:
    """Restituisce 'Home vs Away' dal match_id."""
    cur.execute(
        "SELECT home_team, away_team FROM matches WHERE match_id=?", (match_id,)
    )
    row = cur.fetchone()
    if row and row[0] and row[1]:
        return f"{row[0]} vs {row[1]}"
    return match_id.replace("_", " ").title()


def get_surebets(cur, min_profit: float = 2.0) -> list[dict]:
    cur.execute(
        """
        SELECT match_id, selections, profit_percent, total_implied_prob, detected_at
        FROM surebets
        WHERE status='active' AND profit_percent >= ?
        ORDER BY profit_percent DESC
        LIMIT 30
        """,
        (min_profit,),
    )
    result = []
    for mid, sels_json, profit, margin, dt in cur.fetchall():
        try:
            sels_parsed = json.loads(sels_json) if sels_json else {}
        except Exception:
            sels_parsed = {}
        result.append(
            {
                "match_id": mid,
                "match_name": get_match_name(cur, mid),
                "profit": round(profit, 2),
                "margin": round(margin, 4),
                "detected_at": dt[:16] if dt else "",
                "selections": sels_parsed,
            }
        )
    return result


def get_odds_changes(cur, match_id: str, threshold: float = 0.10) -> dict:
    """Ritorna variazioni percentuali per mercato/selezione.
    threshold = 0.10 → alert su variazioni >10%.
    """
    # Ultima quota per ogni (market, selection, bookmaker)
    cur.execute(
        """
        SELECT market_type, selection_name, odds_value, bookmaker_id
        FROM odds WHERE match_id = ?
        """,
        (match_id,),
    )
    current = {(r[0], r[1], r[3]): r[2] for r in cur.fetchall()}

    # Penultima quota dalla history
    cur.execute(
        """
        SELECT market_type, selection_name, odds_value, bookmaker_id, recorded_at
        FROM odds_history
        WHERE match_id = ?
        ORDER BY recorded_at DESC
        """,
        (match_id,),
    )
    previous = {}
    for mkt, sel, odds, bk, ts in cur.fetchall():
        key = (mkt, sel, bk)
        if key not in previous:
            previous[key] = odds  # prima occorrenza = più recente precedente

    changes = {}
    for key, curr_val in current.items():
        mkt, sel, bk = key
        if key in previous:
            prev_val = previous[key]
            if prev_val > 0:
                delta = (curr_val - prev_val) / prev_val
                if abs(delta) >= threshold:
                    changes[f"{bk}|{mkt}|{sel}"] = {
                        "prev": prev_val,
                        "curr": curr_val,
                        "delta_pct": round(delta * 100, 1),
                        "direction": "up" if delta > 0 else "down",
                    }
    return changes


def get_matches(cur, limit: int = 100):
    """Restituisce partite con tutte le quote per tabella comparativa."""
    cur.execute(
        """
        SELECT match_id, home_team, away_team, league_id, match_date, match_time, status
        FROM matches
        ORDER BY match_date ASC, match_time ASC
        LIMIT ?
        """,
        (limit,),
    )
    matches = []
    for mid, home, away, league, date, time, status in cur.fetchall():
        cur.execute(
            """
            SELECT bookmaker_id, market_type, selection_name, odds_value
            FROM odds WHERE match_id = ?
            ORDER BY bookmaker_id, market_type, selection_name
            """,
            (mid,),
        )
        raw = cur.fetchall()
        # struttura: {bookmaker: {market: {selection: odds}}}
        data = {}
        bookmakers = set()
        markets = set()
        for bk, mkt, sel, odds in raw:
            bookmakers.add(bk)
            markets.add(mkt)
            if bk not in data:
                data[bk] = {}
            if mkt not in data[bk]:
                data[bk][mkt] = {}
            data[bk][mkt][sel] = odds

        # variazioni significative
        changes = get_odds_changes(cur, mid)

        matches.append(
            {
                "id": mid,
                "home": home,
                "away": away,
                "league": league,
                "date": date,
                "time": time,
                "status": status,
                "data": data,
                "bookmakers": sorted(bookmakers),
                "markets": sorted(markets),
                "changes": changes,
            }
        )
    return matches


def get_leagues(cur):
    cur.execute(
        "SELECT DISTINCT league_id FROM matches WHERE league_id IS NOT NULL AND league_id != '' ORDER BY league_id"
    )
    return [r[0] for r in cur.fetchall()]


def get_all_bookmakers(cur):
    cur.execute(
        "SELECT DISTINCT bookmaker_id FROM odds WHERE bookmaker_id IS NOT NULL ORDER BY bookmaker_id"
    )
    return [r[0] for r in cur.fetchall()]


# ── CSV Export ───────────────────────────────────────────────────────


def csv_export_data(cur) -> str:
    """Genera CSV con tutte le quote per download."""
    cur.execute(
        """
        SELECT o.match_id, m.home_team, m.away_team, m.league_id,
               o.bookmaker_id, o.market_type, o.selection_name,
               o.odds_value, o.scraped_at
        FROM odds o
        JOIN matches m ON o.match_id = m.match_id
        ORDER BY m.match_date, m.match_time, o.bookmaker_id, o.market_type
        """
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["match_id", "home", "away", "league", "bookmaker", "market", "selection", "odds", "scraped_at"]
    )
    for row in cur.fetchall():
        writer.writerow(row)
    return buf.getvalue()


# ── HTML Generator ───────────────────────────────────────────────────


def generate(db_path: str, output_path: str, limit: int = 100, min_profit: float = 2.0):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    stats = get_db_stats(cur)
    surebets = get_surebets(cur, min_profit)
    matches = get_matches(cur, limit)
    leagues = get_leagues(cur)
    all_bookmakers = get_all_bookmakers(cur)

    # ── CSV embedded ──
    csv_data = csv_export_data(cur)
    csv_b64 = (
        "data:text/csv;charset=utf-8," + csv_data.replace("\n", "%0A").replace(",", "%2C")
    )

    # ── Surebets HTML ──
    sb_html = ""
    if surebets:
        srows = ""
        for sb in surebets:
            combo = sb.get("selections", {})
            if isinstance(combo, dict):
                combo_str = " | ".join(
                    f"{k}@{v.get('odds', '?')} ({v.get('bookmaker', '?')})"
                    for k, v in combo.items()
                )
            elif isinstance(combo, list):
                combo_str = " | ".join(str(x) for x in combo[:3])
            else:
                combo_str = str(combo)[:120]
            srows += f"""
<div class="sb-row">
  <div class="sb-info">
    <div class="sb-match">{sb['match_name']}</div>
    <div class="sb-details">{combo_str}</div>
  </div>
  <div class="sb-badge">+{sb['profit']}%</div>
</div>"""
        sb_html = f"""
<div class="panel danger" id="surebets-panel">
  <div class="panel-header">
    <span class="panel-icon">🚨</span>
    <span>Surebet Rilevate <span class="badge">{len(surebets)}</span></span>
  </div>
  <div class="panel-body">{srows}</div>
</div>"""

    # ── Filtri HTML ──
    league_opts = "\n".join(f'<option value="{l}">{l}</option>' for l in leagues[:30])
    bk_opts = "\n".join(f'<option value="{b}">{b}</option>' for b in all_bookmakers[:20])

    # ── Matches + Tabella Comparativa ──
    matches_html = ""
    comparison_rows = []
    for m in matches:
        mid = m["id"]
        home = m["home"]
        away = m["away"]
        league = m["league"]
        date = m["date"]
        time = m["time"]
        meta = f"{league} — {date} {time}".strip(" —")

        # mercati disponibili
        markets_available = m["markets"]
        bookmakers_available = m["bookmakers"]

        # Card mercati (versione compatta)
        mkts_html = ""
        for mkt in markets_available[:4]:
            sel_html = ""
            for bk in bookmakers_available[:4]:
                if mkt in m["data"].get(bk, {}):
                    for sel, odds in list(m["data"][bk][mkt].items())[:4]:
                        # variazione?
                        ch_key = f"{bk}|{mkt}|{sel}"
                        ch = m["changes"].get(ch_key)
                        ch_badge = ""
                        if ch:
                            arrow = "📈" if ch["direction"] == "up" else "📉"
                            ch_badge = f'<span class="var-badge {ch["direction"]}">{arrow} {ch["delta_pct"]}</span>'
                        sel_html += f'<span class="sel"><span class="sel-n">{sel}</span><span class="sel-o">{odds}</span><span class="sel-bk">{bk[:10]}</span>{ch_badge}</span>'
            mkts_html += f'<div class="mkt-block"><div class="mkt-title">{mkt}</div><div class="sel-wrap">{sel_html}</div></div>'

        # Alert variazioni
        changes_html = ""
        if m["changes"]:
            up = sum(1 for c in m["changes"].values() if c["direction"] == "up")
            down = sum(1 for c in m["changes"].values() if c["direction"] == "down")
            changes_html = f'<div class="changes-bar"><span class="ch-up">📈 {up}</span><span class="ch-down">📉 {down}</span></div>'

        matches_html += f"""
<div class="match-card" data-league="{league}" data-teams="{home.lower()} {away.lower()}">
  <div class="match-header">
    <div class="match-teams"><span class="home">{home}</span> <span class="vs">vs</span> <span class="away">{away}</span></div>
    <div class="match-meta"><span class="league-tag">{league}</span><span class="date">{meta}</span>{changes_html}</div>
  </div>
  <div class="match-markets">{mkts_html}</div>
</div>"""

        # Tabella comparativa
        for mkt in markets_available[:3]:
            row = {
                "match": f"{home} vs {away}",
                "market": mkt,
                "league": league,
            }
            for bk in bookmakers_available[:6]:
                sels = m["data"].get(bk, {}).get(mkt, {})
                row[bk] = " / ".join(f"{s}:{o}" for s, o in list(sels.items())[:3])
            comparison_rows.append(row)

    # ── Tabella Comparativa HTML ──
    # Prendi le colonne dai dati
    if comparison_rows:
        all_keys = set()
        for r in comparison_rows:
            all_keys.update(r.keys())
        cols = ["match", "market", "league"] + sorted(
            [k for k in all_keys if k not in ("match", "market", "league")]
        )
        thead = "".join(f"<th>{c}</th>" for c in cols)
        tbody = ""
        for r in comparison_rows[:50]:
            tbody += "<tr>" + "".join(f"<td>{r.get(c, '-')}</td>" for c in cols) + "</tr>"
        comp_table = f"""
<div class="panel" style="margin-top:20px;overflow-x:auto">
  <div class="panel-header"><span class="panel-icon">📊</span>Tabella Comparativa Quote</div>
  <div class="panel-body" style="padding:0">
    <table class="comp-table">
      <thead><tr>{thead}</tr></thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
</div>"""
    else:
        comp_table = ""

    # ── Trend Quote globali (ultime 10 variazioni) ──
    cur.execute(
        """
        SELECT o.match_id, m.home_team, m.away_team, o.market_type,
               o.selection_name, o.odds_value, o.bookmaker_id, o.scraped_at
        FROM odds o
        JOIN matches m ON o.match_id = m.match_id
        WHERE o.scraped_at > datetime('now', '-1 hour')
        ORDER BY o.scraped_at DESC
        LIMIT 30
        """
    )
    recent_changes = []
    for row in cur.fetchall():
        recent_changes.append(
            {
                "match": f"{row[1]} vs {row[2]}",
                "market": row[3],
                "sel": row[4],
                "odds": row[5],
                "bk": row[6],
                "time": row[7][11:16] if row[7] else "",
            }
        )

    trend_html = ""
    if recent_changes:
        trs = ""
        for rc in recent_changes[:15]:
            trs += f"""
<div class="trend-row">
  <span class="trend-match">{rc['match'][:28]}</span>
  <span class="trend-mkt">{rc['market']}</span>
  <span class="trend-sel">{rc['sel']}</span>
  <span class="trend-odds">{rc['odds']}</span>
  <span class="trend-bk">{rc['bk'][:10]}</span>
  <span class="trend-time">{rc['time']}</span>
</div>"""
        trend_html = f"""
<div class="panel" style="margin-top:20px">
  <div class="panel-header"><span class="panel-icon">📈</span>Ultimi Aggiornamenti (ultima ora)</div>
  <div class="panel-body">{trs}</div>
</div>"""

    conn.close()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Template HTML ──
    html = f"""<!DOCTYPE html>
<html lang="it"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="1800">
<title>WinBet Dashboard v3</title>
<style>
:root{{--bg:#0b1121;--card:#151e32;--card-h:#1a2642;--text:#e2e8f0;--muted:#94a3b8;
       --accent:#38bdf8;--accent2:#818cf8;--danger:#f87171;--success:#34d399;--warn:#fbbf24}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.5}}
.container{{max-width:1700px;margin:0 auto;padding:20px}}
header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:15px;border-bottom:1px solid #1e293b;flex-wrap:wrap;gap:10px}}
header h1{{margin:0;font-size:1.7em;color:var(--accent);display:flex;align-items:center;gap:10px}}
.sub{{color:var(--muted);font-size:0.82em}}
.actions{{display:flex;gap:10px;align-items:center}}
.btn{{padding:8px 16px;border-radius:8px;border:1px solid var(--accent);background:rgba(56,189,248,0.1);color:var(--accent);font-size:0.85em;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px;transition:all .2s}}
.btn:hover{{background:rgba(56,189,248,0.25)}}
.btn-success{{border-color:var(--success);color:var(--success);background:rgba(52,211,153,0.1)}}
.btn-success:hover{{background:rgba(52,211,153,0.2)}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:20px}}
.stat-card{{background:linear-gradient(145deg,var(--card),var(--card-h));border-radius:10px;padding:14px;text-align:center;border:1px solid #1e293b;transition:transform .2s}}
.stat-card:hover{{transform:translateY(-2px);border-color:var(--accent)}}
.stat-card .n{{font-size:1.7em;font-weight:700;color:var(--accent)}}
.stat-card .l{{font-size:0.75em;color:var(--muted);margin-top:3px;text-transform:uppercase;letter-spacing:.5px}}
.main-layout{{display:grid;grid-template-columns:240px 1fr;gap:16px}}
.sidebar{{display:flex;flex-direction:column;gap:14px;position:sticky;top:20px;align-self:start}}
.panel{{background:var(--card);border-radius:12px;border:1px solid #1e293b;overflow:hidden}}
.panel-header{{padding:12px 14px;font-weight:600;border-bottom:1px solid #1e293b;display:flex;align-items:center;gap:8px;background:var(--card-h)}}
.panel-icon{{font-size:1.1em}}
.panel-body{{padding:12px 14px}}
.panel.danger{{border-color:rgba(248,113,113,0.35)}}
.panel.danger .panel-header{{color:var(--danger);background:rgba(248,113,113,0.08)}}
.filter-group{{margin-bottom:10px}}
.filter-group label{{display:block;font-size:.75em;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}}
.filter-group input,.filter-group select{{width:100%;padding:7px 9px;border-radius:6px;border:1px solid #334155;background:#0f172a;color:var(--text);font-size:.88em}}
.filter-group input:focus,.filter-group select:focus{{outline:none;border-color:var(--accent)}}
.badge{{display:inline-flex;align-items:center;justify-content:center;background:var(--accent);color:#0f172a;font-size:.72em;font-weight:700;padding:2px 7px;border-radius:12px;margin-left:4px}}
.sb-row{{display:flex;justify-content:space-between;align-items:center;padding:9px 11px;border-bottom:1px solid #1e293b;gap:10px}}
.sb-row:last-child{{border-bottom:none}}
.sb-match{{font-weight:600;font-size:.88em}}
.sb-details{{font-size:.75em;color:var(--muted);margin-top:2px;word-break:break-all}}
.sb-badge{{padding:3px 10px;border-radius:6px;font-weight:700;font-size:.82em;white-space:nowrap;background:linear-gradient(135deg,#34d399,#10b981);color:#fff}}
.best-row{{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px dashed #1e293b;font-size:.83em}}
.best-row:last-child{{border-bottom:none}}
.best-val{{color:var(--success);font-weight:700}}
.matches-area{{display:flex;flex-direction:column;gap:12px}}
.match-card{{background:var(--card);border-radius:12px;border:1px solid #1e293b;overflow:hidden;transition:border-color .2s}}
.match-card:hover{{border-color:var(--accent2)}}
.match-header{{padding:12px 14px;background:var(--card-h);border-bottom:1px solid #1e293b}}
.match-teams{{font-size:1.05em;font-weight:700;margin-bottom:4px}}
.match-teams .vs{{color:var(--muted);margin:0 7px;font-weight:400}}
.match-teams .home{{color:var(--accent)}}
.match-teams .away{{color:var(--accent2)}}
.match-meta{{display:flex;gap:8px;flex-wrap:wrap;font-size:.78em;color:var(--muted);align-items:center}}
.league-tag{{background:rgba(129,140,248,0.12);color:var(--accent2);padding:2px 7px;border-radius:4px;font-size:.9em}}
.changes-bar{{display:flex;gap:6px;margin-left:auto}}
.ch-up{{background:rgba(52,211,153,0.15);color:var(--success);padding:1px 6px;border-radius:4px;font-size:.85em}}
.ch-down{{background:rgba(248,113,113,0.15);color:var(--danger);padding:1px 6px;border-radius:4px;font-size:.85em}}
.match-markets{{padding:12px 14px;display:flex;flex-direction:column;gap:10px}}
.mkt-block{{padding:9px;background:rgba(15,23,42,0.5);border-radius:8px}}
.mkt-title{{font-size:.72em;color:var(--accent);text-transform:uppercase;letter-spacing:.5px;font-weight:700;margin-bottom:6px}}
.sel-wrap{{display:flex;gap:7px;flex-wrap:wrap}}
.sel{{display:flex;flex-direction:column;align-items:center;background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.15);border-radius:7px;padding:6px 10px;min-width:65px;position:relative}}
.sel-n{{font-size:.72em;color:var(--muted);margin-bottom:1px}}
.sel-o{{font-size:1.05em;font-weight:700;color:var(--text)}}
.sel-bk{{font-size:.65em;color:#64748b;margin-top:1px;max-width:65px;overflow:hidden;text-overflow:ellipsis}}
.sel.best-odds{{background:rgba(52,211,153,0.12);border-color:rgba(52,211,153,0.4)}}
.sel.best-odds .sel-o{{color:var(--success)}}
.var-badge{{position:absolute;top:-4px;right:-4px;font-size:.6em;padding:1px 4px;border-radius:4px;font-weight:700}}
.var-badge.up{{background:var(--success);color:#0f172a}}
.var-badge.down{{background:var(--danger);color:#fff}}
.comp-table{{width:100%;border-collapse:collapse;font-size:.82em}}
.comp-table th{{background:var(--card-h);padding:8px 10px;text-align:left;border-bottom:1px solid #1e293b;color:var(--accent);font-weight:600}}
.comp-table td{{padding:7px 10px;border-bottom:1px solid #1e293b;white-space:nowrap}}
.comp-table tr:hover td{{background:rgba(56,189,248,0.04)}}
.trend-row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed #1e293b;font-size:.82em}}
.trend-row:last-child{{border-bottom:none}}
.trend-match{{min-width:160px;font-weight:600}}
.trend-mkt{{color:var(--accent);min-width:80px}}
.trend-sel{{color:var(--muted);min-width:50px}}
.trend-odds{{font-weight:700;min-width:45px}}
.trend-bk{{color:var(--muted);font-size:.9em;min-width:70px}}
.trend-time{{color:#64748b;font-size:.85em}}
.empty{{text-align:center;padding:50px 20px;color:var(--muted}}
.empty-icon{{font-size:3em;margin-bottom:10px}}
@media(max-width:900px){{.main-layout{{grid-template-columns:1fr}}.sidebar{{position:static;order:2}}}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div><h1>⚽ WinBet Dashboard</h1><div class="sub">Quote live dai principali bookmaker — Ultimo aggiornamento: {timestamp}</div></div>
    <div class="actions">
      <span class="sub">Auto-refresh: 1h</span>
      <a href="{csv_b64}" download="winbet_quote.csv" class="btn btn-success">📥 Esporta CSV</a>
    </div>
  </header>

  <div class="stats">
    <div class="stat-card"><div class="n">{stats['matches']}</div><div class="l">Partite</div></div>
    <div class="stat-card"><div class="n">{stats['odds']}</div><div class="l">Quote salvate</div></div>
    <div class="stat-card"><div class="n">{len(surebets)}</div><div class="l">Surebet ≥{min_profit}%</div></div>
    <div class="stat-card"><div class="n">{stats['bookmakers']}</div><div class="l">Bookmaker</div></div>
    <div class="stat-card"><div class="n">{stats['last_update'][:10] if stats['last_update'] != 'N/A' else '—'}</div><div class="l">Ultimo aggiornamento</div></div>
  </div>

  <div class="main-layout">
    <div class="sidebar">
      <div class="panel">
        <div class="panel-header"><span class="panel-icon">🔍</span>Filtri</div>
        <div class="panel-body">
          <div class="filter-group"><label>Campionato</label><select id="filter-league" onchange="applyFilters()"><option value="">Tutti</option>{league_opts}</select></div>
          <div class="filter-group"><label>Bookmaker</label><select id="filter-bk" onchange="applyFilters()"><option value="">Tutti</option>{bk_opts}</select></div>
          <div class="filter-group"><label>Cerca squadra</label><input type="text" id="filter-team" placeholder="Nome squadra..." onkeyup="applyFilters()"/></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header"><span class="panel-icon">🏆</span>Migliori Quote</div>
        <div class="panel-body" id="best-odds-body"><div class="empty" style="padding:20px"><em>Seleziona un campionato...</em></div></div>
      </div>
    </div>

    <div class="matches-area">
      {sb_html}
      <h2 style="color:var(--accent);margin:0;font-size:1.25em">📋 Partite</h2>
      {matches_html if matches_html else '<div class="empty"><div class="empty-icon">📭</div>Nessuna partita trovata</div>'}
      {comp_table}
      {trend_html}
    </div>
  </div>
</div>

<script>
function applyFilters(){{
  const league = document.getElementById('filter-league').value.toLowerCase();
  const team = document.getElementById('filter-team').value.toLowerCase();
  document.querySelectorAll('.match-card').forEach(card=>{{
    const cardLeague = (card.dataset.league||'').toLowerCase();
    const teams = (card.dataset.teams||'').toLowerCase();
    const show = (!league||cardLeague.includes(league)) && (!team||teams.includes(team));
    card.style.display = show ? '' : 'none';
  }});
}}
</script>
</body></html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard v3 generata: {output_path}")
    print(f"   Partite: {stats['matches']} | Quote: {stats['odds']} | Surebets≥{min_profit}%: {len(surebets)}")
    print(f"   CSV embeddato | Trend ultima ora | Variazioni >10% evidenziate")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--output", default="/mnt/c/Users/angel/WinBet/dashboard.html")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--min-profit", type=float, default=2.0)
    args = p.parse_args()
    generate(args.db, args.output, args.limit, args.min_profit)


if __name__ == "__main__":
    main()

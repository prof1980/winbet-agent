#!/usr/bin/env python3
"""WinBet Dashboard Generator v2 — Dashboard professionale con filtri, trend e surebets.

Uso:
    python3 generate_dashboard.py [--db path] [--output dashboard.html] [--min-profit 1.0]
"""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "winbet.db"


def get_db_stats(cur: sqlite3.Cursor) -> dict:
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


def get_surebets(cur: sqlite3.Cursor, min_profit: float = 1.0) -> list[dict]:
    """Surebets filtrate per profitto realistico."""
    cur.execute("""
        SELECT match_id, selections, profit_percent, total_implied_prob, detected_at
        FROM surebets
        WHERE status = 'active' AND profit_percent >= ?
        ORDER BY profit_percent DESC
        LIMIT 20
    """, (min_profit,))
    rows = cur.fetchall()
    result = []
    for mid, sels, profit, margin, dt in rows:
        try:
            sel_data = json.loads(sels) if sels else {}
        except Exception:
            sel_data = {}
        result.append({
            "match_id": mid,
            "profit": round(profit, 2),
            "margin": round(margin, 4),
            "detected_at": dt[:16] if dt else "",
            "selections": sel_data,
        })
    return result


def get_matches(cur: sqlite3.Cursor, limit: int = 100) -> list[dict]:
    """Recupera partite con quote aggregate per mercato."""
    cur.execute("""
        SELECT match_id, home_team, away_team, league_id, match_date, match_time, status
        FROM matches
        ORDER BY match_date ASC, match_time ASC
        LIMIT ?
    """, (limit,))
    matches = []
    for mid, home, away, league, date, time, status in cur.fetchall():
        # Quote per questa partita
        cur.execute("""
            SELECT market_type, selection_name, odds_value, bookmaker_id, scraped_at
            FROM odds
            WHERE match_id = ?
            ORDER BY market_type, selection_name, odds_value DESC
        """, (mid,))

        markets = {}
        for mkt, sel, odds, bk, at in cur.fetchall():
            key = mkt
            if key not in markets:
                markets[key] = {}
            if sel not in markets[key]:
                markets[key][sel] = []
            markets[key][sel].append({"odds": odds, "bookmaker": bk})

        # Calcola miglior quota per selezione
        best_markets = {}
        for mkt, sels in markets.items():
            best_markets[mkt] = {}
            for sel, bk_list in sels.items():
                best = max(bk_list, key=lambda x: x["odds"])
                best_markets[mkt][sel] = best

        matches.append({
            "id": mid,
            "home": home,
            "away": away,
            "league": league or "",
            "date": date or "",
            "time": time or "",
            "status": status or "",
            "markets": best_markets,
        })
    return matches


def get_leagues(cur: sqlite3.Cursor) -> list[str]:
    cur.execute("SELECT DISTINCT league_id FROM matches WHERE league_id IS NOT NULL AND league_id != '' ORDER BY league_id")
    return [r[0] for r in cur.fetchall()]


def get_bookmakers(cur: sqlite3.Cursor) -> list[str]:
    cur.execute("SELECT DISTINCT bookmaker_id FROM odds WHERE bookmaker_id IS NOT NULL ORDER BY bookmaker_id")
    return [r[0] for r in cur.fetchall()]


def get_odds_trends(cur: sqlite3.Cursor, match_id: str, limit: int = 5) -> dict:
    """Restituisce trend quote per i principali mercati di una partita."""
    cur.execute("""
        SELECT market_type, selection_name, odds_value, recorded_at
        FROM odds_history
        WHERE match_id = ?
        ORDER BY recorded_at DESC
        LIMIT ?
    """, (match_id, limit * 6))
    trends = {}
    for mkt, sel, odds, ts in cur.fetchall():
        key = f"{mkt}_{sel}"
        if key not in trends:
            trends[key] = []
        trends[key].append({"odds": odds, "ts": ts})
    return trends


def generate(db_path: str, output_path: str, limit: int = 100, min_profit: float = 1.0) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    stats = get_db_stats(cur)
    surebets = get_surebets(cur, min_profit)
    matches = get_matches(cur, limit)
    leagues = get_leagues(cur)
    bookmakers = get_bookmakers(cur)

    # Calcola quote migliori per mercato
    market_best = {}
    for m in matches:
        for mkt, sels in m["markets"].items():
            if mkt not in market_best:
                market_best[mkt] = {}
            for sel, data in sels.items():
                if sel not in market_best[mkt] or data["odds"] > market_best[mkt][sel]["odds"]:
                    market_best[mkt][sel] = {"odds": data["odds"], "match": f"{m['home']} vs {m['away']}"}

    # Surebets HTML
    surebets_html = ""
    if surebets:
        srows = ""
        for sb in surebets:
            combo = sb.get("selections", {})
            if isinstance(combo, list):
                combo_str = " | ".join(str(x) for x in combo[:3])
            elif isinstance(combo, dict):
                combo_str = " | ".join(
                    f"{k}@{v.get('odds','?')} ({v.get('bookmaker','?')})"
                    for k, v in combo.items()
                )
            else:
                combo_str = str(combo)[:100]
            srows += f'''
<div class="sb-row">
  <div class="sb-info">
    <div class="sb-match">{sb['match_id']}</div>
    <div class="sb-details">{combo_str}</div>
  </div>
  <div class="sb-badge" style="background: linear-gradient(135deg,#34d399,#10b981)">+{sb['profit']}%</div>
</div>'''
        surebets_html = f'''
<div class="panel danger">
  <div class="panel-header">
    <span class="panel-icon">🚨</span>
    <span>Surebet Rilevate <span class="badge">{len(surebets)}</span></span>
  </div>
  <div class="panel-body">{srows}</div>
</div>'''

    # Filtri
    league_options = "\n".join(f'    <option value="{l}">{l}</option>' for l in leagues[:30])
    bk_options = "\n".join(f'    <option value="{b}">{b}</option>' for b in bookmakers[:20])

    # Matches HTML
    matches_html = ""
    for idx, m in enumerate(matches):
        mid = m["id"]
        home = m["home"]
        away = m["away"]
        league = m["league"]
        date = m["date"]
        time = m["time"]
        status = m["status"]

        # Formatta data
        date_display = f"{date} {time}" if date else "Data sconosciuta"

        # Mercati
        markets_html = ""
        for mkt_name, sels in list(m["markets"].items())[:4]:
            sel_html = ""
            for sel_name, data in sels.items():
                odds = data["odds"]
                bk = data["bookmaker"]
                # Verifica se è la migliore quota globale per questo mercato/selezione
                is_best = False
                if mkt_name in market_best and sel_name in market_best[mkt_name]:
                    is_best = abs(market_best[mkt_name][sel_name]["odds"] - odds) < 0.01

                best_cls = "best-odds" if is_best else ""
                sel_html += f'''<span class="sel {best_cls}"><span class="sel-n">{sel_name}</span><span class="sel-o">{odds}</span><span class="sel-bk">{bk[:12]}</span></span>'''

            markets_html += f'''
<div class="mkt-block">
  <div class="mkt-title">{mkt_name}</div>
  <div class="sel-wrap">{sel_html}</div>
</div>'''

        matches_html += f'''
<div class="match-card" data-league="{league}" data-index="{idx}">
  <div class="match-header">
    <div class="match-teams"><span class="home">{home}</span> <span class="vs">vs</span> <span class="away">{away}</span></div>
    <div class="match-meta"><span class="league-tag">{league}</span> <span class="date">{date_display}</span> <span class="status">{status}</span></div>
  </div>
  <div class="match-markets">{markets_html}</div>
</div>'''

    best_odds_html = ""
    for mkt, sels in list(market_best.items())[:5]:
        for sel, data in list(sels.items())[:3]:
            best_odds_html += f'''<div class="best-row">
  <span><b>{mkt}</b> {sel}</span>
  <span class="best-val">{data['odds']}</span>
  <span class="best-match">{data['match'][:30]}</span>
</div>'''

    conn.close()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="1800">
<title>WinBet Dashboard v2</title>
<style>
:root{{--bg:#0b1121;--card:#151e32;--card-h:#1a2642;--text:#e2e8f0;--muted:#94a3b8;--accent:#38bdf8;--accent2:#818cf8;--danger:#f87171;--success:#34d399;--warn:#fbbf24}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.5}}
.container{{max-width:1600px;margin:0 auto;padding:20px}}
header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px;padding-bottom:15px;border-bottom:1px solid #1e293b}}
header h1{{margin:0;font-size:1.8em;color:var(--accent);display:flex;align-items:center;gap:10px}}
.sub{{color:var(--muted);font-size:0.85em}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:25px}}
.stat-card{{background:linear-gradient(145deg,var(--card),var(--card-h));border-radius:10px;padding:16px;text-align:center;border:1px solid #1e293b;transition:transform .2s}}
.stat-card:hover{{transform:translateY(-2px);border-color:var(--accent)}}
.stat-card .n{{font-size:1.9em;font-weight:700;color:var(--accent)}}
.stat-card .l{{font-size:0.8em;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:0.5px}}
.main-layout{{display:grid;grid-template-columns:260px 1fr;gap:20px}}
.sidebar{{display:flex;flex-direction:column;gap:16px}}
.panel{{background:var(--card);border-radius:12px;border:1px solid #1e293b;overflow:hidden}}
.panel-header{{padding:14px 16px;font-weight:600;border-bottom:1px solid #1e293b;display:flex;align-items:center;gap:10px;background:var(--card-h)}}
.panel-icon{{font-size:1.2em}}
.panel-body{{padding:14px}}
.panel.danger{{border-color:rgba(248,113,113,0.3)}}
.panel.danger .panel-header{{color:var(--danger);background:rgba(248,113,113,0.08)}}
.filter-group{{margin-bottom:12px}}
.filter-group label{{display:block;font-size:0.8em;color:var(--muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.5px}}
.filter-group input,.filter-group select{{width:100%;padding:8px 10px;border-radius:6px;border:1px solid #334155;background:#0f172a;color:var(--text);font-size:0.9em}}
.filter-group input:focus,.filter-group select:focus{{outline:none;border-color:var(--accent)}}
.badge{{display:inline-flex;align-items:center;justify-content:center;background:var(--accent);color:#0f172a;font-size:0.75em;font-weight:700;padding:2px 8px;border-radius:12px}}
.sb-row{{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;border-bottom:1px solid #1e293b;gap:10px}}
.sb-row:last-child{{border-bottom:none}}
.sb-match{{font-weight:600;font-size:0.9em}}
.sb-details{{font-size:0.78em;color:var(--muted);margin-top:3px;word-break:break-all}}
.sb-badge{{padding:4px 10px;border-radius:6px;font-weight:700;font-size:0.85em;white-space:nowrap}}
.best-row{{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px dashed #1e293b;font-size:0.85em}}
.best-row:last-child{{border-bottom:none}}
.best-val{{color:var(--success);font-weight:700}}
.best-match{{color:var(--muted);font-size:0.8em;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.matches-area{{display:flex;flex-direction:column;gap:14px}}
.match-card{{background:var(--card);border-radius:12px;border:1px solid #1e293b;overflow:hidden;transition:border-color .2s}}
.match-card:hover{{border-color:var(--accent2)}}
.match-header{{padding:14px 16px;background:var(--card-h);border-bottom:1px solid #1e293b}}
.match-teams{{font-size:1.1em;font-weight:700;margin-bottom:6px}}
.match-teams .vs{{color:var(--muted);margin:0 8px;font-weight:400}}
.match-teams .home{{color:var(--accent)}}
.match-teams .away{{color:var(--accent2)}}
.match-meta{{display:flex;gap:10px;flex-wrap:wrap;font-size:0.78em;color:var(--muted);align-items:center}}
.league-tag{{background:rgba(129,140,248,0.12);color:var(--accent2);padding:2px 8px;border-radius:4px;font-size:0.9em}}
.status{{background:rgba(56,189,248,0.1);color:var(--accent);padding:2px 8px;border-radius:4px}}
.match-markets{{padding:14px 16px;display:flex;flex-direction:column;gap:12px}}
.mkt-block{{padding:10px;background:rgba(15,23,42,0.5);border-radius:8px}}
.mkt-title{{font-size:0.75em;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;font-weight:700;margin-bottom:8px}}
.sel-wrap{{display:flex;gap:8px;flex-wrap:wrap}}
.sel{{display:flex;flex-direction:column;align-items:center;background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.15);border-radius:8px;padding:8px 12px;min-width:70px}}
.sel-n{{font-size:0.75em;color:var(--muted);margin-bottom:2px}}
.sel-o{{font-size:1.15em;font-weight:700;color:var(--text)}}
.sel-bk{{font-size:0.7em;color:#64748b;margin-top:2px;max-width:70px;overflow:hidden;text-overflow:ellipsis}}
.sel.best-odds{{background:rgba(52,211,153,0.12);border-color:rgba(52,211,153,0.4)}}
.sel.best-odds .sel-o{{color:var(--success)}}
.empty{{text-align:center;padding:60px 20px;color:var(--muted)}}
.empty-icon{{font-size:3em;margin-bottom:10px}}
@media(max-width:900px){{.main-layout{{grid-template-columns:1fr}}.sidebar{{order:2}}}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div><h1>⚽ WinBet Dashboard</h1><div class="sub">Quote live dai principali bookmaker — Ultimo aggiornamento: {timestamp}</div></div>
    <div class="sub">Auto-refresh: 1h | Fonti: SNAI, Eurobet, The Odds API</div>
  </header>

  <div class="stats">
    <div class="stat-card"><div class="n">{stats['matches']}</div><div class="l">Partite</div></div>
    <div class="stat-card"><div class="n">{stats['odds']}</div><div class="l">Quote salvate</div></div>
    <div class="stat-card"><div class="n">{len(surebets)}</div><div class="l">Surebet &gt;{min_profit}%</div></div>
    <div class="stat-card"><div class="n">{stats['bookmakers']}</div><div class="l">Bookmaker</div></div>
    <div class="stat-card"><div class="n">{stats['last_update'][:10] if stats['last_update'] != 'N/A' else '—'}</div><div class="l">Ultimo aggiornamento</div></div>
  </div>

  <div class="main-layout">
    <div class="sidebar">
      <div class="panel">
        <div class="panel-header"><span class="panel-icon">🔍</span>Filtri</div>
        <div class="panel-body">
          <div class="filter-group">
            <label>Campionato</label>
            <select id="filter-league" onchange="applyFilters()">
              <option value="">Tutti</option>
              {league_options}
            </select>
          </div>
          <div class="filter-group">
            <label>Bookmaker</label>
            <select id="filter-bk" onchange="applyFilters()">
              <option value="">Tutti</option>
              {bk_options}
            </select>
          </div>
          <div class="filter-group">
            <label>Cerca squadra</label>
            <input type="text" id="filter-team" placeholder="Nome squadra..." onkeyup="applyFilters()"/>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header"><span class="panel-icon">🏆</span>Migliori Quote</div>
        <div class="panel-body">{best_odds_html}</div>
      </div>
    </div>

    <div class="matches-area">
      {surebets_html}
      <h2 style="color:var(--accent);margin:0;font-size:1.3em">📋 Partite</h2>
      {matches_html if matches_html else '<div class="empty"><div class="empty-icon">📭</div>Nessuna partita trovata</div>'}
    </div>
  </div>
</div>

<script>
function applyFilters() {{
  const league = document.getElementById('filter-league').value.toLowerCase();
  const bk = document.getElementById('filter-bk').value.toLowerCase();
  const team = document.getElementById('filter-team').value.toLowerCase();
  const cards = document.querySelectorAll('.match-card');
  cards.forEach(card => {{
    const text = card.innerText.toLowerCase();
    const cardLeague = (card.dataset.league || '').toLowerCase();
    const show = (!league || cardLeague.includes(league)) &&
                 (!team || text.includes(team));
    card.style.display = show ? '' : 'none';
  }});
}}
</script>
</body>
</html>
'''

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard v2 generata: {output_path}")
    print(f"   Statistiche: {stats['matches']} partite, {stats['odds']} quote, {len(surebets)} surebets filtrate (≥{min_profit}%)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default="/mnt/c/Users/angel/WinBet/dashboard.html")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--min-profit", type=float, default=1.0, help="Profitto minimo per mostrare surebet")
    args = parser.parse_args()
    generate(args.db, args.output, args.limit, args.min_profit)


if __name__ == "__main__":
    main()

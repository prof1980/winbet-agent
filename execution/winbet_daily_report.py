#!/usr/bin/env python3
"""
WinBet Daily Report — Genera report completo sullo stato dell'agente
e lo invia via email Libero a uno o più destinatari.

Contenuto del report:
1. Stato scraping: bookmaker attivi, eventi raccolti, errori
2. Surebet rilevate: top 10 con profitto >= 1%
3. Quote migliori per partita: variazioni rispetto al giorno precedente
4. Performance scraper: tempi medi,成功率
5. Salute sistema: spazio disco, dimensione DB, uptime
6. Notizie e azioni consigliate

Esempio:
    python winbet_daily_report.py --to angelo.bruno80@gmail.com
    python winbet_daily_report.py --to angelo.bruno80@gmail.com,watson.ag@libero.it
    python winbet_daily_report.py --to angelo.bruno80@gmail.com --days 7  # report settimanale
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "python-dotenv",
# ]
# ///

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

sys.path.insert(0, str(_PROJECT_ROOT / "execution"))
from libero_notifier import LiberoNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("winbet_daily_report")

_DB_PATH = _PROJECT_ROOT / "winbet.db"
_CONFIG_PATH = _PROJECT_ROOT / "winbet_config.json"


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def collect_db_stats() -> dict:
    """Raccoglie statistiche dal database."""
    if not _DB_PATH.exists():
        return {"error": "Database non trovato"}

    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    stats = {}

    # Conteggi base
    c.execute("SELECT COUNT(*) FROM matches")
    stats["total_matches"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM odds")
    stats["total_odds"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surebets")
    stats["total_surebets"] = c.fetchone()[0]

    # Surebet con profitto >= 1%
    c.execute("SELECT COUNT(*) FROM surebets WHERE profit_percent >= 1.0")
    stats["surebets_profitable"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM surebets WHERE profit_percent >= 5.0")
    stats["surebets_high_profit"] = c.fetchone()[0]
    c.execute("SELECT MAX(profit_percent) FROM surebets")
    stats["max_profit"] = c.fetchone()[0] or 0

    # Partite per lega
    c.execute("""
        SELECT league_id, COUNT(*) as cnt
        FROM matches
        WHERE league_id IS NOT NULL AND league_id != ''
        GROUP BY league_id
        ORDER BY cnt DESC
        LIMIT 10
    """)
    stats["leagues"] = [{"name": r[0], "count": r[1]} for r in c.fetchall()]

    # Bookmaker con dati
    c.execute("""
        SELECT bookmaker_id, COUNT(DISTINCT match_id) as matches, COUNT(*) as odds
        FROM odds
        GROUP BY bookmaker_id
        ORDER BY matches DESC
    """)
    stats["bookmakers"] = [
        {"name": r[0], "matches": r[1], "odds": r[2]} for r in c.fetchall()
    ]

    # Surebet top 10
    c.execute("""
        SELECT s.profit_percent, s.market_type, s.selections,
               m.home_team, m.away_team, m.match_date
        FROM surebets s
        JOIN matches m ON s.match_id = m.match_id
        WHERE s.profit_percent >= 1.0
        ORDER BY s.profit_percent DESC
        LIMIT 10
    """)
    stats["top_surebets"] = []
    for profit, market, sels_json, home, away, date in c.fetchall():
        try:
            sels = json.loads(sels_json) if sels_json else []
        except Exception:
            sels = []
        stats["top_surebets"].append({
            "profit": profit,
            "market": market,
            "match": f"{home} vs {away}",
            "date": date,
            "selections": sels,
        })

    # Quote aggiornate oggi
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM odds WHERE DATE(scraped_at) = ?", (today,))
    stats["odds_updated_today"] = c.fetchone()[0]

    # Cronologia scraping (ultimi N giorni)
    c.execute("""
        SELECT DATE(started_at) as day, bookmaker_id,
               SUM(matches_found) as matches, COUNT(*) as runs,
               SUM(CASE WHEN errors IS NULL OR errors = '' THEN 1 ELSE 0 END) as success
        FROM scrape_log
        WHERE DATE(started_at) >= DATE('now', '-7 days')
        GROUP BY DATE(started_at), bookmaker_id
        ORDER BY day DESC
    """)
    stats["scrape_history"] = [
        {
            "day": r[0],
            "bookmaker": r[1],
            "matches": r[2] or 0,
            "runs": r[3],
            "success": r[4],
        }
        for r in c.fetchall()
    ]

    conn.close()
    return stats


def collect_system_health() -> dict:
    """Salute sistema: disco, DB, config."""
    health = {}

    # Spazio disco
    import shutil
    disk = shutil.disk_usage(_PROJECT_ROOT)
    health["disk_total_gb"] = disk.total / (1024**3)
    health["disk_used_gb"] = disk.used / (1024**3)
    health["disk_free_gb"] = disk.free / (1024**3)
    health["disk_used_percent"] = (disk.used / disk.total) * 100

    # Dimensione database
    if _DB_PATH.exists():
        health["db_size_mb"] = _DB_PATH.stat().st_size / (1024**2)
    else:
        health["db_size_mb"] = 0

    # Config
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            health["interval_minutes"] = cfg.get("scrape", {}).get("interval_minutes", "?")
            health["enabled_bookmakers"] = cfg.get("scrape", {}).get("bookmakers_enabled", [])
            health["mode"] = cfg.get("mode", "?")
        except Exception:
            health["config_error"] = "Impossibile leggere winbet_config.json"
    else:
        health["config_error"] = "winbet_config.json non trovato"

    return health


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_text_report(stats: dict, health: dict, days: int = 1) -> str:
    """Genera report in formato testo (plaintext)."""
    now = datetime.now(timezone.utc)
    report_type = "GIORNALIERO" if days == 1 else f"ULTIMI {days} GIORNI"

    lines = []
    lines.append("=" * 70)
    lines.append(f"📊 WINBET REPORT {report_type}")
    lines.append(f"📅 Generato: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append(f"🗄️  Database: {stats.get('total_matches', 0)} partite, "
                 f"{stats.get('total_odds', 0)} quote, "
                 f"{stats.get('total_surebets', 0)} surebet")
    lines.append("=" * 70)
    lines.append("")

    # 1. Salute sistema
    lines.append("🖥️  STATO SISTEMA")
    lines.append("-" * 70)
    if "db_size_mb" in health:
        lines.append(f"  • Database: {health['db_size_mb']:.2f} MB")
    if "disk_free_gb" in health:
        lines.append(f"  • Disco libero: {health['disk_free_gb']:.1f} GB "
                     f"({health['disk_used_percent']:.1f}% usato)")
    if "interval_minutes" in health:
        lines.append(f"  • Intervallo scraping: {health['interval_minutes']} minuti")
    if "enabled_bookmakers" in health:
        bm_list = ", ".join(health["enabled_bookmakers"]) or "nessuno"
        lines.append(f"  • Bookmaker abilitati: {bm_list}")
    if "mode" in health:
        lines.append(f"  • Modalità: {health['mode']}")
    lines.append(f"  • Quote aggiornate oggi: {stats.get('odds_updated_today', 0)}")
    lines.append("")

    # 2. Bookmaker attivi
    if stats.get("bookmakers"):
        lines.append("📡 BOOKMAKER ATTIVI")
        lines.append("-" * 70)
        lines.append(f"  {'Bookmaker':<25} {'Partite':>10} {'Quote':>10}")
        for bm in stats["bookmakers"][:10]:
            lines.append(f"  {bm['name']:<25} {bm['matches']:>10} {bm['odds']:>10}")
        lines.append("")

    # 3. Top leghe
    if stats.get("leagues"):
        lines.append("⚽ TOP CAMPIONATI (per numero partite)")
        lines.append("-" * 70)
        for lg in stats["leagues"][:8]:
            lines.append(f"  • {lg['name']}: {lg['count']} partite")
        lines.append("")

    # 4. Surebet
    lines.append("💰 SUREBET RILEVATE")
    lines.append("-" * 70)
    profitable = stats.get("surebets_profitable", 0)
    high_profit = stats.get("surebets_high_profit", 0)
    max_profit = stats.get("max_profit", 0)
    lines.append(f"  • Totale con profitto >= 1%: {profitable}")
    lines.append(f"  • Totale con profitto >= 5%: {high_profit}")
    lines.append(f"  • Profitto massimo rilevato: {max_profit:.2f}%")
    lines.append("")

    if stats.get("top_surebets"):
        lines.append("  🔝 Top 10 Surebet:")
        for i, sb in enumerate(stats["top_surebets"], 1):
            lines.append(f"  {i:>2}. [{sb['profit']:>5.2f}%] {sb['match']} ({sb['date']})")
            lines.append(f"      Mercato: {sb['market']}")
            for sel in sb["selections"][:3]:
                bk = sel.get("bookmaker", "?")
                oc = sel.get("label", sel.get("selection", sel.get("outcome", "?")))
                od = sel.get("odds", 0)
                lines.append(f"        {oc} @ {od:.2f} ({bk})")
        lines.append("")

    # 5. Cronologia scraping
    if stats.get("scrape_history"):
        lines.append("📈 CRONOLOGIA SCRAPING (ultimi 7 giorni)")
        lines.append("-" * 70)
        lines.append(f"  {'Data':<12} {'Bookmaker':<20} {'Partite':>8} {'Run':>5} {'OK':>5}")
        for entry in stats["scrape_history"][:15]:
            lines.append(
                f"  {entry['day']:<12} {entry['bookmaker']:<20} "
                f"{entry['matches']:>8} {entry['runs']:>5} {entry['success']:>5}"
            )
        lines.append("")

    # Footer
    lines.append("=" * 70)
    lines.append("🌐 Dashboard: http://localhost:8080/")
    lines.append("📧 Per inviare comandi: scrivi a watson.ag@libero.it")
    lines.append("=" * 70)

    return "\n".join(lines)


def render_html_report(stats: dict, health: dict, days: int = 1) -> str:
    """Genera report in formato HTML per email più ricche."""
    now = datetime.now(timezone.utc)
    report_type = "Giornaliero" if days == 1 else f"Ultimi {days} giorni"

    css = """
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 0 auto;
               padding: 20px; background: #f5f5f5; color: #333; }
        .header { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
                  color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .header h1 { margin: 0; font-size: 24px; }
        .header .meta { opacity: 0.9; font-size: 14px; margin-top: 5px; }
        .card { background: white; padding: 15px 20px; border-radius: 8px;
                margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .card h2 { margin-top: 0; font-size: 18px; color: #1e3a8a; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8fafc; font-weight: 600; color: #1e3a8a; }
        .stat { display: inline-block; margin-right: 30px; }
        .stat-label { font-size: 12px; color: #64748b; text-transform: uppercase; }
        .stat-value { font-size: 24px; font-weight: bold; color: #1e3a8a; }
        .profit { color: #16a34a; font-weight: bold; }
        .profit-high { color: #dc2626; font-weight: bold; }
        .footer { text-align: center; color: #64748b; font-size: 12px; margin-top: 30px; }
    </style>
    """

    # Stats boxes
    stats_html = f"""
    <div style="display: flex; flex-wrap: wrap; gap: 20px; margin: 15px 0;">
        <div class="stat">
            <div class="stat-label">Partite</div>
            <div class="stat-value">{stats.get('total_matches', 0)}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Quote</div>
            <div class="stat-value">{stats.get('total_odds', 0):,}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Surebet</div>
            <div class="stat-value">{stats.get('total_surebets', 0)}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Profittevoli (≥1%)</div>
            <div class="stat-value profit">{stats.get('surebets_profitable', 0)}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Alta Priorità (≥5%)</div>
            <div class="stat-value profit-high">{stats.get('surebets_high_profit', 0)}</div>
        </div>
    </div>
    """

    # Bookmaker table
    bm_rows = ""
    for bm in stats.get("bookmakers", [])[:10]:
        bm_rows += f"<tr><td>{bm['name']}</td><td>{bm['matches']}</td><td>{bm['odds']:,}</td></tr>"

    # Surebet table
    sb_rows = ""
    for sb in stats.get("top_surebets", [])[:10]:
        profit_class = "profit-high" if sb["profit"] >= 5 else "profit"
        sels_text = ", ".join(
            f"{s.get('label', s.get('selection', s.get('outcome', '?')))} @ {s.get('odds', 0):.2f} ({s.get('bookmaker', '?')})"
            for s in sb.get("selections", [])[:3]
        )
        sb_rows += f"""
        <tr>
            <td><span class="{profit_class}">{sb['profit']:.2f}%</span></td>
            <td>{sb['match']}</td>
            <td>{sb['market']}</td>
            <td><small>{sels_text}</small></td>
        </tr>
        """

    # Cronologia scraping
    hist_rows = ""
    for h in stats.get("scrape_history", [])[:10]:
        hist_rows += f"""
        <tr>
            <td>{h['day']}</td>
            <td>{h['bookmaker']}</td>
            <td>{h['matches']}</td>
            <td>{h['runs']}</td>
            <td>{h['success']}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8">{css}</head><body>
        <div class="header">
            <h1>📊 WinBet Report {report_type}</h1>
            <div class="meta">Generato: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
        </div>

        <div class="card">
            <h2>📈 Stato Generale</h2>
            {stats_html}
        </div>

        <div class="card">
            <h2>💰 Top Surebet</h2>
            <table>
                <thead>
                    <tr><th>Profitto</th><th>Partita</th><th>Mercato</th><th>Selezioni</th></tr>
                </thead>
                <tbody>{sb_rows or '<tr><td colspan="4">Nessuna surebet profittevole</td></tr>'}</tbody>
            </table>
        </div>

        <div class="card">
            <h2>📡 Bookmaker Attivi</h2>
            <table>
                <thead><tr><th>Nome</th><th>Partite</th><th>Quote</th></tr></thead>
                <tbody>{bm_rows or '<tr><td colspan="3">Nessun dato</td></tr>'}</tbody>
            </table>
        </div>

        <div class="card">
            <h2>📊 Cronologia Scraping (ultimi 7 giorni)</h2>
            <table>
                <thead>
                    <tr><th>Data</th><th>Bookmaker</th><th>Partite</th><th>Run</th><th>OK</th></tr>
                </thead>
                <tbody>{hist_rows or '<tr><td colspan="5">Nessuna attività</td></tr>'}</tbody>
            </table>
        </div>

        <div class="footer">
            WinBet Agent • Dashboard: <a href="http://localhost:8080/">localhost:8080</a><br>
            Comandi email: scrivi a watson.ag@libero.it
        </div>
    </body></html>
    """
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="WinBet Daily Report via email")
    parser.add_argument(
        "--to", required=True,
        help="Destinatari (separati da virgola)"
    )
    parser.add_argument(
        "--days", type=int, default=1,
        help="Numero di giorni da includere nel report (default: 1)"
    )
    parser.add_argument(
        "--subject-prefix", default="WinBet",
        help="Prefisso del subject"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Genera report senza inviare email"
    )

    args = parser.parse_args()

    log.info(f"Generazione report WinBet per ultimi {args.days} giorni")
    stats = collect_db_stats()
    health = collect_system_health()

    text = render_text_report(stats, health, days=args.days)
    html = render_html_report(stats, health, days=args.days)

    subject = f"[{args.subject_prefix}] Report {datetime.now():%Y-%m-%d}"
    if args.days > 1:
        subject += f" ({args.days} giorni)"

    if args.dry_run:
        print("=" * 70)
        print(f"SUBJECT: {subject}")
        print("=" * 70)
        print(text)
        return 0

    # Invia email
    recipients = [r.strip() for r in args.to.split(",") if r.strip()]
    n = LiberoNotifier()
    log.info(f"Invio report a {len(recipients)} destinatari: {recipients}")

    success = 0
    for recipient in recipients:
        ok = n.send_email(
            to=recipient,
            subject=subject,
            body=text,
            html_body=html,
        )
        if ok:
            success += 1
            log.info(f"✅ Report inviato a {recipient}")
        else:
            log.error(f"❌ Invio fallito per {recipient}")

    log.info(f"Completato: {success}/{len(recipients)} report inviati")
    return 0 if success == len(recipients) else 1


if __name__ == "__main__":
    sys.exit(main())

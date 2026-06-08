#!/usr/bin/env python3
"""Eurobet Odds Scraper - API-first via curl_cffi.

Uses discovered endpoints from the-odds-api / discovery pass.
Endpoints:
  - /detail-service/sport-schedule/services/meeting/{discipline}/{meeting}?prematch=1&live=0
  - /detail-service/sport-schedule/services/discipline/calcio?prematch=1&live=0&temporalFilter=TEMPORAL_FILTER_OGGI

Quote values are in hundredths (142 = 1.42).
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["curl_cffi"]
# ///

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from curl_cffi import requests as curl_requests

DEFAULT_DB = Path(__file__).parent.parent / "winbet.db"

EUROBET_ENDPOINTS = {
    "mondiali-calcio": {
        "url": "https://www.eurobet.it/detail-service/sport-schedule/services/meeting/calcio/wd-mondiali-calcio?prematch=1&live=0",
        "competition": "Mondiali 2026",
    },
    "amichevoli-nazionali": {
        "url": "https://www.eurobet.it/detail-service/sport-schedule/services/meeting/calcio/wd-amichevoli-nazionali?prematch=1&live=0",
        "competition": "Amichevoli Nazionali",
    },
    "calcio-oggi": {
        "url": "https://www.eurobet.it/detail-service/sport-schedule/services/discipline/calcio?prematch=1&live=0&temporalFilter=TEMPORAL_FILTER_OGGI",
        "competition": "Calcio Oggi",
    },
}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.eurobet.it/it/scommesse",
    "Origin": "https://www.eurobet.it",
    "Connection": "keep-alive",
}


class EurobetScraper:
    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_DB)
        self.events_scraped = 0
        self.odds_saved = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fetch(self, url: str) -> dict | None:
        try:
            resp = curl_requests.get(
                url,
                headers=HEADERS,
                impersonate="chrome136",
                timeout=20,
            )
            if resp.status_code != 200:
                print(f"  ⚠ Eurobet HTTP {resp.status_code} for {url}")
                return None
            return resp.json()
        except Exception as exc:
            print(f"  ✗ Eurobet fetch failed: {exc}")
            return None

    @staticmethod
    def _odd_to_decimal(odd_value: int | float) -> float:
        """Convert hundredths to decimal odds."""
        if not odd_value:
            return 0.0
        return round(float(odd_value) / 100.0, 2)

    @staticmethod
    def _ms_to_iso(ts_ms: int | float) -> str:
        """Convert millisecond timestamp to ISO 8601."""
        if not ts_ms:
            return ""
        try:
            dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
            return dt.astimezone().isoformat()
        except Exception:
            return ""

    @staticmethod
    def _split_date_time(iso_str: str) -> tuple[str, str]:
        """Split ISO string into date and time parts."""
        if not iso_str:
            return "", ""
        if "T" in iso_str:
            parts = iso_str.split("T")
            return parts[0], parts[1][:5] if len(parts[1]) >= 5 else parts[1]
        return iso_str, ""

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_eurobet_event(self, item: dict, default_competition: str) -> dict | None:
        """Parse a single Eurobet event dict into standard WinBet format."""
        event_info = item.get("eventInfo", {})
        if not event_info:
            return None

        home = event_info.get("teamHome", {}).get("description", "")
        away = event_info.get("teamAway", {}).get("description", "")
        if not home or not away:
            return None

        event_desc = event_info.get("eventDescription", f"{home} - {away}")
        event_id = str(event_info.get("eventCode", ""))
        program_code = str(event_info.get("programCode", ""))
        start_ts = event_info.get("eventData", 0)
        competition = event_info.get("meetingDescription", default_competition)
        is_live = bool(event_info.get("live", False))

        canonical_id = f"eb_{program_code}_{event_id}"
        start_iso = self._ms_to_iso(start_ts)
        match_date, match_time = self._split_date_time(start_iso)

        markets = []
        bet_groups = item.get("betGroupList", [])
        for group in bet_groups:
            for odd_group in group.get("oddGroupList", []):
                market_name = odd_group.get("oddGroupDescription", "")
                if not market_name:
                    continue

                selections = []
                for odd in odd_group.get("oddList", []):
                    odd_val = self._odd_to_decimal(odd.get("oddValue", 0))
                    if odd_val <= 1.0:
                        continue
                    sel_name = odd.get("boxTitle", odd.get("oddDescription", ""))
                    sel_label = odd.get("oddDescription", sel_name)
                    selections.append({
                        "name": sel_name,
                        "label": sel_label,
                        "odds": odd_val,
                    })

                if selections:
                    markets.append({
                        "market_type": market_name,
                        "market_name": market_name,
                        "selections": selections,
                    })

        return {
            "event_id": canonical_id,
            "home_team": home,
            "away_team": away,
            "event_description": event_desc,
            "start_time": start_iso,
            "match_date": match_date,
            "match_time": match_time,
            "competition": competition,
            "live": is_live,
            "markets": markets,
        }

    def scrape_endpoint(self, key: str) -> list[dict]:
        """Scrape a single Eurobet endpoint by key."""
        config = EUROBET_ENDPOINTS.get(key)
        if not config:
            print(f"  ⚠ Unknown endpoint key: {key}")
            return []

        url = config["url"]
        default_comp = config["competition"]
        print(f"  🔍 Eurobet scraping: {key} → {default_comp}")

        data = self._fetch(url)
        if not data:
            return []

        if data.get("code") != 1:
            desc = data.get("description", "unknown")
            print(f"  ⚠ Eurobet API error: {desc}")
            return []

        result = data.get("result", {})
        groups = result.get("dataGroupList", [])
        if not groups:
            print(f"  ⚠ No dataGroupList in response")
            return []

        events = []
        total_items = 0
        for group in groups:
            items = group.get("itemList", [])
            for item in items:
                total_items += 1
                ev = self._parse_eurobet_event(item, default_comp)
                if ev and ev["markets"]:
                    events.append(ev)

        print(f"  ✓ Parsed {len(events)}/{total_items} events with odds")
        return events

    def scrape_all(self, endpoints: list[str] | None = None) -> list[dict]:
        """Scrape all configured Eurobet endpoints."""
        if endpoints is None:
            endpoints = ["mondiali-calcio", "amichevoli-nazionali"]

        all_events = []
        for key in endpoints:
            events = self.scrape_endpoint(key)
            all_events.extend(events)
        return all_events

    # ------------------------------------------------------------------
    # Database persistence (aligned with scrape_unified.py schema)
    # ------------------------------------------------------------------
    def save_to_db(self, events: list[dict]) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        for ev in events:
            match_id = ev["event_id"]
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
            """, (match_id, ev["competition"], ev["home_team"], ev["away_team"],
                  ev["match_date"], ev["match_time"], "scheduled", now))
            self.events_scraped += 1

            for mkt in ev.get("markets", []):
                for sel in mkt.get("selections", []):
                    cur.execute("""
                        INSERT INTO odds_history (match_id, bookmaker_id, market_type, selection_name, odds_value, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (match_id, "eurobet", mkt["market_type"], sel["name"], sel["odds"], now))

                    cur.execute("""
                        INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT DO UPDATE SET
                            odds_value=excluded.odds_value,
                            odds_decimal=excluded.odds_decimal,
                            scraped_at=excluded.scraped_at,
                            updated_at=excluded.updated_at
                    """, (match_id, "eurobet", mkt["market_type"], sel["name"], sel.get("label", ""), sel["odds"], sel["odds"], now, now))
                    self.odds_saved += 1

        conn.commit()
        conn.close()
        print(f"  💾 Saved {self.events_scraped} events, {self.odds_saved} odds")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eurobet API Odds Scraper")
    parser.add_argument("--endpoints", default="mondiali-calcio,amichevoli-nazionali",
                        help="Comma-separated endpoint keys")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--store-db", action="store_true", help="Persist to database")
    args = parser.parse_args()

    endpoint_keys = [k.strip() for k in args.endpoints.split(",")]

    scraper = EurobetScraper(db_path=args.db)
    events = scraper.scrape_all(endpoint_keys)

    result = {
        "scrape_timestamp": datetime.now().isoformat(),
        "bookmaker": "eurobet",
        "endpoints": endpoint_keys,
        "total_events": len(events),
        "events": events,
    }

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  ✓ JSON written to {args.output}")

    if args.store_db:
        scraper.save_to_db(events)

    print(f"\n📊 EUROBET: {len(events)} events scraped")


if __name__ == "__main__":
    main()

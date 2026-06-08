#!/usr/bin/env python3
"""WinBet Cloud Scraper — HTTP-based scraper using cloudscraper to bypass Cloudflare.

Use this when Playwright scraping fails due to anti-bot protections.
Targets: SNAI, Eurobet, Goldbet, OddsPortal, and other Italian bookmakers.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["cloudscraper", "beautifulsoup4"]
# ///

import argparse
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cloudscraper
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
DB_CONFIG = ROOT / "config" / "db_config.json"

def get_db():
    cfg = json.loads(DB_CONFIG.read_text(encoding="utf-8"))
    conn = sqlite3.connect(cfg["path"], check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.7,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

class CloudScraperEngine:
    """Scraper that uses cloudscraper to bypass Cloudflare and other anti-bot."""

    def __init__(self, proxy: str | None = None):
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            },
            delay=10,
        )
        self.proxy = proxy
        if proxy:
            self.scraper.proxies = {
                'http': proxy,
                'https': proxy,
            }
        self.session = self.scraper

    def get(self, url: str, **kwargs) -> Any:
        """Make a GET request with anti-bot handling."""
        merged_headers = {**HEADERS, **kwargs.pop('headers', {})}
        try:
            r = self.session.get(url, headers=merged_headers, timeout=30, allow_redirects=True, **kwargs)
            return r
        except Exception as exc:
            print(f"  ✗ Request failed: {exc}")
            return None

    def find_api_in_html(self, html: str, patterns: list[str]) -> list[str]:
        """Extract API endpoint URLs from HTML."""
        found = []
        for pat in patterns:
            regex = pat.replace("*", r"[^\"'<>]*")
            matches = re.findall(regex, html)
            found.extend(matches)
        return list(set(found))[:20]

    def parse_oddsportal(self, html: str, url: str) -> list[dict]:
        """Parse OddsPortal/CentroQuote HTML."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        # CentroQuote uses different structure from old OddsPortal
        # Try to find event rows
        event_rows = soup.select("div.eventRow, div[class*='event'], tr[class*='event'], div.match-row")
        if not event_rows:
            # Fallback: look for table rows with team names
            event_rows = soup.find_all("tr", class_=lambda x: x and ("event" in x.lower() or "match" in x.lower()))

        for row in event_rows:
            # Extract teams
            teams = row.select("a[href*='/team/'], .team-name, [class*='team'], .participant")
            if len(teams) >= 2:
                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)
            else:
                # Try generic name extraction
                name_el = row.select_one("a[href*='/match/'], a[href*='/game/']")
                if name_el:
                    text = name_el.get_text(strip=True)
                    if " - " in text:
                        parts = text.split(" - ", 1)
                        home, away = parts[0].strip(), parts[1].strip()
                    else:
                        continue
                else:
                    continue

            # Extract odds
            odds_els = row.select("[class*='odd'], [class*='quota'], [class*='price'], .oddsCell, td.odds")
            selections = []
            labels = ["1", "X", "2"]
            for i, el in enumerate(odds_els[:3]):
                text = el.get_text(strip=True).replace(",", ".")
                try:
                    val = float(text)
                    if val > 1.0:
                        selections.append({"name": labels[i], "label": labels[i], "odds": val})
                except (ValueError, IndexError):
                    continue

            if home and away and selections:
                events.append({
                    "home_team": home,
                    "away_team": away,
                    "source_url": url,
                    "selections": selections,
                })

        return events

    def discover(self, bookmaker: str, url: str) -> dict:
        """Discovery mode: analyze a bookmaker page for endpoints and structure."""
        print(f"🔍 CloudScraper discovery for {bookmaker} ...")
        r = self.get(url)
        if not r:
            return {"error": "request failed", "bookmaker": bookmaker}

        print(f"  Status: {r.status_code}, Final URL: {r.url}")

        # Look for JSON API endpoints in the page
        api_patterns = [
            r'https?://[^\s"\'<>]*/api/[^\s"\'<>]*',
            r'https?://[^\s"\'<>]*/sport[^\s"\'<>]*',
            r'https?://[^\s"\'<>]*/odds[^\s"\'<>]*',
            r'https?://[^\s"\'<>]*/event[^\s"\'<>]*',
            r'https?://[^\s"\'<>]*/match[^\s"\'<>]*',
        ]
        api_urls = []
        for pat in api_patterns:
            matches = re.findall(pat, r.text)
            api_urls.extend(matches)
        api_urls = list(set(api_urls))[:30]

        # Look for inline JSON data
        json_data = []
        for script in re.findall(r'\u003cscript[^\u003e]*\u003e([\s\S]*?)\u003c/script\u003e', r.text):
            if '"odds"' in script or '"events"' in script or '"matches"' in script:
                # Try to extract JSON object
                for match in re.findall(r'\{[^{}]*"(?:odds|events|matches|data)"[^{}]*\}', script):
                    json_data.append(match[:500])

        return {
            "bookmaker": bookmaker,
            "url": str(r.url),
            "status_code": r.status_code,
            "content_type": r.headers.get("content-type", ""),
            "server": r.headers.get("server", ""),
            "page_length": len(r.text),
            "api_urls_found": api_urls,
            "json_snippets": json_data[:10],
            "has_cloudflare": "cloudflare" in r.text.lower() or "cf-" in str(r.headers.get("server", "")).lower(),
            "html_preview": r.text[:2000],
        }


def main():
    parser = argparse.ArgumentParser(description="WinBet CloudScraper Engine")
    parser.add_argument("--discover", action="store_true", help="Discovery mode")
    parser.add_argument("--bookmaker", default="oddsportal", help="Bookmaker key")
    parser.add_argument("--url", default=None, help="Target URL")
    parser.add_argument("--proxy", default=None, help="Proxy URL (e.g. socks5://user:pass@host:port)")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    engine = CloudScraperEngine(proxy=args.proxy)

    if args.discover:
        url = args.url or "https://www.oddsportal.com/football/italy/serie-a/"
        result = engine.discover(args.bookmaker, url)
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n✓ Discovery report written to {out_path}")
        print(f"  API URLs found: {len(result.get('api_urls_found', []))}")
        print(f"  Cloudflare detected: {result.get('has_cloudflare', False)}")
    else:
        # Default: parse a URL
        url = args.url or "https://www.oddsportal.com/football/italy/serie-a/"
        print(f"Fetching {url} ...")
        r = engine.get(url)
        if r:
            events = engine.parse_oddsportal(r.text, str(r.url))
            print(f"Found {len(events)} events")
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(events, indent=2, ensure_ascii=False))
            print(f"✓ Output written to {out_path}")
        else:
            print("✗ Failed to fetch page")


if __name__ == "__main__":
    main()

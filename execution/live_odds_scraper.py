#!/usr/bin/env python3
"""WinBet Live Odds Scraper — Playwright-based scraper with smart waiting.

This script waits for dynamic content to load and intercepts API responses.
Designed for sites that serve odds via JavaScript/React/Vue after initial page load.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright", "beautifulsoup4"]
# ///

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

async def scrape_oddsportal_smart(url: str, output: Path) -> None:
    """Scrape OddsPortal/CentroQuote with smart waiting and API interception."""
    print(f"🌐 Scraping {url} with smart waiting...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            timezone_id="Europe/Rome",
        )

        page = await context.new_page()

        # Intercept all network responses
        api_responses = []
        async def handle_response(response):
            try:
                if response.status == 200 and "json" in (response.headers.get("content-type", "")):
                    body = await response.json()
                    api_responses.append({"url": response.url, "body": body})
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as exc:
            print(f"  ⚠ Navigation warning (continuing): {exc}")
            # Try domcontentloaded as fallback
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

        # Wait a bit for any lazy-loaded content
        await asyncio.sleep(3)

        # Try multiple selectors for event rows
        selectors = [
            "div.eventRow",
            "div[class*='eventRow']",
            "tr.deactivate",
            "div[class*='match-row']",
            "[data-testid='event-row']",
            "tr[class*='event']",
            "div.event",
        ]

        found_selector = None
        for sel in selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    found_selector = sel
                    print(f"  ✓ Found {count} rows with selector: {sel}")
                    break
            except Exception:
                continue

        events = []
        if found_selector:
            rows = await page.locator(found_selector).all()
            for row in rows[:30]:  # Limit to first 30
                try:
                    # Extract text content
                    text = await row.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]

                    # Try to find team names and odds
                    teams = []
                    odds = []
                    for line in lines:
                        # Odds are typically numbers like 1.95, 2.10, 3.50
                        if re.match(r'^\d+[\.,]\d+$', line.replace(',', '.')):
                            try:
                                odds.append(float(line.replace(',', '.')))
                            except:
                                pass
                        # Team names are longer text without numbers at start
                        elif len(line) > 2 and not re.match(r'^\d+[\.,]', line) and not line in ['-', 'vs', '–']:
                            teams.append(line)

                    if len(teams) >= 2 and len(odds) >= 2:
                        events.append({
                            "home_team": teams[0],
                            "away_team": teams[1],
                            "odds": odds[:3],
                            "raw_text": " | ".join(lines[:5]),
                        })
                except Exception:
                    continue

        # Also try to get content after scrolling
        if not events:
            print("  🔍 No events from selectors, trying full page content...")
            html = await page.content()
            # Try to parse with BeautifulSoup
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Look for common patterns
            for sel in selectors:
                rows = soup.select(sel)
                if rows:
                    print(f"  ✓ BS4 found {len(rows)} rows with: {sel}")
                    for row in rows[:20]:
                        text = row.get_text(separator="\n")
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        teams = []
                        odds = []
                        for line in lines:
                            if re.match(r'^\d+[\.,]\d+$', line.replace(',', '.')):
                                try:
                                    odds.append(float(line.replace(',', '.')))
                                except:
                                    pass
                            elif len(line) > 2 and not re.match(r'^\d+[\.,]', line):
                                teams.append(line)
                        if len(teams) >= 2 and len(odds) >= 2:
                            events.append({
                                "home_team": teams[0],
                                "away_team": teams[1],
                                "odds": odds[:3],
                                "raw_text": " | ".join(lines[:5]),
                            })
                    break

        # Check intercepted API responses for odds data
        print(f"  📡 Intercepted {len(api_responses)} JSON responses")
        api_events = []
        for resp in api_responses:
            url = resp["url"]
            body = resp["body"]
            if isinstance(body, list):
                for item in body:
                    if isinstance(item, dict):
                        home = item.get("homeTeam") or item.get("home") or item.get("team1")
                        away = item.get("awayTeam") or item.get("away") or item.get("team2")
                        if home and away:
                            api_events.append({
                                "home_team": str(home),
                                "away_team": str(away),
                                "source": "api_intercept",
                                "api_url": url,
                            })
            elif isinstance(body, dict):
                # Try common keys
                for key in ["events", "matches", "data", "items", "results"]:
                    if key in body and isinstance(body[key], list):
                        for item in body[key]:
                            if isinstance(item, dict):
                                home = item.get("homeTeam") or item.get("home") or item.get("team1")
                                away = item.get("awayTeam") or item.get("away") or item.get("team2")
                                if home and away:
                                    api_events.append({
                                        "home_team": str(home),
                                        "away_team": str(away),
                                        "source": "api_intercept",
                                        "api_url": url,
                                    })

        await browser.close()

        result = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "selector_used": found_selector,
            "events_from_dom": len(events),
            "events_from_api": len(api_events),
            "api_responses_count": len(api_responses),
            "events": events,
            "api_events": api_events,
            "api_urls": [r["url"] for r in api_responses],
        }

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n✓ Results written to {output}")
        print(f"  DOM events: {len(events)}")
        print(f"  API events: {len(api_events)}")

        if events:
            print("\n  Sample events:")
            for e in events[:3]:
                print(f"    {e['home_team']} vs {e['away_team']} — odds: {e['odds']}")


def main():
    parser = argparse.ArgumentParser(description="WinBet Live Odds Scraper")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    asyncio.run(scrape_oddsportal_smart(args.url, Path(args.output)))


if __name__ == "__main__":
    main()

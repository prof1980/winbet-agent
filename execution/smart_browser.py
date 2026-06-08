#!/usr/bin/env python3
"""WinBet Smart Browser Scraper — Scraping avanzato con anti-bot bypass.

Uso: python3 smart_browser.py --bookmaker snai --competition serie-a --output /tmp/result.json

Strategia:
  1. Playwright con context persistente (cookie, localStorage)
  2. Stealth avanzato: webdriver patch, canvas fingerprint, timezone
  3. Navigazione umana: click, scroll, attesa variabile
  4. Multi-strategy: API intercept → DOM parsing → screenshot OCR
  5. Auto-cookie e sessione gestita
"""

import argparse
import asyncio
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configurazione per bookmaker
# ---------------------------------------------------------------------------

BOOKMAKERS = {
    "snai": {
        "name": "SNAI",
        "url": "https://www.snai.it/scommesse/calcio/italia/serie-a",
        "url_template": "https://www.snai.it/scommesse/calcio/{competition}",
        "competitions": {
            "serie-a": "italia/serie-a",
            "serie-b": "italia/serie-b",
            "champions-league": "champions-league",
            "premier-league": "inghilterra/premier-league",
            "la-liga": "spagna/la-liga",
            "bundesliga": "germania/bundesliga",
            "ligue-1": "francia/ligue-1",
        },
        "api_patterns": ["/api/", "/prematch", "/sport/", "/event", "/quota", "/odds"],
        "selectors": {
            "event_container": "[class*='event-list-item'], .event-item, [data-testid*='event']",
            "event_rows": "[class*='event-row'], [class*='match-row'], [class*='event-list-item']",
            "home_team": "[class*='home-team'], [class*='team-home'], [class*='team1']",
            "away_team": "[class*='away-team'], [class*='team-away'], [class*='team2']",
            "odds_1": "[class*='quota-1'], [class*='odd-1'], [data-odds='1']",
            "odds_x": "[class*='quota-X'], [class*='odd-X'], [data-odds='X']",
            "odds_2": "[class*='quota-2'], [class*='odd-2'], [data-odds='2']",
            "match_date": "[class*='match-date'], [class*='event-time'], time",
        }
    },
    "eurobet": {
        "name": "Eurobet",
        "url": "https://www.eurobet.it/it/scommesse/calcio/italia/serie-a",
        "url_template": "https://www.eurobet.it/it/scommesse/calcio/{competition}",
        "competitions": {
            "serie-a": "italia/serie-a",
            "champions-league": "europa/champions-league",
            "premier-league": "inghilterra/premier-league",
        },
        "api_patterns": ["/api/", "/sport/", "/detail-service/", "/prematch"],
    },
    "goldbet": {
        "name": "Goldbet",
        "url": "https://www.goldbet.it/scommesse/calcio",
        "competitions": {},
        "api_patterns": ["/api/", "/sport/", "/event"],
    },
    "oddsportal": {
        "name": "OddsPortal",
        "url": "https://www.oddsportal.com/matches/football/italy/serie-a",
        "url_template": "https://www.oddsportal.com/matches/football/{competition}",
        "competitions": {
            "serie-a": "italy/serie-a",
            "premier-league": "england/premier-league",
            "la-liga": "spain/laliga",
            "bundesliga": "germany/bundesliga",
            "champions-league": "europe/champions-league",
        },
        "api_patterns": ["/ajax-", "/feed", "/data/"],
    }
}

# ---------------------------------------------------------------------------
# Stealth script injection
# ---------------------------------------------------------------------------

STEALTH_SCRIPT = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fake plugins
Object.defineProperty(navigator, 'plugins', { get: () => [
    {name: 'Chrome PDF Plugin'}, {name: 'Native Client'},
    {name: 'Widevine Content Decryption Module'}
]});

// Fake mimeTypes
Object.defineProperty(navigator, 'mimeTypes', { get: () => [
    {type: 'application/pdf'}, {type: 'application/x-google-chrome-pdf'},
    {type: 'application/vnd.google.chrome.pepflashplayer'}
]});

// Languages
Object.defineProperty(navigator, 'languages', { get: () => ['it-IT', 'it', 'en-US', 'en'] });

// Canvas noise (anti-fingerprinting)
const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData = function(...args) {
    const imageData = originalGetImageData.apply(this, args);
    for (let i = 0; i < imageData.data.length; i += 4) {
        imageData.data[i] += Math.random() < 0.5 ? 1 : -1;
    }
    return imageData;
};

// WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';  // UNMASKED_VENDOR_WEBGL
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';  // UNMASKED_RENDERER_WEBGL
    return getParameter(parameter);
};

// Notification permission
const originalQuery = window.Notification?.permission;
if (window.Notification) {
    Object.defineProperty(Notification, 'permission', { get: () => 'default' });
}

// Permissions API
const originalPermissionsQuery = navigator.permissions?.query;
if (originalPermissionsQuery) {
    navigator.permissions.query = function(parameters) {
        return originalPermissionsQuery.call(this, parameters).then(result => {
            if (parameters.name === 'notifications') {
                return Object.create(result, { state: { value: 'prompt' } });
            }
            return result;
        });
    };
}
"""

# ---------------------------------------------------------------------------
# Human-like interaction helpers
# ---------------------------------------------------------------------------

async def human_scroll(page):
    """Scroll umano: scroll piccoli con pause variabili."""
    for _ in range(random.randint(3, 7)):
        await page.evaluate(f"window.scrollBy(0, {random.randint(200, 600)})")
        await asyncio.sleep(random.uniform(0.3, 1.2))
    # Scroll back up a bit
    await page.evaluate(f"window.scrollBy(0, -{random.randint(300, 800)})")
    await asyncio.sleep(random.uniform(0.2, 0.5))

async def human_click(page, selector):
    """Click con movimento del mouse realistico."""
    try:
        element = page.locator(selector).first
        if await element.is_visible(timeout=2000):
            # Muovi il mouse sopra l'elemento prima di cliccare
            box = await element.bounding_box()
            if box:
                await page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                await asyncio.sleep(random.uniform(0.1, 0.4))
            await element.click()
            return True
    except Exception:
        pass
    return False

async def accept_cookies(page):
    """Tenta di accettare i cookie banner."""
    cookie_selectors = [
        "button:has-text('Accetta')",
        "button:has-text('Accetta tutti')",
        "button:has-text('Accetto')",
        "button:has-text('Conferma')",
        "[data-testid='cookie-accept']",
        "#onetrust-accept-btn-handler",
        "button[id*='cookie']",
        "button[class*='cookie']",
        "a:has-text('Accetta')",
    ]
    for sel in cookie_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(timeout=5000)
                print("   ✅ Cookie banner accettato")
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue
    print("   ℹ️  Nessun cookie banner trovato")

# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def extract_events_from_dom(html_content: str, bookmaker_key: str) -> list[dict]:
    """Estrae eventi e quote dall'HTML."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []
    
    config = BOOKMAKERS.get(bookmaker_key, {})
    selectors = config.get("selectors", {})
    
    # Cerca container eventi
    event_rows = soup.select(selectors.get("event_rows", "[class*='event']"))
    
    if not event_rows:
        # Fallback: cerca qualsiasi struttura tabellare con squadre
        event_rows = soup.find_all(['tr', 'div', 'li'], class_=re.compile(r'(event|match|partita|gioco)', re.I))
    
    for row in event_rows:
        # Estrai squadre
        home = None
        away = None
        
        # Prova i selettori configurati
        home_el = row.select_one(selectors.get("home_team", ""))
        away_el = row.select_one(selectors.get("away_team", ""))
        
        if home_el and away_el:
            home = home_el.get_text(strip=True)
            away = away_el.get_text(strip=True)
        else:
            # Euristico: cerca testi in maiuscolo che sembrano nomi squadre
            texts = [t.strip() for t in row.stripped_strings if len(t.strip()) > 2]
            if len(texts) >= 2:
                home, away = texts[0], texts[1]
        
        if not home or not away or home == away:
            continue
        
        # Estrai quote
        odds = {}
        odds_els = row.find_all(text=re.compile(r'\d+[.,]\d+'))
        for i, el in enumerate(odds_els[:3]):
            try:
                val = float(el.strip().replace(',', '.'))
                if 1.0 < val < 50.0:
                    key = ['1', 'X', '2'][i] if i < 3 else str(i)
                    odds[key] = val
            except (ValueError, IndexError):
                continue
        
        # Estrai data
        date_str = ""
        time_el = row.find(['time', 'span', 'div'], class_=re.compile(r'(time|date|ora)', re.I))
        if time_el:
            date_str = time_el.get_text(strip=True)
        
        if odds:
            events.append({
                "home_team": home,
                "away_team": away,
                "start_time": date_str,
                "odds": odds,
                "source": bookmaker_key,
            })
    
    return events

# ---------------------------------------------------------------------------
# Browser setup
# ---------------------------------------------------------------------------

async def setup_browser(playwright, headless: bool = False, profile_dir: Path = None):
    """Configura un browser Playwright con massima stealth."""
    
    # Crea o riutilizza un profilo persistente
    if profile_dir is None:
        profile_dir = Path("/mnt/c/Users/angel/WinBet/.tmp/playwright_profile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-extensions",
            "--disable-default-apps",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
        ],
        viewport={"width": 1920, "height": 1080},
        locale="it-IT",
        timezone_id="Europe/Rome",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        java_script_enabled=True,
        bypass_csp=True,
    )
    
    # Aggiungi script stealth a tutte le pagine
    await browser.add_init_script(STEALTH_SCRIPT)
    
    return browser

# ---------------------------------------------------------------------------
# Main scraping logic
# ---------------------------------------------------------------------------

async def scrape_bookmaker(bookmaker: str, competition: str, output: str, headless: bool = True, timeout: int = 60):
    """Scrape un bookmaker con strategie multiple."""
    
    config = BOOKMAKERS.get(bookmaker)
    if not config:
        print(f"❌ Bookmaker '{bookmaker}' non configurato")
        return {"error": "Bookmaker sconosciuto"}
    
    # Costruisci URL
    comp_path = config.get("competitions", {}).get(competition, "")
    if comp_path:
        url = config["url_template"].format(competition=comp_path)
    else:
        url = config["url"]
    
    print(f"📊 Scraping {config['name']} | {competition}")
    print(f"🌐 URL: {url}")
    print(f"🔒 Headless: {headless}")
    
    from playwright.async_api import async_playwright
    
    result = {
        "bookmaker": bookmaker,
        "competition": competition,
        "url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "events": [],
        "errors": [],
        "strategy": "",
    }
    
    async with async_playwright() as p:
        # Setup browser
        browser = await setup_browser(p, headless=headless)
        
        try:
            page = await browser.new_page()
            
            # Intercetta le richieste di rete
            api_responses = []
            async def handle_response(response):
                try:
                    url = response.url
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type.lower():
                        body = await response.json()
                        api_responses.append({"url": url, "body": body, "status": response.status})
                except Exception:
                    pass
            
            page.on("response", handle_response)
            
            # Navigazione con retry
            print("   🚀 Navigazione...")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"   ⚠️  Navigation warning: {e}")
                result["errors"].append(f"Navigazione: {e}")
            
            # Accetta cookie
            print("   🍪 Gestione cookie...")
            await accept_cookies(page)
            
            # Attesa anti-bot
            wait_time = random.uniform(4.0, 8.0)
            print(f"   ⏳ Attesa {wait_time:.1f}s anti-bot...")
            await asyncio.sleep(wait_time)
            
            # Scroll per caricare contenuto lazy
            print("   📜 Scroll pagina...")
            await human_scroll(page)
            
            # Attesa contenuto
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Screenshot per debug
            screenshot_path = f"/mnt/c/Users/angel/WinBet/.tmp/screenshot_{bookmaker}_{competition}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"   📸 Screenshot: {screenshot_path}")
            
            # Estrai HTML
            html = await page.content()
            print(f"   📄 HTML caricato: {len(html)} bytes")
            
            # Salva HTML per debug
            html_path = f"/mnt/c/Users/angel/WinBet/.tmp/html_{bookmaker}_{competition}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            # Strategia 1: Parse API responses
            if api_responses:
                print(f"   🎯 {len(api_responses)} risposte API intercettate")
                for resp in api_responses:
                    events = try_parse_api_response(resp["body"], bookmaker)
                    if events:
                        result["events"].extend(events)
                        result["strategy"] = "api_intercept"
                        print(f"   ✅ {len(events)} eventi da API")
            
            # Strategia 2: Parse DOM
            if not result["events"]:
                print("   🔍 Parsing DOM...")
                events = extract_events_from_dom(html, bookmaker)
                if events:
                    result["events"].extend(events)
                    result["strategy"] = "dom_parse"
                    print(f"   ✅ {len(events)} eventi da DOM")
                else:
                    result["errors"].append("Nessun evento trovato nel DOM")
                    print("   ⚠️  Nessun evento trovato nel DOM")
            
            # Deduplica
            seen = set()
            unique = []
            for ev in result["events"]:
                key = f"{ev.get('home_team','')} vs {ev.get('away_team','')}"
                if key not in seen:
                    seen.add(key)
                    unique.append(ev)
            result["events"] = unique
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"   ❌ Errore: {e}")
        finally:
            await browser.close()
    
    # Scrivi output
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Risultato: {len(result['events'])} eventi | Strategy: {result['strategy']}")
    print(f"💾 Output: {output}")
    return result


def try_parse_api_response(data: Any, bookmaker: str) -> list[dict]:
    """Prova a parsare una risposta API in eventi."""
    events = []
    
    if not isinstance(data, (dict, list)):
        return events
    
    # Cerca liste di eventi
    def search_events(obj, depth=0):
        if depth > 10:
            return
        if isinstance(obj, dict):
            # Cerca chiavi comuni per eventi
            for key in ["events", "matches", "partite", "data", "items", "results", "fixtures"]:
                if key in obj and isinstance(obj[key], list):
                    for item in obj[key]:
                        ev = parse_event_item(item)
                        if ev:
                            events.append(ev)
                    return
            # Ricorsione
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    search_events(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    ev = parse_event_item(item)
                    if ev:
                        events.append(ev)
                    else:
                        search_events(item, depth + 1)
    
    search_events(data)
    return events


def parse_event_item(item: dict) -> dict | None:
    """Prova a estrarre un evento da un dizionario."""
    if not isinstance(item, dict):
        return None
    
    # Cerca nomi squadre
    home_keys = ["home", "homeTeam", "home_team", "team1", "squadraCasa", "casa"]
    away_keys = ["away", "awayTeam", "away_team", "team2", "squadraTrasferta", "trasferta"]
    
    home = None
    away = None
    for k in home_keys:
        if k in item:
            home = str(item[k])
            break
    for k in away_keys:
        if k in item:
            away = str(item[k])
            break
    
    if not home or not away:
        return None
    
    # Estrai quote
    odds = {}
    for key in ["odds", "quote", "prices", "markets"]:
        if key in item:
            odds_data = item[key]
            if isinstance(odds_data, dict):
                for k, v in odds_data.items():
                    if k in ["1", "X", "2"]:
                        try:
                            odds[k] = float(v)
                        except (ValueError, TypeError):
                            pass
            break
    
    return {
        "home_team": home,
        "away_team": away,
        "start_time": item.get("startTime", item.get("date", "")),
        "odds": odds,
        "source": "api",
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="WinBet Smart Browser Scraper")
    parser.add_argument("--bookmaker", required=True, choices=list(BOOKMAKERS.keys()), help="Bookmaker da scrapare")
    parser.add_argument("--competition", default="serie-a", help="Competizione")
    parser.add_argument("--output", required=True, help="File JSON di output")
    parser.add_argument("--headless", action="store_true", default=False, help="Browser headless (default: visibile)")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Browser visibile")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in secondi")
    
    args = parser.parse_args()
    
    # Se siamo in WSL senza display, forza headless con warning
    display = subprocess.run(["echo", "$DISPLAY"], capture_output=True, text=True, shell=True)
    if not args.headless and not display.stdout.strip():
        print("⚠️  DISPLAY non trovato, forzo headless. Per visibile usa: export DISPLAY=:99")
        args.headless = True
    
    result = asyncio.run(scrape_bookmaker(
        args.bookmaker,
        args.competition,
        args.output,
        headless=args.headless,
        timeout=args.timeout
    ))
    
    if result.get("events"):
        print("\n📋 Prime 3 partite:")
        for ev in result["events"][:3]:
            print(f"   • {ev['home_team']} vs {ev['away_team']} — Quote: {ev.get('odds', {})}")
    else:
        print("\n⚠️  Nessun evento estratto. Verifica screenshot per diagnostica.")

if __name__ == "__main__":
    main()

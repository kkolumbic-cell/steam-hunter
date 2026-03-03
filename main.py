import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urlparse, unquote, urljoin
from datetime import datetime
import os
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# --- CONFIGURATION ---
DB_FILE = 'database.json'
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com', 'yahoo.com', 'hotmail.com']

TARGET_TAGS = [
    'strategy', 'base building', 'colony sim', 'economy', 'city builder', 
    'resource management', 'management', 'grand strategy', 'tower defense', 
    'turn-based strategy', 'turn-based tactics', 'tactical rpg', 'turn-based combat', 
    'tactical', 'real time tactics', 'psychological horror', 'horror', 'survival horror'
]

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

def parse_steam_date(date_str):
    date_str = date_str.strip()
    if not date_str or "coming" in date_str.lower() or "tba" in date_str.lower() or "wishlist" in date_str.lower() or "to be announced" in date_str.lower():
        return datetime(2099, 12, 31)
    
    formats = ['%d %b, %Y', '%b %d, %Y', '%b %Y', '%Y']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime(1900, 1, 1)

def filter_emails(emails, site_url):
    site_domain = ""
    try:
        netloc = urlparse(site_url).netloc.lower()
        site_domain = netloc[4:] if netloc.startswith('www.') else netloc
    except: pass
    clean = [e.lower() for e in emails if (site_domain and site_domain in e.lower()) or (e.lower().split('@')[-1] in TRUSTED_PROVIDERS)]
    return list(set(clean))

def save_data(database):
    current_refresh_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    with open(DB_FILE, 'w') as f:
        json.dump(database, f, indent=4)
    
    sorted_games = sorted(database.values(), key=lambda x: parse_steam_date(x.get('Date', '')), reverse=True)
    visible_games_count = sum(1 for g in database.values() if g.get('Email') or g.get('Discord') or g.get('Site'))

    html = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
        body {{ background: #0b0e14; color: #d1d1d1; font-family: sans-serif; padding: 15px; }}
        .stats-bar {{ background: #2a475e; padding: 10px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; border-left: 5px solid #a3da00; }}
        .game-row {{ background: #1a1f26; margin: 5px 0; padding: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; border-left: 5px solid #3a4453; }}
        .game-info {{ display: flex; align-items: center; }}
        .game-thumb {{ width: 60px; height: auto; margin-right: 15px; border-radius: 2px; }}
        .game-title-link {{ color: inherit; text-decoration: none; font-weight: bold; font-size: 1.1em; }}
        .game-title-link:hover {{ color: #66c0f4; }}
        .email {{ color: #a3da00; font-weight: bold; }}
        a {{ color: #66c0f4; text-decoration: none; }}
        .date-header {{ color: #66c0f4; margin-top: 25px; border-bottom: 1px solid #333; }}
        .spacer {{ display: inline-block; width: 20px; }}
    </style></head><body>
    <div class='stats-bar'>
        <b>Bot Status:</b> Active <span style='color:#a3da00;'>●</span> | 
        <b>Last Refresh:</b> {current_refresh_time} | 
        <b>Actionable Leads:</b> {visible_games_count}
    </div>"""

    curr_date = ""
    for g in sorted_games:
        if not g.get('Email') and not g.get('Discord') and not g.get('Site'):
            continue

        date = g.get('Date', 'TBA')
        if date != curr_date:
            curr_date = date
            html += f"<h3 class='date-header'>{curr_date}</h3>"
        
        links = []
        if g.get('Email'): links.append(f"<span class='email'>{g['Email']}</span>")
        if g.get('Discord'): links.append(f"<a href='{g['Discord']}' target='_blank'>Discord</a>")
        if g.get('Site'): links.append(f"<a href='{g['Site']}' target='_blank'>Site</a>")
        
        html += f"""<div class='game-row'>
            <div class='game-info'>
                <img src='{g.get('Thumb', '')}' class='game-thumb'>
                <a href='{g.get('URL', '#')}' target='_blank' class='game-title-link'>{g.get('Title', 'Unknown')}</a>
            </div>
            <span>{"<span class='spacer'></span>".join(links)}</span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</body></html>")

def run_script():
    with open("last_run.txt", "w") as f:
        f.write(f"Scraper last active: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: database = json.load(f)
            except: database = {}

    req_session = requests.Session()
    req_session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    print("--- Firing up Playwright Browser with Stealth ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        context.add_cookies([
            {"name": "birthtime", "value": "631180801", "domain": "store.steampowered.com", "path": "/"},
            {"name": "lastagecheckage", "value": "1-0-1990", "domain": "store.steampowered.com", "path": "/"},
            {"name": "wants_mature_content", "value": "1", "domain": "store.steampowered.com", "path": "/"}
        ])
        
        page = context.new_page()
        
        # Apply the stealth cloaking to the page
        stealth_sync(page)

        print("--- Fetching Latest SteamDB Events ---")
        try:
            page.goto("https://steamdb.info/history/events/?type=game", timeout=30000)
            page.wait_for_timeout(5000)
            
            # --- DEBUGGING: Let's see what the page actually is ---
            print(f"DEBUG - The page title is: {page.title()}")
            
            html_content = page.content()
            
            # Save the HTML so we can review it on GitHub if it fails
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(html_content)
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            app_links = soup.select('a[href^="/app/"]')
            app_ids = list(set([link['href'].split('/')[2] for link in app_links if link['href'].split('/')[2].isdigit()]))
            
            print(f"Found {len(app_ids)} newly updated/added apps. Processing...")

            for app_id in app_ids:
                if app_id in database and database[app_id].get('Email'):
                    continue

                steamdb_app_url = f"https://steamdb.info/app/{app_id}/"
                page.goto(steamdb_app_url, timeout=30000)
                page.wait_for_timeout(3000) 
                
                db_soup = BeautifulSoup(page.content(), 'html.parser')
                tag_elements = db_soup.select('a[href^="/tags/"]')
                game_tags = [t.text.strip().lower() for t in tag_elements]
                
                has_target_tag = any(tag in game_tags for tag in TARGET_TAGS)
                
                if not has_target_tag:
                    continue

                print(f"Matched App ID: {app_id} (Tags: {', '.join([t for t in game_tags if t in TARGET_TAGS])})")
                
                steam_url = f"https://store.steampowered.com/app/{app_id}/"
                page.goto(steam_url, timeout=30000)
                page.wait_for_timeout(3000)
                
                s_soup = BeautifulSoup(page.content(), 'html.parser')
                
                title_el = s_soup.select_one('.apphub_AppName')
                title = title_el.text.strip() if title_el else f"Unknown Game ({app_id})"
                
                date_el = s_soup.select_one('.release_date .date')
                release_date = date_el.text.strip() if date_el else "TBA"
                
                thumb_el = s_soup.select_one('.game_header_image_full')
                thumb = thumb_el['src'] if thumb_el else ""

                game_info = database.get(app_id, {
                    'Title': title, 'Date': release_date, 'Email': '', 'Discord': '', 
                    'URL': steam_url, 'Site': '', 'Thumb': thumb
                })

                for link in s_soup.select('.apphub_OtherSiteInfo a'):
                    txt, href = link.get_text().lower(), link.get('href', '')
                    if 'website' in txt or 'official site' in txt:
                        found_site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                        if 'steampowered' not in found_site:
                            game_info['Site'] = found_site
                    if 'discord' in txt or 'discord.gg' in href:
                        game_info['Discord'] = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href

                if game_info['Site']:
                    try:
                        site_res = req_session.get(game_info['Site'], headers=get_headers(), timeout=10)
                        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', site_res.text)
                        
                        if not emails:
                            site_soup = BeautifulSoup(site_res.text, 'html.parser')
                            for s_link in site_soup.find_all('a', href=True):
                                s_txt, s_href = s_link.get_text().lower(), s_link['href']
                                if any(k in s_txt or k in s_href.lower() for k in ['contact', 'about', 'support', 'impressum']):
                                    contact_url = urljoin(game_info['Site'], s_href)
                                    c_res = req_session.get(contact_url, headers=get_headers(), timeout=10)
                                    emails += re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', c_res.text)
                                    if emails: break
                        
                        clean = filter_emails(emails, game_info['Site'])
                        if clean: game_info['Email'] = ", ".join(clean)
                    except: pass
                
                database[app_id] = game_info
                save_data(database)
                
        except Exception as e:
            print(f"Critical error during scrape: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run_script()

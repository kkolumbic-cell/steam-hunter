import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urlparse, unquote, urljoin
from datetime import datetime
import os
import random

# --- CONFIGURATION ---
DB_FILE = 'database.json'
APP_LIST_FILE = 'app_list.json' # Our baseline memory of known Steam games
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

    print("--- Fetching Master Steam App List ---")
    data = None
    endpoints = [
        "https://api.steampowered.com/ISteamApps/GetAppList/v2/",
        "https://community.steam-api.com/ISteamApps/GetAppList/v2/"
    ]
    
    # Try our redundant API endpoints
    for api_url in endpoints:
        try:
            print(f"Connecting to: {api_url}")
            res = req_session.get(api_url, headers=get_headers(), timeout=30)
            
            # Ensure the server gave us a success code AND actual JSON data
            if res.status_code == 200 and 'json' in res.headers.get('Content-Type', '').lower():
                data = res.json()
                print("Successfully fetched Master List.")
                break
            else:
                print(f"Failed. Status: {res.status_code}. Retrying next endpoint...")
        except Exception as e:
            print(f"Error connecting: {e}")
        time.sleep(2) # Brief pause before hitting the backup API
        
    if not data or 'applist' not in data:
        print("Critical error: All Steam API endpoints were blocked or failed. Stopping execution to prevent database corruption.")
        return

    try:
        current_app_ids = set([str(app['appid']) for app in data.get('applist', {}).get('apps', [])])
        print(f"Total apps currently on Steam: {len(current_app_ids)}")
        
        known_app_ids = set()
        if os.path.exists(APP_LIST_FILE):
            with open(APP_LIST_FILE, 'r') as f:
                try: known_app_ids = set(json.load(f))
                except: known_app_ids = set()
                
        # The Initialization Trick
        if not known_app_ids:
            print(f"Initialization run detected. Saving {len(current_app_ids)} apps to baseline.")
            with open(APP_LIST_FILE, 'w') as f:
                json.dump(list(current_app_ids), f)
            print("Baseline saved! The next scheduled run will detect newly added games.")
            return

        # Mathematical Difference
        new_app_ids = current_app_ids - known_app_ids
        print(f"Found {len(new_app_ids)} brand new App IDs since last run. Processing...")

        for app_id in new_app_ids:
            if app_id in database and database[app_id].get('Email'):
                continue

            time.sleep(random.uniform(1.5, 3.0)) 
            
            steam_url = f"https://store.steampowered.com/app/{app_id}/"
            s_res = req_session.get(steam_url, headers=get_headers(), timeout=15)
            
            if s_res.url != steam_url and not s_res.url.startswith(steam_url):
                continue
                
            s_soup = BeautifulSoup(s_res.text, 'html.parser')
            
            tag_elements = s_soup.select('.app_tag')
            game_tags = [t.text.strip().lower() for t in tag_elements if t.text.strip() != '+']
            
            has_target_tag = any(tag in game_tags for tag in TARGET_TAGS)
            
            if not has_target_tag:
                continue

            print(f"Matched App ID: {app_id} (Tags: {', '.join([t for t in game_tags if t in TARGET_TAGS])})")
            
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
            
        # Update the baseline at the very end so we are ready for the next 6-hour window
        with open(APP_LIST_FILE, 'w') as f:
            json.dump(list(current_app_ids), f)
            
    except Exception as e:
        print(f"Critical error during scrape: {e}")

if __name__ == "__main__":
    run_script()

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
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com', 'yahoo.com', 'hotmail.com']

# The genres we WANT. If it has any of these, it stays.
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
    
    # Save the full database unconditionally
    with open(DB_FILE, 'w') as f:
        json.dump(database, f, indent=4)
    
    sorted_games = sorted(database.values(), key=lambda x: parse_steam_date(x.get('Date', '')), reverse=True)
    visible_games_count = len(sorted_games)

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
        <b>Tracked Games:</b> {visible_games_count}
    </div>"""

    curr_date = ""
    for g in sorted_games:
        # NO LONGER FILTERING GAMES WITHOUT CONTACTS. ALL MATCHES ARE DISPLAYED.
        date = g.get('Date', 'TBA')
        if date != curr_date:
            curr_date = date
            html += f"<h3 class='date-header'>{curr_date}</h3>"
        
        links = []
        if g.get('Email'): links.append(f"<span class='email'>{g['Email']}</span>")
        if g.get('Discord'): links.append(f"<a href='{g['Discord']}' target='_blank'>Discord</a>")
        if g.get('Site'): links.append(f"<a href='{g['Site']}' target='_blank'>Site</a>")
        
        # If the bot found absolutely nothing, explicitly state it so the team knows they need to dig manually
        if not links:
            links.append("<span style='color: #888;'>No contacts found</span>")
            
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
    API_KEY = os.environ.get('STEAM_API_KEY')
    if not API_KEY:
        print("Critical Error: STEAM_API_KEY environment variable is not set.")
        return

    current_time = int(time.time())
    
    # FRESH START LOGIC
    # If last_run.txt is deleted, we completely wipe the database and set the clock to NOW.
    if not os.path.exists('last_run.txt'):
        print("Fresh Start Triggered: Deleting historical database and setting baseline to current time.")
        with open('last_run.txt', 'w') as f:
            f.write(str(current_time))
        with open(DB_FILE, 'w') as f:
            json.dump({}, f)
        save_data({}) # Updates the HTML to be completely blank
        print("Wipe complete. The bot will hunt for strictly new games on the next scheduled run.")
        return

    # If it's a normal run, read the last timestamp
    try:
        with open('last_run.txt', 'r') as f:
            content = f.read().strip()
            last_timestamp = int(content) if content.isdigit() else (current_time - (6 * 3600))
    except:
        last_timestamp = current_time - (6 * 3600)

    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: database = json.load(f)
            except: database = {}

    req_session = requests.Session()
    req_session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    print(f"--- Fetching apps modified since Unix Time: {last_timestamp} ---")
    
    api_url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={API_KEY}&if_modified_since={last_timestamp}&max_results=50000"
    
    try:
        res = req_session.get(api_url, headers=get_headers(), timeout=30)
        if res.status_code != 200:
            print(f"Failed to fetch from IStoreService. Status Code: {res.status_code}")
            return
            
        data = res.json()
        apps = data.get('response', {}).get('apps', [])
        
        new_app_ids = [str(app['appid']) for app in apps]
        print(f"API returned {len(new_app_ids)} updated/new App IDs in this time window. Processing...")

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
            
            # THE ONLY FILTER: Does it have any tag from our whitelist?
            if not any(good_tag in game_tags for good_tag in TARGET_TAGS):
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
            
        # Update the time marker for the next 6-hour cycle
        with open('last_run.txt', 'w') as f:
            f.write(str(current_time))
            
    except Exception as e:
        print(f"Critical error during scrape: {e}")

if __name__ == "__main__":
    run_script()

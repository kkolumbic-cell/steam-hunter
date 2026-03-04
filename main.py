import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urlparse, parse_qs, unquote, urljoin
from datetime import datetime
import os
import random

# --- CONFIGURATION ---
DB_FILE = 'database.json'
MASTER_LIST_FILE = 'master_list.json'
RECENT_GAMES_FILE = 'recent_games.json'
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com', 'yahoo.com', 'hotmail.com']

# --- THE SNIPER TEST ---
# We are forcing it to scan Korea: IL-2 Series to prove the global link extractor works
TEST_APP_IDS = ['247970']

TARGET_TAGS = [
    'strategy', 'base building', 'colony sim', 'economy', 'city builder', 
    'resource management', 'management', 'grand strategy', 'tower defense', 
    'turn-based strategy', 'turn-based tactics', 'tactical rpg', 'turn-based combat', 
    'tactical', 'real time tactics', 'psychological horror', 'horror', 'survival horror'
]

EXCLUDE_TAGS = ['nudity']

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

def get_clean_url(href):
    if 'linkfilter' in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if 'url' in qs:
                return qs['url'][0]
            elif 'u' in qs:
                return qs['u'][0]
        except:
            pass
    return href

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
    
    sorted_games = sorted(database.values(), key=lambda x: x.get('AddedDate', '2000-01-01'), reverse=True)
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
        .meta-info {{ font-size: 0.85em; color: #888; margin-top: 4px; }}
        .tag-highlight {{ color: #a3da00; }}
    </style></head><body>
    <div class='stats-bar'>
        <b>Bot Status:</b> Active <span style='color:#a3da00;'>●</span> | 
        <b>Last Refresh:</b> {current_refresh_time} | 
        <b>Tracked Games:</b> {visible_games_count}
    </div>"""

    curr_date = ""
    for g in sorted_games:
        date = g.get('AddedDate', 'Prior to Update')
        if date != curr_date:
            curr_date = date
            html += f"<h3 class='date-header'>Lead Found/Updated: {curr_date}</h3>"
        
        links = []
        if g.get('Email'): links.append(f"<span class='email'>{g['Email']}</span>")
        if g.get('Discord'): links.append(f"<a href='{g['Discord']}' target='_blank'>Discord</a>")
        if g.get('Site'): links.append(f"<a href='{g['Site']}' target='_blank'>Site</a>")
        
        if not links:
            links.append("<span style='color: #888;'>No contacts found</span>")
            
        tags_str = ", ".join(g.get('MatchedTags', ['Unknown']))
        release_str = g.get('Date', 'TBA')
            
        html += f"""<div class='game-row'>
            <div class='game-info'>
                <img src='{g.get('Thumb', '')}' class='game-thumb'>
                <div>
                    <a href='{g.get('URL', '#')}' target='_blank' class='game-title-link'>{g.get('Title', 'Unknown')}</a>
                    <div class='meta-info'>
                        <b>Release:</b> {release_str} <span class='spacer'></span> <b>Tags:</b> <span class='tag-highlight'>{tags_str}</span>
                    </div>
                </div>
            </div>
            <span>{"<span class='spacer'></span>".join(links)}</span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</body></html>")

def build_master_list(api_key, req_session):
    print("Building baseline memory of all historical Steam games. This takes a few seconds...")
    master_list = set()
    last_appid = 0
    while True:
        url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={api_key}&max_results=50000&last_appid={last_appid}"
        res = req_session.get(url, timeout=20)
        if res.status_code != 200:
            break
        data = res.json()
        apps = data.get('response', {}).get('apps', [])
        if not apps:
            break
        for app in apps:
            master_list.add(str(app['appid']))
            last_appid = app['appid']
    
    with open(MASTER_LIST_FILE, 'w') as f:
        json.dump(list(master_list), f)
    print(f"Baseline built! Memorized {len(master_list)} old games.")
    return master_list

def run_script():
    API_KEY = os.environ.get('STEAM_API_KEY')
    if not API_KEY:
        print("Critical Error: STEAM_API_KEY environment variable is not set.")
        return

    current_time = int(time.time())
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    req_session = requests.Session()
    req_session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: database = json.load(f)
            except: pass

    recent_games = []
    if os.path.exists(RECENT_GAMES_FILE):
        with open(RECENT_GAMES_FILE, 'r') as f:
            try: recent_games = json.load(f)
            except: pass

    if not os.path.exists(MASTER_LIST_FILE):
        build_master_list(API_KEY, req_session)
        with open('last_run.txt', 'w') as f:
            f.write(str(current_time))
        print("Initialization complete. Stopping execution. Next run will catch truly NEW games.")
        return

    master_list = set()
    with open(MASTER_LIST_FILE, 'r') as f:
        master_list = set(json.load(f))

    try:
        with open('last_run.txt', 'r') as f:
            content = f.read().strip()
            last_timestamp = int(content) if content.isdigit() else (current_time - (6 * 3600))
    except:
        last_timestamp = current_time - (6 * 3600)

    print(f"--- Fetching apps modified since Unix Time: {last_timestamp} ---")
    
    api_url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={API_KEY}&if_modified_since={last_timestamp}&max_results=50000"
    
    try:
        res = req_session.get(api_url, headers=get_headers(), timeout=30)
        if res.status_code != 200:
            print(f"Failed to fetch from IStoreService.")
            return
            
        data = res.json()
        apps = data.get('response', {}).get('apps', [])
        modified_app_ids = [str(app['appid']) for app in apps]
        
        apps_to_scrape = []
        for app_id in modified_app_ids:
            if app_id in database:
                if not database[app_id].get('Email'):
                    apps_to_scrape.append(app_id)
            elif app_id not in master_list:
                apps_to_scrape.append(app_id)
                master_list.add(app_id)
                recent_games.append(app_id)
            elif app_id in recent_games:
                apps_to_scrape.append(app_id)

        # Inject our Sniper Test IDs into the front of the line!
        for test_id in TEST_APP_IDS:
            if test_id not in apps_to_scrape:
                apps_to_scrape.insert(0, test_id)
            # Temporarily wipe its memory in the database so it scrapes entirely fresh
            if test_id in database:
                del database[test_id]

        if len(recent_games) > 500:
            recent_games = recent_games[-500:]

        print(f"API returned {len(modified_app_ids)} modified apps. Processing {len(apps_to_scrape)} new/dashboard apps (including test apps)...")

        for app_id in apps_to_scrape:
            time.sleep(random.uniform(1.5, 3.0)) 
            
            steam_url = f"https://store.steampowered.com/app/{app_id}/"
            s_res = req_session.get(steam_url, headers=get_headers(), timeout=15)
            
            if s_res.url != steam_url and not s_res.url.startswith(steam_url):
                continue
                
            s_soup = BeautifulSoup(s_res.text, 'html.parser')
            
            tag_elements = s_soup.select('.app_tag')
            game_tags = [t.text.strip().lower() for t in tag_elements if t.text.strip() != '+']
            
            if any(bad_tag in game_tags for bad_tag in EXCLUDE_TAGS):
                continue

            matched_tags = [t for t in game_tags if t in TARGET_TAGS]
            if not matched_tags:
                continue

            print(f"Matched/Updated App ID: {app_id}")
            
            title_el = s_soup.select_one('.apphub_AppName')
            title = title_el.text.strip() if title_el else f"Unknown Game ({app_id})"
            
            date_el = s_soup.select_one('.release_date .date')
            release_date = date_el.text.strip() if date_el else "TBA"
            
            thumb_el = s_soup.select_one('.game_header_image_full')
            thumb = thumb_el['src'] if thumb_el else ""

            game_info = database.get(app_id, {
                'Title': title, 'Email': '', 'Discord': '', 
                'URL': steam_url, 'Site': '', 'Thumb': thumb
            })
            
            game_info['Date'] = release_date
            game_info['AddedDate'] = today_str
            game_info['MatchedTags'] = matched_tags

            # --- THE FOOLPROOF GLOBAL LINK SCANNER ---
            for link in s_soup.find_all('a', href=True):
                txt = link.get_text().lower().strip()
                href = link.get('href', '')
                actual_url = get_clean_url(href)
                
                # Ignore internal Steam links so we don't accidentally log Steam's own support pages
                if 'steampowered.com' in actual_url or 'steamcommunity.com' in actual_url:
                    continue

                # 1. Grab Discord by checking the actual decoded URL
                if not game_info['Discord']:
                    if 'discord.gg' in actual_url or 'discord.com/invite' in actual_url:
                        game_info['Discord'] = actual_url
                
                # 2. Grab Website by looking for the words in your screenshot!
                if not game_info['Site']:
                    if 'website' in txt or 'official site' in txt:
                        # Ensure it's not a Discord/Twitter link masquerading as a website button
                        if 'discord' not in actual_url and 'twitter' not in actual_url:
                            game_info['Site'] = actual_url

            # Email hunting via the Official Website
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
            
        with open('last_run.txt', 'w') as f:
            f.write(str(current_time))
            
        with open(MASTER_LIST_FILE, 'w') as f:
            json.dump(list(master_list), f)
        with open(RECENT_GAMES_FILE, 'w') as f:
            json.dump(recent_games, f)
            
    except Exception as e:
        print(f"Critical error during scrape: {e}")

if __name__ == "__main__":
    run_script()

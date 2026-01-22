import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urlparse, unquote, parse_qs, urljoin
from datetime import datetime
import os

# --- CONFIGURATION ---
BASE_SEARCH_URL = "https://store.steampowered.com/search/results/?sort_by=_ASC&category1=998&os=win&supportedlang=english&filter=comingsoon"
BATCH_LIMIT = 50 
DB_FILE = 'database.json'
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com', 'yahoo.com', 'hotmail.com']

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://store.steampowered.com/'
    }

def get_base_domain(url):
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith('www.'): netloc = netloc[4:]
        return netloc
    except: return ""

def filter_emails(emails, site_url):
    site_domain = get_base_domain(site_url)
    clean = [e.lower() for e in emails if (site_domain and site_domain in e.lower()) or (e.lower().split('@')[-1] in TRUSTED_PROVIDERS)]
    return list(set(clean))

def save_data(database, stats):
    """Saves the JSON and generates the clean HTML dashboard."""
    with open(DB_FILE, 'w') as f:
        json.dump(database, f, indent=4)
    
    sorted_games = sorted(database.values(), key=lambda x: x.get('Date', ''), reverse=True)
    
    html = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
        body {{ background: #0b0e14; color: #d1d1d1; font-family: sans-serif; padding: 15px; }}
        .stats-bar {{ background: #2a475e; padding: 10px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; border-left: 5px solid #a3da00; }}
        .game-row {{ background: #1a1f26; margin: 5px 0; padding: 12px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; border-left: 5px solid #3a4453; }}
        /* RULE: Gray out rows with no contact info */
        .empty-row {{ opacity: 0.35; filter: grayscale(100%); }}
        .email {{ color: #a3da00; font-weight: bold; }}
        a {{ color: #66c0f4; text-decoration: none; }}
        .date-header {{ color: #66c0f4; margin-top: 25px; border-bottom: 1px solid #333; }}
        .spacer {{ display: inline-block; width: 35px; }} /* Rule: 5-space empty gap */
    </style></head><body>
    <div class='stats-bar'>
        <b>Sync:</b> {stats['success']}/{stats['total']} Scanned | 
        <b>Total:</b> {len(database)} | 
        <b>Updated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>"""

    curr_date = ""
    for g in sorted_games:
        release_date = g.get('Date', '')
        if release_date != curr_date:
            curr_date = release_date
            html += f"<h3 class='date-header'>{curr_date}</h3>"
        
        discord_url = g.get('Discord', '')
        site_url = g.get('Site', '')
        emails = g.get('Email', '')

        # Check if the row is empty (only has Steam URL)
        is_empty = not emails and not discord_url and not site_url
        row_class = "game-row empty-row" if is_empty else "game-row"

        # Formatting values: Show nothing if empty instead of "None"
        email_display = f"<span class='email'>{emails}</span>" if emails else ""
        discord_btn = f"<a href='{discord_url}'>Discord</a>" if discord_url else ""
        site_btn = f"<a href='{site_url}'>Site</a>" if site_url else ""
        
        # Build the data string with the requested spacers
        data_parts = [part for part in [email_display, discord_btn, site_btn] if part]
        data_string = "<span class='spacer'></span>".join(data_parts)
        
        html += f"""<div class='{row_class}'>
            <span><b>{g.get('Title', 'Unknown')}</b></span>
            <span>
                {data_string}
                <span class='spacer'></span>
                <a href='{g.get('URL', '#')}'>Steam</a>
            </span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</body></html>")

def run_script():
    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: 
                database = json.load(f)
                # Cleanup old data for the new UI rules
                for app_id in database:
                    for key in ['Email', 'Discord', 'Site']:
                        if database[app_id].get(key) == 'None':
                            database[app_id][key] = ''
            except: database = {}

    stats = {'total': 0, 'success': 0}
    session = requests.Session()
    session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    try:
        res = session.get(f"{BASE_SEARCH_URL}&start=0", headers=get_headers(), timeout=20)
        rows = BeautifulSoup(res.text, 'html.parser').select('.search_result_row')[:BATCH_LIMIT]
        stats['total'] = len(rows)

        for i, row in enumerate(rows):
            try:
                app_id = row['data-ds-appid']
                title = row.select_one('.title').text.strip()
                print(f"[{i+1}/{len(rows)}] Checking: {title}")
                
                game_info = database.get(app_id, {
                    'Title': title, 'Date': row.select_one('.search_released').text.strip(),
                    'Email': '', 'Discord': '', 'URL': row['href'].split('?')[0], 'Site': ''
                })

                p_res = session.get(game_info['URL'], headers=get_headers(), timeout=12)
                p_soup = BeautifulSoup(p_res.text, 'html.parser')
                
                for link in p_soup.find_all('a', href=True):
                    txt, href = link.get_text().lower(), link['href']
                    if 'website' in txt:
                        site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                        if 'steampowered' not in site:
                            game_info['Site'] = site
                            if not game_info['Email']:
                                try:
                                    s_res = session.get(site, headers=get_headers(), timeout=10)
                                    found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', s_res.text)
                                    clean = filter_emails(found, site)
                                    if clean: game_info['Email'] = ", ".join(clean)
                                except: pass
                    if 'discord' in txt or 'discord.gg' in href:
                        game_info['Discord'] = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href

                stats['success'] += 1
                database[app_id] = game_info
            except: pass
            
            time.sleep(4)

    finally:
        save_data(database, stats)

if __name__ == "__main__":
    run_script()

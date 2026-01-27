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
BATCH_LIMIT = 150 
DB_FILE = 'database.json'
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com', 'yahoo.com', 'hotmail.com']

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://store.steampowered.com/'
    }

def filter_emails(emails, site_url):
    site_domain = ""
    try:
        netloc = urlparse(site_url).netloc.lower()
        site_domain = netloc[4:] if netloc.startswith('www.') else netloc
    except: pass
    clean = [e.lower() for e in emails if (site_domain and site_domain in e.lower()) or (e.lower().split('@')[-1] in TRUSTED_PROVIDERS)]
    return list(set(clean))

def save_data(database):
    """Updates both the JSON database and the live HTML dashboard."""
    current_refresh_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    with open(DB_FILE, 'w') as f:
        json.dump(database, f, indent=4)
    
    sorted_games = sorted(database.values(), key=lambda x: x.get('Date', 'TBA'), reverse=True)
    
    html = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
        body {{ background: #0b0e14; color: #d1d1d1; font-family: sans-serif; padding: 15px; }}
        .stats-bar {{ background: #2a475e; padding: 10px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; border-left: 5px solid #a3da00; }}
        .game-row {{ background: #1a1f26; margin: 5px 0; padding: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; border-left: 5px solid #3a4453; }}
        .empty-row {{ opacity: 0.35; filter: grayscale(100%); }}
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
        <b>Total Database:</b> {len(database)}
    </div>"""

    curr_date = ""
    for g in sorted_games:
        date = g.get('Date', 'TBA')
        if date != curr_date:
            curr_date = date
            html += f"<h3 class='date-header'>{curr_date}</h3>"
        
        has_email = bool(g.get('Email'))
        has_discord = bool(g.get('Discord'))
        has_site = bool(g.get('Site'))
        
        row_class = "game-row"
        if not has_email and not has_discord and not has_site:
            row_class = "game-row empty-row"
        
        links = []
        if g.get('Email'): links.append(f"<span class='email'>{g['Email']}</span>")
        if g.get('Discord'): links.append(f"<a href='{g['Discord']}' target='_blank'>Discord</a>")
        if g.get('Site'): links.append(f"<a href='{g['Site']}' target='_blank'>Site</a>")
        
        html += f"""<div class='{row_class}'>
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

    session = requests.Session()
    session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    # Scans first 150 games across 3 pages
    for start in [0, 50, 100]:
        print(f"--- Systematic Scan: Batch {start} ---")
        try:
            search_url = f"https://store.steampowered.com/search/results/?sort_by=_ASC&category1=998&os=win&supportedlang=english&filter=comingsoon&start={start}"
            res = session.get(search_url, headers=get_headers(), timeout=20)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('.search_result_row')

            for row in rows:
                app_id = row['data-ds-appid']
                title = row.select_one('.title').text.strip()

                if app_id in database and database[app_id].get('Email'):
                    continue

                print(f"New Hunt: {title}")
                
                game_info = database.get(app_id, {
                    'Title': title, 
                    'Date': row.select_one('.search_released').text.strip(),
                    'Email': '', 'Discord': '', 'URL': row['href'].split('?')[0], 'Site': '',
                    'Thumb': row.select_one('.search_capsule img')['src'] if row.select_one('.search_capsule img') else ""
                })

                try:
                    p_res = session.get(game_info['URL'], headers=get_headers(), timeout=12)
                    p_soup = BeautifulSoup(p_res.text, 'html.parser')
                    
                    for link in p_soup.find_all('a', href=True):
                        txt, href = link.get_text().lower(), link['href']
                        if 'website' in txt or 'official site' in txt:
                            site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                            if 'steampowered' not in site:
                                game_info['Site'] = site
                                s_res = session.get(site, headers=get_headers(), timeout=10)
                                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', s_res.text)
                                clean = filter_emails(emails, site)
                                if clean: game_info['Email'] = ", ".join(clean)
                        if 'discord' in txt or 'discord.gg' in href:
                            game_info['Discord'] = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                    
                    database[app_id] = game_info
                    time.sleep(random.uniform(3.0, 6.0))
                except: pass
        except: pass
    
    save_data(database)

if __name__ == "__main__":
    run_script()

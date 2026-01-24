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
    with open(DB_FILE, 'w') as f:
        json.dump(database, f, indent=4)
    
    sorted_games = sorted(database.values(), key=lambda x: x.get('Date', ''), reverse=True)
    
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
        <b>Sync:</b> {stats['success']}/{stats['total']} Scanned | <b>Total:</b> {len(database)} | <b>Updated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>"""

    curr_date = ""
    for g in sorted_games:
        release_date = g.get('Date', '')
        if release_date != curr_date:
            curr_date = release_date
            html += f"<h3 class='date-header'>{curr_date}</h3>"
        
        discord_url = g.get('Discord', '')
        site_url = g.get('Site', '')
        contact_page = g.get('ContactPage', '')
        emails = g.get('Email', '')
        thumb = g.get('Thumb', '')

        is_empty = not emails and not discord_url and not site_url and not contact_page
        row_class = "game-row empty-row" if is_empty else "game-row"

        # Logic for right-side links with target='_blank'
        links_list = []
        if emails: links_list.append(f"<span class='email'>{emails}</span>")
        if discord_url: links_list.append(f"<a href='{discord_url}' target='_blank'>Discord</a>")
        if site_url: links_list.append(f"<a href='{site_url}' target='_blank'>Site</a>")
        if contact_page: links_list.append(f"<a href='{contact_page}' target='_blank'>Contact/About</a>")
        
        data_string = "<span class='spacer'></span>".join(links_list)
        
        html += f"""<div class='{row_class}'>
            <div class='game-info'>
                <img src='{thumb}' class='game-thumb'>
                <a href='{g.get('URL', '#')}' target='_blank' class='game-title-link'>{g.get('Title', 'Unknown')}</a>
            </div>
            <span>{data_string}</span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</body></html>")

def run_script():
    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: database = json.load(f)
            except: database = {}

    stats = {'total': 0, 'success': 0}
    session = requests.Session()
    session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    try:
        res = session.get(f"{BASE_SEARCH_URL}&start=0", headers=get_headers(), timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('.search_result_row')[:BATCH_LIMIT]
        stats['total'] = len(rows)

        for i, row in enumerate(rows):
            try:
                app_id = row['data-ds-appid']
                title = row.select_one('.title').text.strip()
                img_tag = row.select_one('.search_capsule img')
                thumb_url = img_tag['src'] if img_tag else ""
                
                print(f"[{i+1}/{len(rows)}] Checking: {title}")
                
                game_info = database.get(app_id, {
                    'Title': title, 'Date': row.select_one('.search_released').text.strip(),
                    'Email': '', 'Discord': '', 'URL': row['href'].split('?')[0], 'Site': '',
                    'ContactPage': '', 'Thumb': thumb_url
                })
                game_info['Thumb'] = thumb_url

                p_res = session.get(game_info['URL'], headers=get_headers(), timeout=12)
                p_soup = BeautifulSoup(p_res.text, 'html.parser')
                
                for link in p_soup.find_all('a', href=True):
                    txt, href = link.get_text().lower(), link['href']
                    if 'website' in txt:
                        site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                        if 'steampowered' not in site:
                            game_info['Site'] = site
                            try:
                                s_res = session.get(site, headers=get_headers(), timeout=10)
                                s_soup = BeautifulSoup(s_res.text, 'html.parser')
                                
                                for s_link in s_soup.find_all('a', href=True):
                                    s_href = s_link['href'].lower()
                                    if 'contact' in s_href:
                                        game_info['ContactPage'] = urljoin(site, s_link['href'])
                                        break
                                    if 'about' in s_href and not game_info['ContactPage']:
                                        game_info['ContactPage'] = urljoin(site, s_link['href'])

                                target_scan = game_info['ContactPage'] if game_info['ContactPage'] else site
                                scan_res = session.get(target_scan, headers=get_headers(), timeout=10)
                                found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', scan_res.text)
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

# Force schedule reset 2026-01-24

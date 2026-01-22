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
REFRESH_LIMIT = 100 
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

def deep_scan(url):
    emails, contact_page = [], "None"
    try:
        res = requests.get(url, headers=get_headers(), timeout=15)
        emails.extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res.text))
        soup = BeautifulSoup(res.text, 'html.parser')
        target = "None"
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            if 'contact' in href or 'about' in href or 'press' in href:
                target = urljoin(url, link['href'])
                if 'contact' in href: break # Contact is priority
        
        if target != "None":
            contact_page = target
            time.sleep(2)
            c_res = requests.get(target, headers=get_headers(), timeout=15)
            emails.extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', c_res.text))
    except: pass
    return emails, contact_page

def run_script():
    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: database = json.load(f)
            except: database = {}

    print(f"--- Loaded {len(database)} games. Syncing latest... ---")
    
    try:
        res = requests.get(f"{BASE_SEARCH_URL}&start=0", headers=get_headers(), timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('.search_result_row')[:REFRESH_LIMIT]
    except Exception as e:
        print(f"Critical Steam Search Error: {e}")
        return

    session = requests.Session()
    session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    for i, row in enumerate(rows):
        app_id = row['data-ds-appid']
        title = row.select_one('.title').text.strip()
        release_date = row.select_one('.search_released').text.strip()
        store_url = row['href'].split('?')[0]
        
        print(f"[{i+1}/{len(rows)}] Processing: {title}")
        
        game_info = database.get(app_id, {
            'Title': title, 'Date': release_date, 'Email': 'None', 
            'Discord': 'None', 'URL': store_url, 'Site': 'None'
        })

        try:
            # The core improvement: wrap each game scan in its own safety net
            p_res = session.get(store_url, headers=get_headers(), timeout=12)
            p_soup = BeautifulSoup(p_res.text, 'html.parser')
            
            # Sidebar search
            sidebar_links = p_soup.select('a[href*="linkfilter"], .btn_share_res')
            for link in sidebar_links:
                href = link.get('href', '')
                text = link.get_text().lower()
                
                if 'website' in text or 'visit the website' in text:
                    site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                    if 'steampowered' not in site:
                        game_info['Site'] = site
                        raw_emails, _ = deep_scan(site)
                        emails = filter_emails(raw_emails, site)
                        if emails: game_info['Email'] = ", ".join(emails)

                if 'discord' in text or 'discord.gg' in href:
                    game_info['Discord'] = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href

        except Exception as e:
            print(f"   [!] Skipping {title} due to connection error.")

        database[app_id] = game_info
        time.sleep(3) # Higher delay to prevent "Exit Code 1"

    # Save Data
    with open(DB_FILE, 'w') as f: json.dump(database, f, indent=4)

    # Generate Responsive HTML
    sorted_games = sorted(database.values(), key=lambda x: x['Date'], reverse=True)
    html = """<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
        body { background: #0b0e14; color: #d1d1d1; font-family: sans-serif; padding: 10px; line-height: 1.6; }
        .container { max-width: 1000px; margin: auto; }
        .game-row { background: #1a1f26; margin: 8px 0; padding: 15px; border-radius: 6px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; border-left: 5px solid #3a4453; transition: 0.3s; }
        .game-row:hover { border-left-color: #66c0f4; background: #1f252d; }
        .date-header { color: #66c0f4; margin-top: 35px; border-bottom: 2px solid #2a313d; padding-bottom: 10px; font-size: 1.4em; }
        .email { color: #a3da00; font-weight: bold; background: rgba(163, 218, 0, 0.1); padding: 2px 6px; border-radius: 3px; }
        a { color: #66c0f4; text-decoration: none; font-size: 0.9em; }
        .discord-btn { background: #5865F2; color: white !important; padding: 4px 10px; border-radius: 4px; font-weight: bold; }
        @media (max-width: 600px) { .game-row { flex-direction: column; align-items: flex-start; } .game-row span { margin-bottom: 10px; } }
    </style></head><body><div class='container'>"""
    
    html += f"<h1>Steam Dev Tracker <small style='font-size:14px; color:#555;'>Last Sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}</small></h1>"
    
    curr_date = ""
    for g in sorted_games:
        if g['Date'] != curr_date:
            curr_date = g['Date']
            html += f"<h2 class='date-header'>{curr_date}</h2>"
        
        discord_html = f"<a class='discord-btn' href='{g['Discord']}'>Discord</a>" if g['Discord'] != 'None' else ""
        site_link = f"<a href='{g['Site']}'>[Site]</a>" if g['Site'] != 'None' else ""
        
        html += f"""<div class='game-row'>
            <span><b style='font-size:1.1em;'>{g['Title']}</b></span>
            <span>
                <span class='email'>{g['Email']}</span> &nbsp;
                {discord_html} &nbsp; {site_link} &nbsp; <a href='{g['URL']}'>[Steam]</a>
            </span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</div></body></html>")

if __name__ == "__main__":
    run_script()

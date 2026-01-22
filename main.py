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
REFRESH_LIMIT = 100  # Always re-scan the latest 100
DB_FILE = 'database.json'
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com']

def get_headers():
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def get_base_domain(url):
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith('www.') else netloc
    except: return ""

def filter_emails(emails, site_url):
    site_domain = get_base_domain(site_url)
    clean = [e.lower() for e in emails if (site_domain and site_domain in e.lower()) or (e.lower().split('@')[-1] in TRUSTED_PROVIDERS)]
    return list(set(clean))

def deep_scan(url):
    """Priority hunt for emails and contact pages."""
    emails, contact_page = [], "None"
    try:
        res = requests.get(url, headers=get_headers(), timeout=10)
        emails.extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res.text))
        soup = BeautifulSoup(res.text, 'html.parser')
        target = "None"
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            if 'contact' in href: target = urljoin(url, link['href']); break
            if 'about' in href and target == "None": target = urljoin(url, link['href'])
        
        if target != "None":
            contact_page = target
            time.sleep(1)
            c_res = requests.get(target, headers=get_headers(), timeout=10)
            emails.extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', c_res.text))
    except: pass
    return emails, contact_page

def run_script():
    # 1. Load History
    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f: database = json.load(f)

    print(f"--- Loaded {len(database)} archived games. Refreshing top {REFRESH_LIMIT} ---")
    
    # 2. Scrape Top 100 from Steam
    res = requests.get(f"{BASE_SEARCH_URL}&start=0", headers=get_headers())
    soup = BeautifulSoup(res.text, 'html.parser')
    rows = soup.select('.search_result_row')[:REFRESH_LIMIT]

    for row in rows:
        app_id = row['data-ds-appid']
        title = row.select_one('.title').text.strip()
        release_date = row.select_one('.search_released').text.strip()
        store_url = row['href'].split('?')[0]
        
        # We always process these 100 to catch updates
        print(f"Checking/Refreshing: {title}")
        game_info = {
            'Title': title, 
            'Date': release_date, 
            'Email': database.get(app_id, {}).get('Email', 'None'), 
            'Discord': 'None', 
            'URL': store_url,
            'LastUpdated': datetime.now().strftime('%Y-%m-%d %H:%M')
        }

        try:
            cookies = {'birthtime': '631180801'}
            p_res = requests.get(store_url, headers=get_headers(), cookies=cookies)
            p_soup = BeautifulSoup(p_res.text, 'html.parser')
            for link in p_soup.find_all('a', href=True):
                txt, href = link.get_text().lower(), link['href']
                if 'website' in txt or 'visit the website' in txt:
                    site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                    raw_emails, _ = deep_scan(site)
                    game_info['Email'] = ", ".join(filter_emails(raw_emails, site))
                if 'discord' in txt or 'discord.gg' in href:
                    game_info['Discord'] = href if 'discord.gg' in href else unquote(href.split('u=')[1].split('&')[0])
        except: pass

        database[app_id] = game_info
        time.sleep(1.2) # Steam polite delay

    # 3. Save Persistent Database
    with open(DB_FILE, 'w') as f: json.dump(database, f, indent=4)

    # 4. Generate Live HTML (Categorized by Date)
    # Sorting: Upcoming first, then by AppID (newest discovered)
    sorted_games = sorted(database.values(), key=lambda x: x['Date'], reverse=True)
    
    html = """<html><head><style>
        body { background: #1b2838; color: #c7d5e0; font-family: 'Motiva Sans', Sans-serif; padding: 40px; }
        .date-section { background: #2a475e; padding: 15px; margin: 20px 0; border-radius: 4px; border-left: 5px solid #66c0f4; }
        .game-card { background: rgba(0,0,0,0.2); margin: 10px 0; padding: 10px; border-radius: 4px; display: flex; justify-content: space-between; }
        a { color: #66c0f4; text-decoration: none; } a:hover { text-decoration: underline; }
        .email { color: #a3da00; font-weight: bold; }
    </style></head><body>"""
    
    html += f"<h1>Steam Developer Watchlist <small>(Last Sync: {datetime.now().strftime('%H:%M')})</small></h1>"
    
    current_date = ""
    for g in sorted_games:
        if g['Date'] != current_date:
            current_date = g['Date']
            html += f"<div class='date-section'><h2>{current_date}</h2></div>"
        
        discord_html = f"<a href='{g['Discord']}'>[Discord]</a>" if g['Discord'] != 'None' else ""
        html += f"""<div class='game-card'>
            <span><b>{g['Title']}</b></span>
            <span><span class='email'>{g['Email']}</span> | {discord_html} | <a href='{g['URL']}'>[Steam]</a></span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</body></html>")

if __name__ == "__main__":
    run_script()

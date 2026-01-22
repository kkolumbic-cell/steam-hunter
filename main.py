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
REFRESH_LIMIT = 50 # Start small to ensure success
DB_FILE = 'database.json'
TRUSTED_PROVIDERS = ['gmail.com', 'outlook.com', 'proton.me', 'protonmail.com', 'zoho.com', 'icloud.com']

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://store.steampowered.com/'
    }

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
    emails, contact_page = [], "None"
    try:
        res = requests.get(url, headers=get_headers(), timeout=12)
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
            c_res = requests.get(target, headers=get_headers(), timeout=12)
            emails.extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', c_res.text))
    except: pass
    return emails, contact_page

def run_script():
    database = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: database = json.load(f)
            except: database = {}

    print(f"--- Syncing {REFRESH_LIMIT} games ---")
    
    # Pass 1: Get the list
    res = requests.get(f"{BASE_SEARCH_URL}&start=0", headers=get_headers())
    soup = BeautifulSoup(res.text, 'html.parser')
    rows = soup.select('.search_result_row')[:REFRESH_LIMIT]

    # Persistent cookies to bypass Age Gate on GitHub
    session = requests.Session()
    session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

    for row in rows:
        app_id = row['data-ds-appid']
        title = row.select_one('.title').text.strip()
        release_date = row.select_one('.search_released').text.strip()
        store_url = row['href'].split('?')[0]
        
        print(f"Hunting: {title}...")
        
        # Initialize entry
        game_info = database.get(app_id, {
            'Title': title, 'Date': release_date, 'Email': 'None', 
            'Discord': 'None', 'URL': store_url, 'Site': 'None'
        })

        try:
            p_res = session.get(store_url, headers=get_headers(), timeout=10)
            p_soup = BeautifulSoup(p_res.text, 'html.parser')
            
            # Find all links in the sidebar/right-hand column
            sidebar_links = p_soup.select('.btn_share_res, .btn_blue_steamui, a[href*="linkfilter"]')
            
            for link in sidebar_links:
                href = link.get('href', '')
                text = link.get_text().lower()
                
                # WEBSITE LOOKUP
                if 'visit the website' in text or 'website' == text.strip():
                    site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                    if 'store.steampowered' not in site:
                        game_info['Site'] = site
                        raw_emails, _ = deep_scan(site)
                        emails = filter_emails(raw_emails, site)
                        if emails: game_info['Email'] = ", ".join(emails)

                # DISCORD LOOKUP
                if 'discord' in text or 'discord.gg' in href:
                    discord = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                    game_info['Discord'] = discord

        except Exception as e:
            print(f"   Error: {e}")

        database[app_id] = game_info
        time.sleep(2) # Be extra polite to Steam

    # Save and Generate HTML
    with open(DB_FILE, 'w') as f: json.dump(database, f, indent=4)

    # Simple Table Styling for the Live Page
    sorted_games = sorted(database.values(), key=lambda x: x['Date'], reverse=True)
    html = """<html><head><style>
        body { background: #0b0e14; color: #d1d1d1; font-family: sans-serif; padding: 20px; }
        .container { max-width: 900px; margin: auto; }
        .game-row { background: #1a1f26; margin-bottom: 5px; padding: 15px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; border-left: 4px solid #3a4453; }
        .date-header { color: #66c0f4; margin-top: 30px; border-bottom: 1px solid #333; padding-bottom: 5px; }
        .email { color: #a3da00; font-family: monospace; }
        a { color: #66c0f4; text-decoration: none; }
        .discord-btn { background: #5865F2; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; }
    </style></head><body><div class='container'>"""
    
    html += f"<h1>Steam Dev Tracker <small style='font-size:12px; color:#666;'>Last Update: {datetime.now().strftime('%H:%M')}</small></h1>"
    
    curr_date = ""
    for g in sorted_games:
        if g['Date'] != curr_date:
            curr_date = g['Date']
            html += f"<h2 class='date-header'>{curr_date}</h2>"
        
        discord_link = f"<a class='discord-btn' href='{g['Discord']}'>Discord</a>" if g['Discord'] != 'None' else ""
        site_link = f"<a href='{g['Site']}'>[Official Site]</a>" if g['Site'] != 'None' else ""
        
        html += f"""<div class='game-row'>
            <span><b>{g['Title']}</b></span>
            <span><span class='email'>{g['Email']}</span> {discord_link} {site_link} <a href='{g['URL']}'>[Steam]</a></span>
        </div>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html + "</div></body></html>")

if __name__ == "__main__":
    run_script()

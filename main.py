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

def parse_steam_date(date_str):
    """Converts Steam date strings into comparable datetime objects."""
    date_str = date_str.strip()
    # Handle vague dates like "Coming Soon" or "TBA" - put them far in the future
    if not date_str or "coming" in date_str.lower() or "tba" in date_str.lower() or "wishlist" in date_str.lower():
        return datetime(2099, 12, 31)
    
    # Try parsing standard formats like "25 Jan, 2026" or "Jan 2026"
    formats = [
        '%d %b, %Y',  # 25 Jan, 2026
        '%b %d, %Y',  # Jan 25, 2026
        '%b %Y',      # Jan 2026
        '%Y'          # 2026
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
            
    # If parsing fails, treat it as a past date (bottom of list)
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
    """Updates both the JSON database and the live HTML dashboard."""
    current_refresh_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    with open(DB_FILE, 'w') as f:
        json.dump(database, f, indent=4)
    
    # --- SMART SORTING ---
    # Sort by the parsed date object, descending (Future -> Present -> Past)
    sorted_games = sorted(
        database.values(), 
        key=lambda x: parse_steam_date(x.get('Date', '')), 
        reverse=True
    )
    
    # Calculate stats for ONLY the visible games
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
        # --- CLEAN LIST FILTER ---
        # If no data is found, skip this entry entirely in the HTML
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

    session = requests.Session()
    session.cookies.update({'birthtime': '631180801', 'lastagecheckage': '1-0-1990', 'wants_mature_content': '1'})

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

                print(f"Checking: {title}")
                
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
                            found_site = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href
                            if 'steampowered' not in found_site:
                                game_info['Site'] = found_site
                        if 'discord' in txt or 'discord.gg' in href:
                            game_info['Discord'] = unquote(href.split('u=')[1].split('&')[0]) if 'linkfilter' in href else href

                    # --- RESTORED CONTACT PAGE LOGIC ---
                    if game_info['Site']:
                        try:
                            s_res = session.get(game_info['Site'], headers=get_headers(), timeout=10)
                            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', s_res.text)
                            
                            # If homepage is empty, hunt for Contact/About pages
                            if not emails:
                                s_soup = BeautifulSoup(s_res.text, 'html.parser')
                                for s_link in s_soup.find_all('a', href=True):
                                    s_txt, s_href = s_link.get_text().lower(), s_link['href']
                                    # Look for keywords in the link text or URL
                                    if any(k in s_txt or k in s_href.lower() for k in ['contact', 'about', 'support', 'impressum']):
                                        contact_url = urljoin(game_info['Site'], s_href)
                                        c_res = session.get(contact_url, headers=get_headers(), timeout=10)
                                        emails += re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', c_res.text)
                                        if emails: break
                            
                            clean = filter_emails(emails, game_info['Site'])
                            if clean: game_info['Email'] = ", ".join(clean)
                        except: pass
                    
                    database[app_id] = game_info
                    time.sleep(random.uniform(3.0, 6.0))
                except: pass
        except: pass
    
    save_data(database)

if __name__ == "__main__":
    run_script()

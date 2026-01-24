# Steam Hunter

Steam Hunter is a small Python scraper that periodically pulls data from Steam and publishes a static dashboard to GitHub Pages.

## Live site

https://kkolumbic-cell.github.io/steam-hunter/

## How it works

- A GitHub Actions workflow runs on a schedule and can also be triggered manually.
- The workflow runs `python main.py`.
- The script updates the generated site assets in the repo (for example `index.html`) and the data file (`database.json`).
- The workflow commits and pushes those generated files back to the `main` branch so GitHub Pages serves the updated content.

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r requirements.txt  # if present
# or: pip install requests beautifulsoup4
python main.py
```

## Repository files (high level)

- `main.py` — scraper / generator entry point.
- `database.json` — scraped data output.
- `index.html` — generated dashboard page served by GitHub Pages.
- `.github/workflows/scrape.yml` — scheduled workflow that refreshes the site.
# Web Scraper

Scrapes content from HTML pages and saves it as JSON.

## Setup

Requires Python 3.12 or newer. Run from the project folder:

```powershell
python -m pip install uv
python -m uv sync --python 3.12
```

## Run

```powershell
python -m uv run scraper https://quotes.toscrape.com/ --max-pages 3
```

Results are saved to `output/results.json`. Running again overwrites the file.

To choose a different output file:

```powershell
python -m uv run scraper https://www.merrjep.com/ --max-pages 1 --output output/merrjep.json
```

For all available options:

```powershell
python -m uv run scraper --help
```

The scraper reads server-returned HTML; it does not run JavaScript.

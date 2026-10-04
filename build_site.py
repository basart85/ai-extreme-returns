"""
Add this week's report to the website folder and rebuild the home page.

Run after weekly_extreme_report.py, from the same folder:
    python3 build_site.py                      # week ending = most recent Friday
    python3 build_site.py --week-ending 2026-09-25

What it does:
  1. copies extreme_returns_report.html  ->  docs/reports/<week-ending>.html
     (and adds an "All reports" link at the top of the report)
  2. records the week and its flagged tickers in docs/reports.json
  3. regenerates docs/index.html with links to every week, newest first

Then commit/upload the docs/ folder; GitHub Pages publishes it when set to serve from /docs.
"""
import argparse
import html
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

REPORT_HTML = Path("extreme_returns_report.html")
CARD_PNG = Path("extreme_returns_chart.png")
NEWS_CSV = Path("extreme_news_last_week.csv")
SITE = Path("docs")   # GitHub Pages: Settings > Pages > branch main, folder /docs

# Your site's public address, no trailing slash. Social previews need full URLs.
SITE_URL = "https://basart85.github.io/ai-extreme-returns"
SITE_TITLE = "AI Stocks: Weekly Extreme Returns"
SITE_INTRO = ("Each week, the largest AI companies' daily returns are compared with the "
              "S&P 500, and days beyond a stock's own 5th or 95th return percentile are "
              "flagged together with the news around them.")


def last_friday(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=(today.weekday() - 4) % 7)


def flagged_tickers() -> list[str]:
    if not NEWS_CSV.exists():
        return []
    df = pd.read_csv(NEWS_CSV)
    return sorted(df["ticker"].dropna().unique()) if "ticker" in df else []


def social_tags(title: str, description: str, page_url: str, image_url: str | None) -> str:
    """Open Graph + Twitter Card tags so X, LinkedIn, WhatsApp etc. show a preview."""
    t, d = html.escape(title), html.escape(description)
    tags = [f'<meta name="description" content="{d}">',
            '<meta property="og:type" content="article">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            f'<meta property="og:url" content="{page_url}">',
            f'<meta name="twitter:title" content="{t}">',
            f'<meta name="twitter:description" content="{d}">']
    if image_url:
        tags += [f'<meta property="og:image" content="{image_url}">',
                 '<meta property="og:image:width" content="1200">',
                 '<meta property="og:image:height" content="630">',
                 '<meta name="twitter:card" content="summary_large_image">',
                 f'<meta name="twitter:image" content="{image_url}">']
    else:
        tags.append('<meta name="twitter:card" content="summary">')
    return "".join(tags)


def publish_report(week: date, tickers: list[str]) -> None:
    (SITE / "reports").mkdir(parents=True, exist_ok=True)
    page = REPORT_HTML.read_text(encoding="utf-8")
    back = ('<p style="margin:0 0 16px"><a href="../index.html">&larr; All reports</a></p>')
    if "All reports" not in page:
        page = page.replace("<main>", "<main>" + back, 1)

    stem = f"{week:%Y-%m-%d}"
    image_url = None
    if CARD_PNG.exists():
        shutil.copyfile(CARD_PNG, SITE / "reports" / f"{stem}.png")
        image_url = f"{SITE_URL}/reports/{stem}.png"
    desc = (f"Extreme return days for {', '.join(tickers)} vs the S&P 500, with the news behind the moves."
            if tickers else "Daily returns of the largest AI stocks vs the S&P 500.")
    if 'property="og:title"' not in page:
        page = page.replace("</head>", social_tags(
            f"AI stocks: extreme return days, week ending {week:%d %b %Y}", desc,
            f"{SITE_URL}/reports/{stem}.html", image_url) + "</head>", 1)
    (SITE / "reports" / f"{stem}.html").write_text(page, encoding="utf-8")


def update_catalog(week: date, tickers: list[str]) -> list[dict]:
    path = SITE / "reports.json"
    catalog = json.loads(path.read_text()) if path.exists() else []
    catalog = [c for c in catalog if c["week_ending"] != f"{week:%Y-%m-%d}"]   # replace re-runs
    catalog.append({"week_ending": f"{week:%Y-%m-%d}", "flagged": tickers,
                    "file": f"reports/{week:%Y-%m-%d}.html"})
    catalog.sort(key=lambda c: c["week_ending"], reverse=True)
    path.write_text(json.dumps(catalog, indent=2))
    return catalog


CSS = """
:root{--bg:#f4f3f0;--card:#fff;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e1;--link:#1f5fae;
  --chip:#eef3fb;--chip-ink:#1f4f8f}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1f1f1e;--ink:#fff;--ink2:#c3c2b7;
  --line:#33332f;--link:#7fb0f0;--chip:#233349;--chip-ink:#b9d3f5}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,
  BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 16px 64px}
h1{font-size:30px;margin:0 0 8px}
.intro{color:var(--ink2);margin:0 0 28px}
ul.weeks{list-style:none;margin:0;padding:0}
ul.weeks li{margin:0 0 12px}
a.week{display:block;background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:16px 18px;text-decoration:none;color:var(--ink)}
a.week:hover,a.week:focus-visible{border-color:var(--link);outline:none}
.date{font-weight:600;font-size:18px}
.latest{font-size:12px;font-weight:700;color:var(--link);margin-left:8px;text-transform:uppercase}
.meta{color:var(--ink2);font-size:14px;margin-top:6px}
.chip{display:inline-block;background:var(--chip);color:var(--chip-ink);font-size:13px;
  font-weight:600;padding:1px 9px;border-radius:999px;margin:2px 4px 0 0}
footer{color:var(--ink2);font-size:13px;margin-top:36px}
"""


def build_index(catalog: list[dict]) -> None:
    items = []
    for n, c in enumerate(catalog):
        wk = datetime.strptime(c["week_ending"], "%Y-%m-%d")
        chips = ("".join(f'<span class="chip">{html.escape(t)}</span>' for t in c["flagged"])
                 if c["flagged"] else "No extreme days")
        latest = '<span class="latest">Latest</span>' if n == 0 else ""
        items.append(f'<li><a class="week" href="{html.escape(c["file"])}">'
                     f'<span class="date">Week ending {wk:%d %B %Y}</span>{latest}'
                     f'<div class="meta">{chips}</div></a></li>')
    latest_png = SITE / catalog[0]["file"].replace(".html", ".png") if catalog else None
    image_url = (f"{SITE_URL}/{catalog[0]['file'].replace('.html', '.png')}"
                 if latest_png and latest_png.exists() else None)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(SITE_TITLE)}</title>
{social_tags(SITE_TITLE, SITE_INTRO, SITE_URL + "/", image_url)}
<style>{CSS}</style></head><body><main>
<h1>{html.escape(SITE_TITLE)}</h1><p class="intro">{html.escape(SITE_INTRO)}</p>
<ul class="weeks">{''.join(items)}</ul>
<footer>For research and information only; not investment advice.
Data: Yahoo Finance, Google News.</footer></main></body></html>"""
    (SITE / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-ending", help="YYYY-MM-DD (default: most recent Friday)")
    args = ap.parse_args()
    week = (datetime.strptime(args.week_ending, "%Y-%m-%d").date()
            if args.week_ending else last_friday())

    if not REPORT_HTML.exists():
        raise SystemExit(f"{REPORT_HTML} not found - run weekly_extreme_report.py first.")
    if "<your-username>" in SITE_URL:
        raise SystemExit("Set SITE_URL at the top of build_site.py to your site's address first.")
    tickers = flagged_tickers()
    publish_report(week, tickers)
    catalog = update_catalog(week, tickers)
    build_index(catalog)
    print(f"Added week ending {week} - site now has {len(catalog)} report(s) in {SITE.resolve()}")

"""
Weekly extreme-returns report.

Reads   extreme_news_last_week.csv  (saved in Step 16)
        extreme_news_articles.csv   (optional, saved in Step 14 - adds article links)
Writes  extreme_returns_report.html (open in a browser; Print > Save as PDF for a PDF)

Run from the folder that holds the CSVs:  python3 weekly_extreme_report.py
Requires: pip install yfinance pandas matplotlib feedparser googlenewsdecoder
"""
import base64
import html
import io
import json
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from matplotlib.ticker import PercentFormatter

try:
    import feedparser
except ImportError:
    feedparser = None
try:
    from googlenewsdecoder import gnewsdecoder
except ImportError:          # links fall back to Google News redirects
    gnewsdecoder = None

NEWS_CSV = "extreme_news_last_week.csv"
ARTICLES_CSV = "extreme_news_articles.csv"
OUT_HTML = "extreme_returns_report.html"
CARD_PNG = "output/extreme_returns_chart.png"   # 1200x630 preview image for X / LinkedIn / WhatsApp
URL_CACHE = Path("resolved_urls.json")   # remembers decoded links so re-runs are fast

# Assets to plot. None = only the assets that had an extreme day last week.
# Or list them, e.g. ["NVDA", "MSFT", "GOOGL", "AMZN", "META"], to plot all five.
PLOT_TICKERS = None

BENCHMARK = "^GSPC"
BENCHMARK_LABEL = "S&P 500"
MAX_HEADLINES = 6
FETCH_NEWS = True    # fetch each extreme day's headlines + links from Google News while building

# Categorical palette in fixed order (validated default), benchmark in neutral gray.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]
BENCH_COLOR = "#52514e"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"


# ---------------------------------------------------------------- data
def load_extremes() -> pd.DataFrame:
    df = pd.read_csv(NEWS_CSV, parse_dates=["date"])
    df["headlines"] = df.get("headlines", "").fillna("")
    return df


def load_articles() -> pd.DataFrame | None:
    if not Path(ARTICLES_CSV).exists():
        print(f"  {ARTICLES_CSV} not found - using headlines and links from {NEWS_CSV}")
        return None
    return pd.read_csv(ARTICLES_CSV, parse_dates=["date"])


def last_week_returns(tickers: list[str]) -> pd.DataFrame:
    prices = yf.download(tickers + [BENCHMARK], period="1mo",
                         auto_adjust=True, progress=False)["Close"]
    rets = prices.pct_change().dropna(how="all")
    rets.index = pd.to_datetime(rets.index).tz_localize(None)
    rets = rets.loc[rets[BENCHMARK].dropna().index[-5:]]      # past 5 trading days
    return rets.rename(columns={BENCHMARK: BENCHMARK_LABEL})


# ---------------------------------------------------------------- chart
def make_chart(rets: pd.DataFrame, tickers: list[str], extremes: pd.DataFrame,
               card_title: str = "") -> str:
    x = range(len(rets))
    fig, ax = plt.subplots(figsize=(10, 5.2))
    fig.patch.set_facecolor("white")

    ax.axhline(0, color="#9a9a9a", linewidth=1, zorder=1)
    ax.plot(x, rets[BENCHMARK_LABEL] * 100, color=BENCH_COLOR, linewidth=2,
            linestyle="--", marker="o", markersize=6, label=BENCHMARK_LABEL, zorder=2)

    colors = {t: SERIES_COLORS[i % len(SERIES_COLORS)] for i, t in enumerate(tickers)}
    for t in tickers:
        ax.plot(x, rets[t] * 100, color=colors[t], linewidth=2, marker="o",
                markersize=6, label=t, zorder=3)

    # highlight extreme days: large ringed marker + value label
    pos = {d: i for i, d in enumerate(rets.index)}
    plotted = extremes[extremes["ticker"].isin(colors) & extremes["date"].isin(pos)]
    for d, group in plotted.groupby("date"):
        i = pos[d]
        for k, row in enumerate(group.sort_values("return_pct", ascending=False).itertuples()):
            y = rets.loc[d, row.ticker] * 100
            ax.scatter(i, y, s=190, color=colors[row.ticker], edgecolors="white",
                       linewidths=2.5, zorder=5)
            up = y >= 0
            # several extremes on one day: alternate labels right/left of the points
            if len(group) > 1:
                side = 1 if k % 2 == 0 else -1
                if i == len(rets) - 1:
                    side = -1
                elif i == 0:
                    side = 1
                dx, ha = 18 * side, ("left" if side > 0 else "right")
                dy, va = 0, "center"
            else:
                dx, ha = 0, "center"
                dy, va = (26, "bottom") if up else (-30, "top")
            ax.annotate(f"{row.ticker} {y:+.2f}%\n({row.tail})", (i, y),
                        xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                        fontsize=9, color=INK, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.9),
                        arrowprops=dict(arrowstyle="-", color=INK_2, linewidth=0.8), zorder=6)

    ax.set_xticks(list(x))
    ax.set_xticklabels([d.strftime("%a %d %b") for d in rets.index], color=INK_2)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=1))
    ax.tick_params(axis="y", colors=INK_2)
    ax.set_ylabel("Daily return", color=INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#bdbcb7")
    ax.margins(x=0.06, y=0.25)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.12), ncol=len(tickers) + 1,
              frameon=False, fontsize=10, handlelength=2.2)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")

    # social-media preview image: exactly 1200x630 px, with a title
    fig.set_size_inches(12, 6.3)
    fig.suptitle(card_title, x=0.012, y=0.985, ha="left", va="top",
                 fontsize=17, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(CARD_PNG, format="png", dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- links
_url_cache = json.loads(URL_CACHE.read_text()) if URL_CACHE.exists() else {}
_decode_warned = False


def publisher_url(link: str) -> str:
    """Turn a Google News redirect link into the publisher's own URL (falls back to the input)."""
    global _decode_warned
    if not isinstance(link, str) or "news.google.com" not in link:
        return link
    if link in _url_cache:
        return _url_cache[link]
    if gnewsdecoder is None:
        if not _decode_warned:
            print("  googlenewsdecoder not installed - using Google News links "
                  "(pip install googlenewsdecoder)")
            _decode_warned = True
        return link
    try:
        result = gnewsdecoder(link, interval=1)
        url = result.get("decoded_url") if result.get("status") else None
    except Exception as e:
        print(f"  could not decode a link: {e}")
        url = None
    if url:
        _url_cache[link] = url
        URL_CACHE.write_text(json.dumps(_url_cache, indent=1))
        return url
    time.sleep(1)
    return link


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# ---------------------------------------------------------------- news
_LEGAL_WORDS = {"inc", "inc.", "corporation", "corp", "corp.", "ltd", "ltd.", "limited",
                "co", "co.", "company", "platforms", "holdings", "plc"}
_names: dict[str, str] = {}


def company_name(ticker: str) -> str:
    if ticker not in _names:
        try:
            name = yf.Ticker(ticker).info.get("shortName") or ticker
        except Exception:
            name = ticker
        words = [w for w in name.replace(",", "").split() if w.lower() not in _LEGAL_WORDS]
        _names[ticker] = " ".join(words) or ticker
    return _names[ticker]


def fetch_news(ticker: str, day: pd.Timestamp) -> list[dict]:
    """Google News articles from the day before to the day after `day`, with links."""
    if feedparser is None:
        print("  feedparser not installed - using headlines from the CSV (pip install feedparser)")
        return []
    start, end = day - pd.Timedelta(days=1), day + pd.Timedelta(days=2)
    query = f'("{company_name(ticker)}" OR {ticker}) after:{start:%Y-%m-%d} before:{end:%Y-%m-%d}'
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
           + "&hl=en-US&gl=US&ceid=US:en")
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"  news fetch failed for {ticker} {day:%Y-%m-%d}: {e}")
        return []
    items, seen = [], set()
    for e in feed.entries:
        source = e.get("source", {}).get("title", "")
        title = e.get("title", "")
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        if not title or title in seen:
            continue
        seen.add(title)
        items.append({"title": title, "source": source, "link": e.get("link", "")})
        if len(items) == MAX_HEADLINES:
            break
    time.sleep(1)                      # be polite to Google between requests
    return items


# ---------------------------------------------------------------- html
CSS = """
body{margin:0;background:#f4f3f0;color:#0b0b0b;font:16px/1.55 -apple-system,
  BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px}
.sub{color:#52514e;margin:0 0 24px}
.card{background:#fff;border:1px solid #e6e5e1;border-radius:10px;padding:20px;margin:0 0 20px}
h2{font-size:20px;margin:0 0 12px}
h3{font-size:18px;margin:0}
.badge{display:inline-block;font-size:13px;font-weight:600;padding:2px 10px;border-radius:999px;
  margin-left:8px;vertical-align:2px}
.up{background:#e3f4ea;color:#0b5d2a}.down{background:#fbe6e4;color:#8a1c14}
img{width:100%;height:auto}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid #e6e5e1;text-align:right}
th:first-child,td:first-child{text-align:left}
td.ext{font-weight:700;text-decoration:underline}
ul{margin:8px 0 0;padding-left:20px}
li{margin:4px 0}
.meta{color:#52514e;font-size:14px;margin:6px 0 0}
.note{color:#52514e;font-size:13px}
a{color:#1f5fae}
"""


def returns_table(rets: pd.DataFrame, cols: list[str], extremes: pd.DataFrame) -> str:
    ext = {(r.ticker, r.date) for r in extremes.itertuples()}
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = ""
    for d, row in rets[cols].iterrows():
        cells = "".join(
            f'<td class="{"ext" if (c, d) in ext else ""}">{row[c] * 100:+.2f}%</td>' for c in cols)
        body += f"<tr><td>{d:%a %d %b %Y}</td>{cells}</tr>"
    return f"<table><thead><tr><th>Date</th>{head}</tr></thead><tbody>{body}</tbody></table>"


def news_items(row, articles: pd.DataFrame | None) -> list[dict]:
    """Headlines with links for one extreme day: live fetch first, then the CSVs as fallback."""
    if FETCH_NEWS:
        items = fetch_news(row.ticker, row.date)
        if items:
            return items
    if articles is not None:
        sub = articles[(articles["ticker"] == row.ticker) & (articles["date"] == row.date)]
        items = [{"title": str(a.title), "source": str(a.source), "link": str(a.link)}
                 for a in sub.head(MAX_HEADLINES).itertuples()]
        if items:
            return items
    titles = [h.strip() for h in str(row.headlines or "").split(" | ") if h.strip()]
    raw = getattr(row, "links", "")
    links = [l.strip() for l in str(raw).split(" | ")] if isinstance(raw, str) and raw else []
    return [{"title": t, "source": "", "link": links[n] if n < len(links) else ""}
            for n, t in enumerate(titles[:MAX_HEADLINES])]


def render_item(item: dict) -> str:
    title = html.escape(item["title"])
    link = item.get("link") or ""
    if not link:
        return f"<li>{title}</li>"
    url = publisher_url(link)
    site = domain(url) if "news.google.com" not in url else ""
    label = " · ".join(html.escape(x) for x in (item.get("source") or "", site) if x)
    return (f'<li><a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{title}</a>'
            + (f' <span class="note">— {label}</span>' if label else "") + "</li>")


def news_section(row, articles: pd.DataFrame | None) -> str:
    cls = "up" if str(row.tail).startswith("top") else "down"
    out = [f'<div class="card"><h3>{html.escape(row.ticker)} · {row.date:%A %d %B %Y}'
           f'<span class="badge {cls}">{row.return_pct:+.2f}% · {html.escape(str(row.tail))}</span></h3>']

    summary = getattr(row, "summary", "")
    if isinstance(summary, str) and summary.strip():
        out.append(f"<p>{html.escape(summary)}</p>")

    items = news_items(row, articles)
    if items:
        out.append("<strong>Key headlines</strong><ul>" + "".join(render_item(i) for i in items) + "</ul>")
        out.append('<p class="meta">News from the day before to the day after the move.</p>')
    else:
        out.append('<p class="meta">No news articles were found for this day.</p>')
    out.append("</div>")
    return "".join(out)


def build_report():
    extremes = load_extremes().rename(columns={"return_%": "return_pct"})
    articles = load_articles()

    tickers = PLOT_TICKERS or sorted(extremes["ticker"].unique())
    if not tickers:
        raise SystemExit("No extreme days last week and no PLOT_TICKERS set - nothing to report.")

    rets = last_week_returns(list(tickers))
    extremes = extremes[extremes["date"].isin(rets.index)].sort_values(["date", "ticker"])
    week = f"{rets.index[0]:%d %b} – {rets.index[-1]:%d %b %Y}"
    chart = make_chart(rets, list(tickers), extremes,
                       card_title=f"AI stocks: extreme return days · {week}")

    flagged = sorted(extremes["ticker"].unique())
    intro = (f"{len(flagged)} asset(s) had at least one day in their own top or bottom 5% of daily "
             f"returns over the past year: {', '.join(flagged)}." if flagged
             else "No asset had a top- or bottom-5% return day this week.")

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Extreme Returns Report</title><style>{CSS}</style></head><body><main>",
        "<h1>AI stocks: extreme return days</h1>",
        f"<p class='sub'>Week of {week} · benchmark: {BENCHMARK_LABEL}</p>",
        f"<div class='card'><h2>Summary</h2><p>{html.escape(intro)}</p>"
        "<p class='note'>Extreme = a daily return beyond the stock's own 5th or 95th percentile "
        "of daily returns over the trailing year.</p></div>",
        "<div class='card'><h2>Daily returns, past 5 trading days</h2>",
        f"<img alt='Line chart of daily returns for {', '.join(tickers)} and the {BENCHMARK_LABEL}"
        f" over the past five trading days, with extreme days highlighted' "
        f"src='data:image/png;base64,{chart}'>",
        returns_table(rets, list(tickers) + [BENCHMARK_LABEL], extremes),
        "<p class='note'>Bold, underlined values are extreme days.</p></div>",
        "<h2>News on extreme days</h2>",
    ]
    parts += [news_section(r, articles) for r in extremes.itertuples(index=False)]
    parts.append("<p class='note'>For research and information only; not investment advice. "
                 "Headlines appearing near a move do not establish that they caused it. "
                 "Data: Yahoo Finance, Google News.</p></main></body></html>")

    Path(OUT_HTML).write_text("".join(parts), encoding="utf-8")
    print(f"Report written to {Path(OUT_HTML).resolve()}")


if __name__ == "__main__":
    build_report()

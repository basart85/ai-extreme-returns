# %% [markdown]
# # Top-N US-traded AI companies by market cap
# Run cell by cell: click "Run Cell" above each `# %%`, or put the cursor in a cell and press Shift+Enter.
# Requires: pip install yfinance pandas ipykernel  (plus the Jupyter extension in VS Code)

# %% Imports and settings
import pandas as pd
import yfinance as yf


# %% Step 6: last week's news per asset (Google News RSS)
import time
from urllib.parse import quote_plus
import feedparser

# %% Step 8: daily returns over the last week, one chart per asset
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter
import textwrap
import matplotlib.pyplot as plt


 
# AI-themed ETFs whose holdings define the candidate universe.
AI_ETFS = ["AIQ", "BOTZ", "ROBT", "IGPT", "CHAT"]

# Optional names you always want considered (leave empty for a purely ETF-driven universe).
MANUAL = ["NVDA", "MSFT", "GOOGL", "META", "AMZN", "AVGO", "TSM", "AMD", "ORCL", "PLTR"]

# Collapse duplicate share classes of the same company.
SHARE_CLASS_ALIASES = {"GOOG": "GOOGL"}

# %% Function definitions
def etf_holdings(etf: str) -> list[str]:
    """Top holdings of an ETF (yfinance exposes roughly the top 10)."""
    try:
        df = yf.Ticker(etf).funds_data.top_holdings
        return [str(s).upper() for s in df.index]
    except Exception as e:
        print(f"  could not read holdings for {etf}: {e}")
        return []


def build_universe() -> list[str]:
    tickers = set(MANUAL)
    for etf in AI_ETFS:
        tickers.update(etf_holdings(etf))
    tickers = {SHARE_CLASS_ALIASES.get(t, t) for t in tickers}
    # Keep US listings: foreign-exchange tickers carry a suffix like "6758.T" or "ASML.AS".
    return sorted(t for t in tickers if "." not in t)


def market_caps(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        try:
            fi = yf.Ticker(t).fast_info
            if fi["currency"] != "USD":
                continue
            rows.append({"ticker": t, "market_cap": fi["marketCap"], "price": fi["lastPrice"]})
        except Exception as e:
            print(f"  skipped {t}: {e}")
    df = pd.DataFrame(rows, columns=["ticker", "market_cap", "price"])
    if df.empty:
        raise RuntimeError("No market caps retrieved - check your connection to Yahoo Finance.")
    return df.dropna(subset=["market_cap"])


def historical_market_cap(ticker: str, start: str = "2020-01-01") -> pd.Series:
    """Point-in-time market cap = daily close x shares outstanding on that date (use for backtests)."""
    tk = yf.Ticker(ticker)
    close = tk.history(start=start, auto_adjust=False)["Close"]
    shares = tk.get_shares_full(start=start)
    shares = shares[~shares.index.duplicated(keep="last")].sort_index()
    close.index = close.index.tz_localize(None)
    shares.index = shares.index.tz_localize(None)
    shares = shares.reindex(close.index, method="ffill")
    return (close * shares).rename(f"{ticker}_market_cap")

# %% Step 1: build the universe (slow part - run once)
universe = build_universe()
print(f"Universe: {len(universe)} tickers")
universe

# %% Step 2: fetch market caps for the whole universe
caps = market_caps(universe)
caps.sort_values("market_cap", ascending=False)

# %% Step 3: top N (re-run with a different N without re-downloading)
N = 5
top = caps.sort_values("market_cap", ascending=False).head(N).copy()
top["market_cap_$bn"] = (top["market_cap"] / 1e9).round(1)
top[["ticker", "price", "market_cap_$bn"]].reset_index(drop=True)

# %% Step 4 (optional): point-in-time market cap history for the top names
hist = pd.concat([historical_market_cap(t) for t in top["ticker"]], axis=1)
hist.tail()


# %% Step 5: daily returns over the last week
tickers = top["ticker"].tolist()

prices = yf.download(tickers, period="1mo", auto_adjust=True, progress=False)["Close"]

returns = prices.pct_change().dropna(how="all").tail(5)   # last 5 trading days
returns.round(4)

# %%
# Legal-form words to strip, so "NVIDIA Corporation" becomes "NVIDIA"
DROP = {"inc", "inc.", "corporation", "corp", "corp.", "ltd", "ltd.", "limited",
        "co", "co.", "company", "platforms", "holdings", "plc"}

# %%
def company_name(ticker):
    try:
        name = yf.Ticker(ticker).info.get("shortName") or ticker
    except Exception:
        name = ticker
    words = [w for w in name.replace(",", "").split() if w.lower() not in DROP]
    return " ".join(words) or ticker

def google_news(ticker, days=7, max_items=20):
    name = company_name(ticker)
    query = f'("{name}" OR {ticker}) when:{days}d'
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
           + "&hl=en-US&gl=US&ceid=US:en")
    feed = feedparser.parse(url)
    rows = []
    for e in feed.entries[:max_items]:
        source = e.get("source", {}).get("title", "")
        title = e.title
        if source and title.endswith(f" - {source}"):   # Google appends " - Source"
            title = title[: -len(source) - 3]
        rows.append({
            "ticker": ticker,
            "published": pd.to_datetime(e.get("published"), utc=True),
            "title": title,
            "source": source,
            "link": e.link,
        })
    return rows

# %%
all_news = []
for t in tickers:
    all_news += google_news(t)
    time.sleep(1)   # be polite to Google between requests

news = (pd.DataFrame(all_news)
        .drop_duplicates(["ticker", "title"])
        .sort_values(["ticker", "published"], ascending=[True, False])
        .reset_index(drop=True))

news.groupby("ticker").size()   # number of articles per ticker


# %% Step 7: news count per day, aligned with returns
news["date"] = (news["published"].dt.tz_convert("America/New_York")
                .dt.normalize().dt.tz_localize(None))
counts = news.groupby(["date", "ticker"]).size().unstack(fill_value=0)
counts.reindex(returns.index, fill_value=0)


# %% 
pct = returns * 100                     # decimals -> percent
n = len(pct.columns)

fig, axes = plt.subplots(n, 1, figsize=(8, 2.2 * n), sharex=True, sharey=True)
axes = np.atleast_1d(axes)              # works even if there is only one ticker

for ax, ticker in zip(axes, pct.columns):
    s = pct[ticker].dropna()
    ax.plot(s.index, s.values, color="#2a6fdb", linewidth=2, marker="o", markersize=6)
    ax.axhline(0, color="#9a9a9a", linewidth=1)            # zero line: up vs down days
    ax.set_title(ticker, loc="left", fontsize=11, fontweight="bold")
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=1))
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    # label only the latest value, not every point
    ax.annotate(f"{s.iloc[-1]:+.2f}%", (s.index[-1], s.iloc[-1]),
                xytext=(8, 0), textcoords="offset points", va="center", fontsize=9, color="#333")

axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
fig.suptitle("Daily returns, last 5 trading days", x=0.01, ha="left", fontsize=13)
fig.tight_layout()
plt.show()



# %% Step 9: daily returns over the last year
end = pd.Timestamp.today().normalize()
start = end - pd.DateOffset(years=1)

# download a few extra days so the first return in the window has a previous close
prices_1y = yf.download(tickers, start=start - pd.Timedelta(days=10),
                        auto_adjust=True, progress=False)["Close"]

returns_1y = prices_1y.pct_change().loc[start:].dropna(how="all")

print(returns_1y.shape)   # about 250 trading days x 5 tickers
returns_1y.tail()


# %% Step 10: 5th and 95th percentile daily returns per asset
cutoffs = returns_1y.quantile([0.05, 0.95]).T
cutoffs.columns = ["bottom_5pct", "top_5pct"]
(cutoffs * 100).round(2)          # in percent

# %%
extremes = []
for t in returns_1y.columns:
    r = returns_1y[t].dropna()
    lo, hi = r.quantile(0.05), r.quantile(0.95)
    tail = r[(r <= lo) | (r >= hi)]
    extremes.append(pd.DataFrame({
        "ticker": t,
        "date": tail.index,
        "return_%": (tail.values * 100).round(2),
        "tail": np.where(tail.values <= lo, "bottom 5%", "top 5%"),
    }))
extremes = pd.concat(extremes).sort_values(["ticker", "date"]).reset_index(drop=True)
extremes



# %% Step 12: extreme-return days in the last week
last_week = returns_1y.index[-5:]          # last 5 trading days

recent_week = extremes[extremes["date"].isin(last_week)]

# flag_week = (recent_week.groupby("ticker")
#              .agg(n_extreme_days=("date", "size"),
#                   bottom_days=("tail", lambda s: (s == "bottom 5%").sum()),
#                   top_days=("tail", lambda s: (s == "top 5%").sum()))
#              .reindex(returns_1y.columns, fill_value=0))
# flag_week["any_extreme"] = flag_week["n_extreme_days"] > 0
# flag_week


flag_week = (recent_week
             .assign(bottom=recent_week["tail"].eq("bottom 5%"),
                     top=recent_week["tail"].eq("top 5%"))
             .groupby("ticker")
             .agg(n_extreme_days=("date", "size"),
                  bottom_days=("bottom", "sum"),
                  top_days=("top", "sum"))
             .reindex(returns_1y.columns, fill_value=0))
flag_week["any_extreme"] = flag_week["n_extreme_days"] > 0
flag_week


# %%

# %%
recent_week




# %% Step 13: news around each extreme-return day
def parse_feed(feed, ticker, max_items):
    rows = []
    for e in feed.entries[:max_items]:
        source = e.get("source", {}).get("title", "")
        title = e.title
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        rows.append({"ticker": ticker,
                     "published": pd.to_datetime(e.get("published"), utc=True),
                     "title": title, "source": source, "link": e.link})
    return rows

def google_news_window(ticker, name, start, end, max_items=10):
    query = f'("{name}" OR {ticker}) after:{start:%Y-%m-%d} before:{end:%Y-%m-%d}'
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
           + "&hl=en-US&gl=US&ceid=US:en")
    return parse_feed(feedparser.parse(url), ticker, max_items)

# %%
# Which extreme days to look up: `extremes` (whole year), `recent` (last month) or `recent_week`
days = extremes

names = {t: company_name(t) for t in days["ticker"].unique()}   # look up each name once

records = []
for _, row in days.iterrows():
    d = pd.Timestamp(row["date"])
    # window: the day before through the day after the move
    items = google_news_window(row["ticker"], names[row["ticker"]],
                               d - pd.Timedelta(days=1), d + pd.Timedelta(days=1))
    for item in items:
        item["date"] = d
    records += items
    time.sleep(1)                     # be polite to Google between requests

event_news = pd.DataFrame(records, columns=["ticker", "date", "published", "title", "source", "link"])
event_news = event_news.drop_duplicates(["ticker", "date", "title"])

# titles sometimes contain "|", which would break the pairing with links
event_news["title"] = event_news["title"].str.replace("|", "-", regex=False)

headlines = (event_news.groupby(["ticker", "date"])
             .agg(n_articles=("title", "size"),
                  headlines=("title", lambda s: " | ".join(s)),
                  links=("link", lambda s: " | ".join(s)),
                  sources=("source", lambda s: ", ".join(pd.unique(s))))
             .reset_index())

# one row per extreme day, with the headlines concatenated
#headlines = (event_news.groupby(["ticker", "date"])
#             .agg(n_articles=("title", "size"),
#                  headlines=("title", lambda s: " | ".join(s)),
#                  sources=("source", lambda s: ", ".join(pd.unique(s))))
#             .reset_index())

extreme_news = days.merge(headlines, on=["ticker", "date"], how="left")
extreme_news["n_articles"] = extreme_news["n_articles"].fillna(0).astype(int)
extreme_news["headlines"] = extreme_news["headlines"].fillna("")
extreme_news
# %%
# %% Step 14: save to CSV
extreme_news.to_csv("extreme_news.csv", index=False, encoding="utf-8-sig")


# %% Step 15: extreme-news rows from the last week only
extreme_news_week = (extreme_news[extreme_news["date"].isin(last_week)]
                     .sort_values(["date", "ticker"])
                     .reset_index(drop=True))
extreme_news_week

# %% 
extreme_news_week.to_csv("extreme_news_last_week.csv", index=False, encoding="utf-8-sig")
# %%
text = ", ".join(map(str, universe))
wrapped = textwrap.fill(text, width=60)   # max ~60 characters per line

fig, ax = plt.subplots(figsize=(8, 0.4 * wrapped.count("\n") + 0.8))
ax.axis("off")
ax.text(0, 1, wrapped, va="top", ha="left", fontsize=12,
        transform=ax.transAxes)
fig.savefig("list.png", dpi=200, bbox_inches="tight")
plt.close(fig)
# %%
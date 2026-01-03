import requests
import csv
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ====================================================
# CONFIG
# ====================================================
OUTPUT_FILE = "form19a_enriched.csv"

HEADERS = {
    "User-Agent": "ETF Dividend Research Tool (manual ingestion)",
    "Accept-Encoding": "identity"
}

TARGET_TICKERS = {"ULTY", "MSTY"}

YIELDMAX_NEWS_INDEX = "https://yieldmaxetfs.com/news/"

# Yahoo validation window (days around payable date)
YAHOO_DATE_TOLERANCE = 3

# ====================================================
# HELPERS
# ====================================================
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.2)
    return r.text

def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date()
    except:
        return None

def parse_pct(text):
    try:
        return float(text.replace("%", "").strip()) / 100
    except:
        return ""

def yahoo_dividends(ticker, start, end):
    """
    Returns list of dividend dates from Yahoo Finance
    """
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={int(start.timestamp())}"
        f"&period2={int(end.timestamp())}"
        f"&interval=1d&events=div"
    )
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return []

    data = r.json().get("chart", {}).get("result", [])
    if not data:
        return []

    events = data[0].get("events", {}).get("dividends", {})
    return [datetime.fromtimestamp(v["date"]).date() for v in events.values()]

# ====================================================
# STEP 1 — AUTO-DISCOVER GLOBENEWSWIRE LINKS
# ====================================================
print("Discovering YieldMax distribution releases…")

index_html = fetch_html(YIELDMAX_NEWS_INDEX)
index_soup = BeautifulSoup(index_html, "html.parser")

release_urls = []

for a in index_soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)

    if (
        "Weekly Distributions" in text
        and "Group" in text
        and "globenewswire.com" in href
    ):
        release_urls.append(href)

release_urls = list(dict.fromkeys(release_urls))  # de-dupe

print(f"Discovered {len(release_urls)} release URLs")

# ====================================================
# STEP 2 — PARSE EACH RELEASE (BACKFILL)
# ====================================================
rows = []

for url in release_urls:
    print(f"Processing release: {url}")
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = soup.find("h1").get_text(strip=True)
    group = "Group 1" if "Group 1" in title else "Group 2" if "Group 2" in title else ""

    table = soup.find("table")
    if not table:
        continue

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    roc_idx = len(headers) - 1

    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) <= roc_idx:
            continue

        row = dict(zip(headers, cells))
        ticker = row.get("Ticker") or row.get("Symbol") or cells[1]

        if ticker not in TARGET_TICKERS:
            continue

        payable = parse_date(row.get("Payable Date", ""))
        ex_date = parse_date(row.get("Ex-Date", ""))
        dividend = row.get("Distribution Amount", "")
        roc = parse_pct(cells[roc_idx])

        # ====================================================
        # STEP 3 — YAHOO VALIDATION
        # ====================================================
        yahoo_match = ""
        if payable:
            start = payable - timedelta(days=YAHOO_DATE_TOLERANCE)
            end = payable + timedelta(days=YAHOO_DATE_TOLERANCE)
            ydates = yahoo_dividends(ticker, start, end)
            yahoo_match = "Yes" if ydates else "No"

        rows.append([
            ticker,
            payable.isoformat() if payable else "",
            ex_date.isoformat() if ex_date else "",
            dividend,
            roc,
            yahoo_match,
            url,
            group
        ])

# ====================================================
# WRITE CSV (ALWAYS REBUILT)
# ====================================================
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Ticker",
        "Distribution Date",
        "Ex-Dividend Date",
        "Dividend Per Share",
        "ROC %",
        "Yahoo Dividend Match",
        "Source URL",
        "Group"
    ])
    writer.writerows(rows)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

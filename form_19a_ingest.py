import requests
import csv
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urljoin

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

YAHOO_DATE_TOLERANCE = 3  # days

# ====================================================
# HELPERS
# ====================================================
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.25)
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
# STEP 1 — DISCOVER YIELDMAX NEWS POSTS
# ====================================================
print("Discovering YieldMax news posts…")

index_html = fetch_html(YIELDMAX_NEWS_INDEX)
index_soup = BeautifulSoup(index_html, "html.parser")

yieldmax_posts = []

for a in index_soup.find_all("a", href=True):
    title = a.get_text(strip=True)
    href = a["href"]

    if (
        "Weekly Distributions" in title
        and "Group" in title
    ):
        full_url = urljoin(YIELDMAX_NEWS_INDEX, href)
        yieldmax_posts.append(full_url)

yieldmax_posts = list(dict.fromkeys(yieldmax_posts))
print(f"Found {len(yieldmax_posts)} YieldMax news posts")

# ====================================================
# STEP 2 — EXTRACT GLOBENEWSWIRE LINKS
# ====================================================
globe_urls = []

for post_url in yieldmax_posts:
    print(f"Scanning YieldMax post: {post_url}")
    post_html = fetch_html(post_url)
    post_soup = BeautifulSoup(post_html, "html.parser")

    for a in post_soup.find_all("a", href=True):
        if "globenewswire.com" in a["href"]:
            globe_urls.append(a["href"])

globe_urls = list(dict.fromkeys(globe_urls))
print(f"Discovered {len(globe_urls)} GlobeNewswire releases")

# ====================================================
# STEP 3 — PARSE GLOBENEWSWIRE TABLES
# ====================================================
rows = []

for url in globe_urls:
    print(f"Processing GlobeNewswire release: {url}")
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

        yahoo_match = ""
        if payable:
            start = payable - timedelta(days=YAHOO_DATE_TOLERANCE)
            end = payable + timedelta(days=YAHOO_DATE_TOLERANCE)
            yahoo_match = "Yes" if yahoo_dividends(ticker, start, end) else "No"

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
# WRITE CSV
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

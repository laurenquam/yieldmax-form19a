import requests
import csv
import time
import re
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

def extract_ticker_from_cells(cells):
    for cell in cells:
        if cell in TARGET_TICKERS:
            return cell
    return None

def yahoo_dividends(ticker, start_date, end_date):
    """
    start_date and end_date are datetime.date objects
    """
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.min.time())

    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={int(start_dt.timestamp())}"
        f"&period2={int(end_dt.timestamp())}"
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

def extract_header_fields(text):
    """
    Extract metadata fields that appear above the table
    """
    def grab(label):
        m = re.search(label + r"\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
        return parse_date(m.group(1)) if m else None

    def grab_pct(label):
        m = re.search(label + r"\s*:\s*([0-9.]+%)", text)
        return parse_pct(m.group(1)) if m else ""

    return {
        "payment_date": grab("Payment Date"),
        "ex_date": grab("Ex-Date"),
        "record_date": grab("Record Date"),
        "distribution_rate": grab_pct("Distribution Rate"),
        "sec_30_day_yield": grab_pct("30-Day SEC Yield"),
    }

# ====================================================
# STEP 1 — DISCOVER YIELDMAX NEWS POSTS
# ====================================================
print("Discovering YieldMax news posts…")

index_html = fetch_html(YIELDMAX_NEWS_INDEX)
index_soup = BeautifulSoup(index_html, "html.parser")

yieldmax_posts = []

for a in index_soup.find_all("a", href=True):
    title = a.get_text(strip=True)
    if "Weekly Distributions" in title and "Group" in title:
        yieldmax_posts.append(urljoin(YIELDMAX_NEWS_INDEX, a["href"]))

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
    if not group:
        continue

    full_text = soup.get_text(" ", strip=True)
    meta = extract_header_fields(full_text)

    table = soup.find("table")
    if not table:
        continue

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    roc_idx = len(headers) - 1

    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 4:
            continue

        ticker = extract_ticker_from_cells(cells)
        if not ticker:
            continue

        dividend = cells[-5] if len(cells) >= 5 else ""
        roc = parse_pct(cells[roc_idx])

        yahoo_match = ""
        if meta["payment_date"]:
            start = meta["payment_date"] - timedelta(days=YAHOO_DATE_TOLERANCE)
            end = meta["payment_date"] + timedelta(days=YAHOO_DATE_TOLERANCE)
            yahoo_match = "Yes" if yahoo_dividends(ticker, start, end) else "No"

        rows.append([
            ticker,
            meta["payment_date"].isoformat() if meta["payment_date"] else "",
            meta["ex_date"].isoformat() if meta["ex_date"] else "",
            meta["record_date"].isoformat() if meta["record_date"] else "",
            dividend,
            roc,
            meta["distribution_rate"],
            meta["sec_30_day_yield"],
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
        "Payment Date",
        "Ex-Dividend Date",
        "Record Date",
        "Dividend Per Share",
        "ROC %",
        "Distribution Rate",
        "30-Day SEC Yield",
        "Yahoo Dividend Match",
        "Source URL",
        "Group"
    ])
    writer.writerows(rows)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

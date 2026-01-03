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
    "Accept": "text/html",
    "Accept-Encoding": "identity"
}

TARGET_TICKERS = {"ULTY", "MSTY"}
YIELDMAX_NEWS_INDEX = "https://yieldmaxetfs.com/news/"
YAHOO_TOLERANCE_DAYS = 3
AMOUNT_TOLERANCE = 0.01  # $0.01 tolerance for Yahoo vs issuer

# ====================================================
# BASIC HELPERS
# ====================================================
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.25)
    return r.text

def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date()
    except Exception:
        return None

def parse_pct(text):
    try:
        return float(text.replace("%", "").strip()) / 100
    except Exception:
        return None

def parse_float(text):
    try:
        return float(text.replace("$", "").strip())
    except Exception:
        return None

# ====================================================
# YAHOO VALIDATION (QA ONLY)
# ====================================================
def yahoo_dividends(ticker, start_date, end_date):
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
    results = []
    for v in events.values():
        results.append({
            "date": datetime.fromtimestamp(v["date"]).date(),
            "amount": float(v["amount"])
        })
    return results

# ====================================================
# HEADER (PER-RELEASE) EXTRACTION
# ====================================================
def extract_release_metadata(text):
    def grab_date(patterns):
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return parse_date(m.group(1))
        return None

    return {
        "payment_date": grab_date([
            r"Payment Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})"
        ]),
        "ex_date": grab_date([
            r"Ex[-\s]?Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            r"Ex[-\s]?Dividend Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})"
        ]),
        "record_date": grab_date([
            r"Record Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})"
        ])
    }

# ====================================================
# STEP 1 — DISCOVER YIELDMAX NEWS POSTS (INCLUSIVE)
# ====================================================
print("Discovering YieldMax news posts…")

index_html = fetch_html(YIELDMAX_NEWS_INDEX)
index_soup = BeautifulSoup(index_html, "html.parser")

yieldmax_posts = []

for a in index_soup.find_all("a", href=True):
    title = a.get_text(strip=True).upper()
    if (
        "GROUP 1" in title
        or "GROUP 2" in title
        or "ULTY" in title
        or "MSTY" in title
        or "DISTRIBU" in title
    ):
        yieldmax_posts.append(urljoin(YIELDMAX_NEWS_INDEX, a["href"]))

yieldmax_posts = list(dict.fromkeys(yieldmax_posts))
print(f"Found {len(yieldmax_posts)} YieldMax candidate posts")

# ====================================================
# STEP 2 — EXTRACT RELEVANT GLOBENEWSWIRE LINKS
# ====================================================
globe_urls = []

for post_url in yieldmax_posts:
    post_html = fetch_html(post_url)
    post_soup = BeautifulSoup(post_html, "html.parser")
    post_text = post_soup.get_text(" ", strip=True).upper()

    if not ("ULTY" in post_text or "MSTY" in post_text):
        continue

    for a in post_soup.find_all("a", href=True):
        if "globenewswire.com" in a["href"]:
            globe_urls.append(a["href"])

globe_urls = list(dict.fromkeys(globe_urls))
print(f"Discovered {len(globe_urls)} GlobeNewswire releases")

# ====================================================
# STEP 3 — PARSE GLOBENEWSWIRE RELEASES
# ====================================================
rows = []
yieldmax_keys = set()  # (ticker, ex_date) for completeness check

for url in globe_urls:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    body_text = soup.get_text(" ", strip=True)

    if not any(t in body_text.upper() for t in TARGET_TICKERS):
        continue

    h1 = soup.find("h1")
    title = h1.get_text(strip=True).upper() if h1 else ""
    group = "Group 1" if "GROUP 1" in title else "Group 2" if "GROUP 2" in title else ""

    meta = extract_release_metadata(body_text)

    table = soup.find("table")
    if not table:
        continue

    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    header_map = {h: i for i, h in enumerate(headers)}

    def col(*names):
        for n in names:
            if n.lower() in header_map:
                return header_map[n.lower()]
        return None

    idx_ticker = col("ticker", "symbol")
    idx_div = col("distribution amount", "distribution", "dividend")
    idx_rate = col("distribution rate")
    idx_sec_yield = col("30-day sec yield", "30 day sec yield")
    roc_idx = len(headers) - 1  # ROC always last

    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) <= roc_idx:
            continue

        ticker = cells[idx_ticker] if idx_ticker is not None else None
        if ticker not in TARGET_TICKERS:
            continue

        dividend = parse_float(cells[idx_div]) if idx_div is not None else None
        dist_rate = parse_pct(cells[idx_rate]) if idx_rate is not None else None
        sec_yield = parse_pct(cells[idx_sec_yield]) if idx_sec_yield is not None else None
        roc = parse_pct(cells[roc_idx])

        ex_date = meta["ex_date"]
        payment_date = meta["payment_date"]
        record_date = meta["record_date"]

        yieldmax_keys.add((ticker, ex_date))

        # Yahoo validation
        yahoo_date = None
        yahoo_amt = None
        yahoo_match = "No"

        anchor = ex_date or payment_date
        if anchor:
            y_events = yahoo_dividends(
                ticker,
                anchor - timedelta(days=YAHOO_TOLERANCE_DAYS),
                anchor + timedelta(days=YAHOO_TOLERANCE_DAYS)
            )
            for ev in y_events:
                if dividend is not None and abs(ev["amount"] - dividend) <= AMOUNT_TOLERANCE:
                    yahoo_date = ev["date"]
                    yahoo_amt = ev["amount"]
                    yahoo_match = "Yes"
                    break

        rows.append([
            ticker,
            group,
            payment_date,
            ex_date,
            record_date,
            dividend,
            roc,
            dist_rate,
            sec_yield,
            yahoo_date,
            yahoo_amt,
            yahoo_match,
            url
        ])

# ====================================================
# STEP 4 — COMPLETENESS CHECK (YAHOO-ANCHOR)
# ====================================================
completeness_rows = []
for ticker in TARGET_TICKERS:
    all_yahoo = yahoo_dividends(
        ticker,
        datetime.today().date() - timedelta(days=365),
        datetime.today().date()
    )
    for ev in all_yahoo:
        key = (ticker, ev["date"])
        if key not in yieldmax_keys:
            completeness_rows.append([
                ticker,
                None,
                None,
                ev["date"],
                None,
                None,
                None,
                None,
                None,
                ev["date"],
                ev["amount"],
                "Missing YieldMax",
                None
            ])

rows.extend(completeness_rows)

# ====================================================
# WRITE CSV
# ====================================================
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Ticker",
        "Group",
        "Payment Date",
        "Ex-Dividend Date",
        "Record Date",
        "Distribution Per Share",
        "ROC %",
        "Distribution Rate",
        "30-Day SEC Yield",
        "Yahoo Dividend Date",
        "Yahoo Dividend Amount",
        "Yahoo Match",
        "Source URL"
    ])
    writer.writerows(rows)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

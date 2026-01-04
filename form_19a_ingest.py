import requests
import csv
import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ====================================================
# CONFIG
# ====================================================
OUTPUT_FILE = "yieldmax_raw_extract.csv"

HEADERS = {
    "User-Agent": "YieldMax Raw Extractor",
    "Accept": "text/html",
    "Accept-Encoding": "identity"
}

TARGET_TICKERS = ["ULTY", "MSTY"]
YIELDMAX_NEWS_INDEX = "https://yieldmaxetfs.com/news/"

# ====================================================
# HELPERS
# ====================================================
def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.2)
    return r.text

def extract_date_block(text, label):
    """
    Extract raw date text like:
    Payment Date: December 30, 2025
    """
    m = re.search(
        rf"{label}\s*:\s*([A-Za-z]+\s+\d{{1,2}},\s+\d{{4}})",
        text,
        re.IGNORECASE
    )
    return m.group(1) if m else ""

# ====================================================
# STEP 1 — DISCOVER YIELDMAX NEWS POSTS
# ====================================================
print("Discovering YieldMax news posts…")

index_html = fetch_html(YIELDMAX_NEWS_INDEX)
index_soup = BeautifulSoup(index_html, "html.parser")

yieldmax_posts = []

for a in index_soup.find_all("a", href=True):
    title = a.get_text(strip=True).upper()
    if any(t in title for t in ["GROUP", "ULTY", "MSTY", "DISTRIBU"]):
        yieldmax_posts.append(urljoin(YIELDMAX_NEWS_INDEX, a["href"]))

yieldmax_posts = list(dict.fromkeys(yieldmax_posts))
print(f"Found {len(yieldmax_posts)} YieldMax candidate posts")

# ====================================================
# STEP 2 — COLLECT GLOBENEWSWIRE LINKS
# ====================================================
globe_urls = []

for post_url in yieldmax_posts:
    html = fetch_html(post_url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).upper()

    if not any(t in text for t in TARGET_TICKERS):
        continue

    for a in soup.find_all("a", href=True):
        if "globenewswire.com" in a["href"]:
            globe_urls.append(a["href"])

globe_urls = list(dict.fromkeys(globe_urls))
print(f"Discovered {len(globe_urls)} GlobeNewswire releases")

# ====================================================
# STEP 3 — RAW EXTRACTION
# ====================================================
rows = []
max_table_cols = 0

for url in globe_urls:
    print(f"Processing: {url}")
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    body_text = soup.get_text(" ", strip=True)

    payment_date = extract_date_block(body_text, "Payment Date")
    ex_date = extract_date_block(body_text, "Ex-Date")
    record_date = extract_date_block(body_text, "Record Date")

    table = soup.find("table")
    if not table:
        print("  ⚠ No table found")
        continue

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    headers_raw = " | ".join(headers)

    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if not cells:
            continue

        row_text = " ".join(cells).upper()

        ticker = None
        for t in TARGET_TICKERS:
            if t in row_text:
                ticker = t
                break

        if not ticker:
            continue

        max_table_cols = max(max_table_cols, len(cells))

        row = {
            "Ticker": ticker,
            "Payment Date": payment_date,
            "Ex-Dividend Date": ex_date,
            "Record Date": record_date,
            "Source URL": url,
            "Table Headers (raw)": headers_raw
        }

        for i, val in enumerate(cells, start=1):
            row[f"Table Col {i}"] = val

        rows.append(row)

print(f"Extracted {len(rows)} rows")

# ====================================================
# WRITE CSV (ALWAYS)
# ====================================================
base_fields = [
    "Ticker",
    "Payment Date",
    "Ex-Dividend Date",
    "Record Date",
    "Source URL",
    "Table Headers (raw)"
]

table_fields = [f"Table Col {i}" for i in range(1, max_table_cols + 1)]
fieldnames = base_fields + table_fields

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

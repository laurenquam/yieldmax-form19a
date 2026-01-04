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

def normalize_space(s):
    return re.sub(r"\s+", " ", s).strip()

def extract_payment_date(text):
    patterns = [
        r"Payment Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Payable Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Payable\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Payment on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""

def extract_date(text, label):
    m = re.search(
        rf"{label}\s*:\s*([A-Za-z]+\s+\d{{1,2}},\s+\d{{4}})",
        text,
        re.IGNORECASE
    )
    return m.group(1) if m else ""

def is_numeric_row(text):
    return bool(re.search(r"(\$|\%|\d+\.\d+)", text))

# ====================================================
# STEP 1 — DISCOVER YIELDMAX NEWS POSTS
# ====================================================
print("Discovering YieldMax news posts…")

index_html = fetch_html(YIELDMAX_NEWS_INDEX)
index_soup = BeautifulSoup(index_html, "html.parser")

yieldmax_posts = []

for a in index_soup.find_all("a", href=True):
    title = a.get_text(strip=True).upper()
    if any(k in title for k in ["GROUP", "ULTY", "MSTY", "DISTRIBU"]):
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
# STEP 3 — RAW EXTRACTION (MULTI-TABLE SAFE)
# ====================================================
rows = []

for url in globe_urls:
    print(f"Processing: {url}")
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    page_text = soup.get_text(" ", strip=True)
    first_table = soup.find("table")
    if first_table:
        pre_table_text = page_text.split(first_table.get_text(" ", strip=True))[0]
    else:
        pre_table_text = page_text

    payment_date = extract_payment_date(pre_table_text)
    ex_date = extract_date(pre_table_text, "Ex[- ]?Date")
    record_date = extract_date(pre_table_text, "Record Date")

    tables = soup.find_all("table")
    if not tables:
        continue

    last_header_row = ""

    for table in tables:
        for tr in table.find_all("tr"):
            cells = [normalize_space(td.get_text()) for td in tr.find_all(["th", "td"])]
            if not cells:
                continue

            row_text = " ".join(cells)
            row_text_upper = row_text.upper()
            row_text_lower = row_text.lower()

            # Header-like row
            if (
                not is_numeric_row(row_text)
                and any(k in row_text_lower for k in ["distribution", "yield", "frequency", "ticker"])
            ):
                last_header_row = " | ".join(cells)
                continue

            # Data row gate
            ticker = None
            for t in TARGET_TICKERS:
                if t in row_text_upper and is_numeric_row(row_text):
                    ticker = t
                    break

            if not ticker:
                continue

            rows.append({
                "Ticker": ticker,
                "Payment Date": payment_date,
                "Ex-Dividend Date": ex_date,
                "Record Date": record_date,
                "Source URL": url,
                "Table Headers (raw)": last_header_row,
                "Table Row (raw)": " | ".join(cells)
            })

print(f"Extracted {len(rows)} rows")

# ====================================================
# WRITE CSV
# ====================================================
fieldnames = [
    "Ticker",
    "Payment Date",
    "Ex-Dividend Date",
    "Record Date",
    "Source URL",
    "Table Headers (raw)",
    "Table Row (raw)"
]

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

import requests
import csv
import time
from bs4 import BeautifulSoup
from datetime import datetime

# ====================================================
# CONFIG
# ====================================================
OUTPUT_FILE = "form19a_enriched.csv"

HEADERS = {
    "User-Agent": "ETF Dividend Research Tool (manual ingestion)",
    "Accept-Encoding": "identity"
}

TARGET_TICKERS = {"ULTY", "MSTY"}

# Seed list – expand over time or automate discovery later
NEWS_RELEASE_URLS = [
    # Group 1 example (ULTY)
    "https://www.globenewswire.com/news-release/2025/12/30/3211304/0/en/YieldMax-ETFs-Announces-Weekly-Distributions-for-Group-1-ETFs.html",

    # Group 2 example (add as needed)
    # "https://www.globenewswire.com/news-release/YYYY/MM/DD/...Group-2-ETFs.html",
]

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
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except:
        return ""

def parse_pct(text):
    try:
        return float(text.replace("%", "").strip()) / 100
    except:
        return ""

# ====================================================
# MAIN
# ====================================================
rows = []

for url in NEWS_RELEASE_URLS:
    print(f"Processing release: {url}")

    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # Infer group from headline
    title = soup.find("h1").get_text(strip=True)
    group = (
        "Group 1" if "Group 1" in title
        else "Group 2" if "Group 2" in title
        else ""
    )

    table = soup.find("table")
    if not table:
        print("⚠️ No table found, skipping")
        continue

    # Extract headers
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    last_col_idx = len(headers) - 1  # ROC column

    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if not cells or len(cells) <= last_col_idx:
            continue

        # Normalize row into dict
        row = dict(zip(headers, cells))
        ticker = (
            row.get("Ticker")
            or row.get("Symbol")
            or cells[1]   # defensive fallback
        )

        if ticker not in TARGET_TICKERS:
            continue

        distribution = row.get("Distribution Amount", "")
        ex_date = parse_date(row.get("Ex-Date", ""))
        payable_date = parse_date(row.get("Payable Date", ""))

        roc_pct = parse_pct(cells[last_col_idx])

        rows.append([
            ticker,
            payable_date,
            ex_date,
            distribution,
            roc_pct,
            url,
            group
        ])

# ====================================================
# WRITE CSV (ALWAYS)
# ====================================================
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Ticker",
        "Distribution Date",
        "Ex-Dividend Date",
        "Dividend Per Share",
        "ROC %",
        "Source URL",
        "Group"
    ])
    writer.writerows(rows)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

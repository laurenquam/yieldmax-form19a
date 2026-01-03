import requests
import time
import csv
import re

# ====================================================
# CONFIG
# ====================================================
CIK = "0001980842"   # YieldMax Option Income ETF Trust
OUTPUT_FILE = "form19a_enriched.csv"

HEADERS = {
    "User-Agent": "ETF Dividend Research Tool (manual ingestion)",
    "Accept-Encoding": "identity"
}

# Map fund names (as they appear in filings) to tickers
FUND_NAME_MAP = {
    "YieldMax MSTR Option Income ETF": "MSTY",
    "YieldMax Ultra Option Income ETF": "ULTY",
}

# Keywords that positively identify a 19a-1 notice
FORM_19A_KEYWORDS = [
    "rule 19a-1",
    "19a-1",
    "section 19(a)"
]

# ====================================================
# HELPERS
# ====================================================
def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.25)
    return r.json()

def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.25)
    return r.text.lower()

# ====================================================
# MAIN
# ====================================================
rows = []

print("Fetching EDGAR submissions index...")
submissions = fetch_json(
    f"https://data.sec.gov/submissions/CIK{CIK}.json"
)

recent = submissions["filings"]["recent"]

for i, form in enumerate(recent["form"]):
    accession = recent["accessionNumber"][i].replace("-", "")
    primary_doc = recent["primaryDocument"][i]
    filing_date = recent["filingDate"][i]

    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(CIK)}/{accession}/{primary_doc}"
    )

    try:
        text = fetch_text(filing_url)
    except Exception as e:
        print(f"Skipping (fetch failed): {filing_url}")
        continue

    # ------------------------------------------------
    # Content-based detection of Form 19a-1
    # ------------------------------------------------
    if not any(k in text for k in FORM_19A_KEYWORDS):
        continue

    print(f"Detected 19a-1 content: {filing_url}")

    # ------------------------------------------------
    # Identify which ETF(s) are referenced
    # ------------------------------------------------
    for fund_name, ticker in FUND_NAME_MAP.items():
        if fund_name.lower() in text:
            rows.append([
                ticker,
                filing_date,     # authoritative filing date
                "",              # ex-div (joined later)
                "",              # ROC (added later if available)
                filing_url
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
        "ROC %",
        "SEC Filing URL"
    ])
    writer.writerows(rows)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")


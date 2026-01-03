import requests
import time
import csv
import re
from datetime import datetime

# ====================================================
# CONFIGURATION
# ====================================================
CIK = "0001980842"   # YieldMax Option Income ETF Trust
OUTPUT_FILE = "form19a_enriched.csv"

USER_AGENT = "ETF Dividend Research Tool (manual ingestion)"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "identity"
}

# Map exact fund names as they appear in Form 19a-1
ETF_MAP = {
    "YieldMax™ MSTR Option Income ETF": "MSTY",
    "YieldMax™ Ultra Option Income ETF": "ULTY"
}

# ====================================================
# HELPERS
# ====================================================
def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return r.json()

def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return r.text

def parse_date(text):
    """
    Converts 'September 27, 2024' → '2024-09-27'
    """
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except Exception:
        return ""

# ====================================================
# STEP 1: LOAD TRUST SUBMISSIONS
# ====================================================
print("Fetching submissions index…")

submissions_url = f"https://data.sec.gov/submissions/CIK{CIK}.json"
submissions = fetch_json(submissions_url)

recent = submissions["filings"]["recent"]

rows = []
processed_filings = 0

# ====================================================
# STEP 2: LOOP FORM 19A FILINGS
# ====================================================
for i, form in enumerate(recent["form"]):
    if "19A" not in form.upper():
        continue

    accession = recent["accessionNumber"][i].replace("-", "")
    primary_doc = recent["primaryDocument"][i]

    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(CIK)}/{accession}/{primary_doc}"
    )

    print(f"Processing filing: {filing_url}")
    processed_filings += 1

    try:
        text = fetch_text(filing_url)
    except Exception as e:
        print(f"Failed to fetch filing text: {e}")
        continue

    # ====================================================
    # STEP 3: PARSE EACH ETF BLOCK
    # ====================================================
    for fund_name, ticker in ETF_MAP.items():
        if fund_name not in text:
            continue

        dist_match = re.search(
            r"Distribution Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text,
            re.IGNORECASE
        )

        ex_match = re.search(
            r"Ex[- ]Dividend Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text,
            re.IGNORECASE
        )

        roc_match = re.search(
            r"return of capital[^0-9]*([0-9]{1,3}\.?[0-9]*)\s*%",
            text,
            re.IGNORECASE
        )

        if not dist_match:
            print(f"⚠️ No distribution date found for {ticker} in this filing")
            continue

        distribution_date = parse_date(dist_match.group(1))
        ex_div_date = parse_date(ex_match.group(1)) if ex_match else ""
        roc_pct = float(roc_match.group(1)) / 100 if roc_match else ""

        rows.append([
            ticker,
            distribution_date,
            ex_div_date,
            roc_pct,
            filing_url
        ])

# ====================================================
# STEP 4: WRITE CSV
# ====================================================
print(f"Processed {processed_filings} Form 19a-1 filings")
print(f"Writing {len(rows)} rows to {OUTPUT_FILE}")

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

print("CSV write complete")

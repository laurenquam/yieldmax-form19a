import requests
import time
import csv
import io
import re
import pdfplumber
from datetime import datetime

# ====================================================
# CONFIG
# ====================================================
OUTPUT_FILE = "form19a_enriched.csv"

PDF_URL = (
    "https://yieldmaxetfs.com/wp-content/uploads/"
    "TaxDocuments/Group_1_Supplemental%20and%20Tax%20IRS%20Form%208937/"
    "YieldMax%2019a-1%20Notice%2011.13.25%20Payable%20-%20Group%201.pdf"
)

HEADERS = {
    "User-Agent": "ETF Dividend Research Tool (manual ingestion)",
    "Accept-Encoding": "identity"
}

TARGET_TICKERS = ["MSTY", "ULTY"]

# ====================================================
# HELPERS
# ====================================================
def fetch_pdf(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return r.content

def extract_text(pdf_bytes):
    text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except:
        return ""

# ====================================================
# MAIN
# ====================================================
print(f"Downloading PDF:\n{PDF_URL}")
pdf_bytes = fetch_pdf(PDF_URL)
full_text = extract_text(pdf_bytes)

print(f"Extracted {len(full_text)} characters")

# ----------------------------
# 1️⃣ Extract payable date (global)
# ----------------------------
payable_match = re.search(
    r"Payable Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    full_text,
    re.IGNORECASE
)

distribution_date = parse_date(payable_match.group(1)) if payable_match else ""
print(f"Distribution (Payable) Date: {distribution_date}")

rows = []

# ----------------------------
# 2️⃣ Extract table rows by ticker
# ----------------------------
lines = full_text.splitlines()

for line in lines:
    for ticker in TARGET_TICKERS:
        if ticker not in line:
            continue

        # Extract all percentages from the line
        pcts = re.findall(r"([0-9]{1,3}\.\d+)%", line)

        # YieldMax tables put ROC % as the LAST percentage
        roc = float(pcts[-1]) / 100 if pcts else ""

        print(f"Parsed {ticker}: ROC={roc}")

        rows.append([
            ticker,
            distribution_date,
            "",                 # Ex-dividend date (not disclosed)
            roc,
            PDF_URL
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
        "ROC %",
        "SEC Filing URL"
    ])
    writer.writerows(rows)

print(f"SUCCESS — wrote {len(rows)} rows to {OUTPUT_FILE}")

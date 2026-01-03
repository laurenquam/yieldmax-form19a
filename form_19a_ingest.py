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

HEADERS = {
    "User-Agent": "ETF Dividend Research Tool (manual ingestion)",
    "Accept-Encoding": "identity"
}

# YieldMax groups (THIS IS THE KEY FIX)
FORM_19A_GROUPS = [
    {
        "group": "Group 1",
        "pdf_url": "https://yieldmaxetfs.com/wp-content/uploads/TaxDocuments/Group_1_Supplemental%20and%20Tax%20IRS%20Form%208937/YieldMax%2019a-1%20Notice%2011.13.25%20Payable%20-%20Group%201.pdf",
        "tickers": ["ULTY"]
    },
    {
        "group": "Group 2",
        "pdf_url": "https://yieldmaxetfs.com/wp-content/uploads/TaxDocuments/Group_2_Supplemental%20and%20Tax%20IRS%20Form%208937/YieldMax%2019a-1%20Notice%2011.13.25%20Payable%20-%20Group%202.pdf",
        "tickers": ["MSTY"]
    }
]

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
rows = []

for group in FORM_19A_GROUPS:
    print(f"Processing {group['group']} PDF")
    pdf_bytes = fetch_pdf(group["pdf_url"])
    text = extract_text(pdf_bytes)

    # Extract payable date ONCE per PDF
    payable_match = re.search(
        r"Payable Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        re.IGNORECASE
    )
    distribution_date = parse_date(payable_match.group(1)) if payable_match else ""

    for line in text.splitlines():
        for ticker in group["tickers"]:
            if ticker not in line:
                continue

            pcts = re.findall(r"([0-9]{1,3}\.\d+)%", line)
            roc = float(pcts[-1]) / 100 if pcts else ""

            rows.append([
                ticker,
                distribution_date,
                "",              # Ex-dividend date not disclosed
                roc,
                group["pdf_url"]
            ])

# ====================================================
# WRITE CSV (ALWAYS FRESH)
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

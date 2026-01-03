import requests
import time
import csv
import re
import io                      # ← FIX
import pdfplumber
from datetime import datetime

# ====================================================
# CONFIG
# ====================================================
OUTPUT_FILE = "form19a_enriched.csv"

USER_AGENT = "ETF Dividend Research Tool (manual ingestion)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "identity"
}

ETF_TICKERS = ["MSTY", "ULTY"]

PDF_URL = (
    "https://yieldmaxetfs.com/wp-content/uploads/"
    "TaxDocuments/Group_1_Supplemental%20and%20Tax%20IRS%20Form%208937/"
    "YieldMax%2019a-1%20Notice%2011.13.25%20Payable%20-%20Group%201.pdf"
)

# ====================================================
# HELPERS
# ====================================================
def fetch_binary(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return r.content

def extract_pdf_text(pdf_bytes):
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
    except Exception:
        return ""

# ====================================================
# MAIN
# ====================================================
rows = []

print(f"Fetching and parsing PDF:\n{PDF_URL}")
pdf_bytes = fetch_binary(PDF_URL)
pdf_text = extract_pdf_text(pdf_bytes)

print(f"Extracted {len(pdf_text)} characters from PDF")

for ticker in ETF_TICKERS:
    if ticker not in pdf_text:
        print(f"{ticker} not found in PDF")
        continue

    # Narrow to local context around ticker
    idx = pdf_text.find(ticker)
    snippet = pdf_text[max(0, idx - 500): idx + 500]

    dist_match = re.search(
        r"Distribution Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        snippet,
        re.IGNORECASE
    )

    ex_match = re.search(
        r"Ex[- ]Dividend Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        snippet,
        re.IGNORECASE
    )

    roc_match = re.search(
        r"Return of Capital[^0-9]*([0-9]{1,3}\.?[0-9]*)\s*%",
        snippet,
        re.IGNORECASE
    )

    dist_date = parse_date(dist_match.group(1)) if dist_match else ""
    ex_date = parse_date(ex_match.group(1)) if ex_match else ""
    roc = float(roc_match.group(1)) / 100 if roc_match else ""

    print(f"{ticker}: dist={dist_date}, ex={ex_date}, roc={roc}")

    rows.append([
        ticker,
        dist_date,
        ex_date,
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


import requests
import time
import csv
import re
import pdfplumber
from datetime import datetime

# ====================================================
# CONFIG
# ====================================================
CIK = "0001980842"
OUTPUT_FILE = "form19a_enriched.csv"

USER_AGENT = "ETF Dividend Research Tool (manual ingestion)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "identity"
}

ETF_MAP = {
    "MSTY": "MSTY",
    "ULTY": "ULTY"
}

# ====================================================
# HELPERS
# ====================================================
def fetch_binary(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return r.content

def pdf_extract_text(pdf_bytes):
    text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def extract_from_pdf_url(url):
    try:
        data = fetch_binary(url)
        return pdf_extract_text(data)
    except Exception as e:
        print(f"PDF extraction failed: {e}")
        return ""

def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except:
        return ""

def find_fields(text):
    dist_date = ""
    ex_date = ""
    roc = ""

    # try common patterns
    dd = re.search(r"Distribution Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if dd:
        dist_date = parse_date(dd.group(1))

    ed = re.search(r"Ex[- ]Dividend Date[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if ed:
        ex_date = parse_date(ed.group(1))

    r = re.search(r"Return of Capital[:\s]*([0-9]{1,3}\.?[0-9]*)\s*%", text, re.IGNORECASE)
    if r:
        try:
            roc = float(r.group(1)) / 100
        except:
            roc = ""

    return dist_date, ex_date, roc

# ====================================================
# HARVEST DATA
# ====================================================
rows = []

# ====================================================
# STEP 1 — Known PDF notice (your provided URL)
# ====================================================
pdf_url = "https://yieldmaxetfs.com/wp-content/uploads/TaxDocuments/Group_1_Supplemental%20and%20Tax%20IRS%20Form%208937/YieldMax%2019a-1%20Notice%2011.13.25%20Payable%20-%20Group%201.pdf"

print(f"Fetching and parsing PDF: {pdf_url}")
pdf_text = extract_from_pdf_url(pdf_url)

if pdf_text:
    for ticker in ETF_MAP:
        # search around ticker label
        if ticker in pdf_text:
            # optionally limit to a section of a few hundred chars around it
            snippet = pdf_text
            dist, ex, roc = find_fields(snippet)
            print(f"Extracted for {ticker}: dist={dist}, ex={ex}, roc={roc}")
            rows.append([ticker, dist, ex, roc, pdf_url])

# ====================================================
# FALLBACK — SEC HTML (not covered here but safe)
# ====================================================
# (Optionally keep your old HTML parsing here)

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

print(f"Done — wrote {len(rows)} rows to {OUTPUT_FILE}")

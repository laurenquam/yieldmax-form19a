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

# Only filing types that can contain narrative disclosures
ALLOWED_FORMS = {
    "497",
    "497K",
    "N-1A",
    "N-1A/A",
    "SUPPL",
    "N-CSR"
}

# Fund name → ticker mapping
FUND_NAME_MAP = {
    "YieldMax MSTR Option Income ETF": "MSTY",
    "YieldMax Ultra Option Income ETF": "ULTY",
}

# Keywords that identify a Rule 19a-1 disclosure
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

def is_narrative_document(filename):
    return filename.lower().endswith((".htm", ".html", ".txt"))

# ====================================================
# MAIN
# ====================================================
rows = []

print("Fetching EDGAR submissions index…")
submissions = fetch_json(
    f"https://data.sec.gov/submissions/CIK{CIK}.json"
)

recent = submissions["filings"]["recent"]

for i, form in enumerate(recent["form"]):
    # ------------------------------------------------
    # 1️⃣ Filter by plausible form types
    # ------------------------------------------------
    if form not in ALLOWED_FORMS:
        continue

    primary_doc = recent["primaryDocument"][i]
    if not is_narrative_document(primary_doc):
        continue

    accession = recent["accessionNumber"][i].replace("-", "")
    filing_date = recent["filingDate"][i]

    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(CIK)}/{accession}/{primary_doc}"
    )

    try:
        text = fetch_text(filing_url)
    except Exception:
        print(f"Skipping (fetch failed): {filing_url}")
        continue

    # ------------------------------------------------
    # 2️⃣ Content-based detection of Rule 19a-1
    # ------------------------------------------------
    if not any(k in text for k in FORM_19A_KEYWORDS):
        continue

    print(f"Detected 19a-1 disclosure: {filing_url}")

    # ------------------------------------------------
    # 3️⃣ Identify which ETF(s) are referenced
    # ------------------------------------------------
    for fund_name, ticker in FUND_NAME_MAP.items():
        if fund_name.lower() in text:
            rows.append([
                ticker,
                filing_date,
                "",          # ex-div (joined later)
                "",          # ROC (added later)
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


import requests
import time
import csv
from bs4 import BeautifulSoup
from datetime import datetime

# ====================================================
# CONFIG
# ====================================================
CIK = "0001980842"   # YieldMax Trust
OUTPUT_FILE = "form19a_enriched.csv"

USER_AGENT = "ETF Dividend Research Tool (manual ingestion)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "identity"
}

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

def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return r.text

def parse_date_safe(text):
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except Exception:
        return ""

# ====================================================
# LOAD TRUST SUBMISSIONS
# ====================================================
submissions = fetch_json(
    f"https://data.sec.gov/submissions/CIK{CIK}.json"
)

recent = submissions["filings"]["recent"]
rows = []

# ====================================================
# LOOP FORM 19A FILINGS
# ====================================================
for i, form in enumerate(recent["form"]):
    if "19A" not in form.upper():
        continue

    accession = recent["accessionNumber"][i].replace("-", "")
    primary_doc = recent["primaryDocument"][i]
    filing_date = recent["filingDate"][i]

    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(CIK)}/{accession}/{primary_doc}"
    )

    print(f"Processing: {filing_url}")

    html = fetch_html(filing_url)
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        continue

    for table in tables:
        rows_html = table.find_all("tr")
        for tr in rows_html:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 3:
                continue

            for fund_name, ticker in ETF_MAP.items():
                if fund_name not in cells[0]:
                    continue

                roc_value = ""
                for c in cells:
                    if "%" in c:
                        try:
                            roc_value = float(c.replace("%", "")) / 100
                        except:
                            pass

                rows.append([
                    ticker,
                    filing_date,   # Distribution date proxy
                    "",             # Ex-div (still blank)
                    roc_value,
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

print(f"Wrote {len(rows)} rows to {OUTPUT_FILE}")

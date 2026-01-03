import requests
import time
import csv
from bs4 import BeautifulSoup
from datetime import datetime

CIK = "0001980842"
OUTPUT_FILE = "form19a_enriched.csv"

HEADERS = {
    "User-Agent": "ETF Dividend Research Tool (manual ingestion)",
    "Accept-Encoding": "identity"
}

# Normalize fund names (no special characters)
ETF_MAP = {
    "YieldMax MSTR Option Income ETF": "MSTY",
    "YieldMax Ultra Option Income ETF": "ULTY"
}

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

def safe_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").date().isoformat()
    except:
        return ""

rows = []

print("Fetching SEC submissions index...")
submissions = fetch_json(f"https://data.sec.gov/submissions/CIK{CIK}.json")
recent = submissions["filings"]["recent"]

for i, form in enumerate(recent["form"]):
    if "19A" not in form.upper():
        continue

    accession = recent["accessionNumber"][i].replace("-", "")
    primary = recent["primaryDocument"][i]
    filing_date = recent["filingDate"][i]

    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{int(CIK)}/{accession}/{primary}"
    )

    print(f"Processing: {filing_url}")

    try:
        html = fetch_html(filing_url)
    except Exception as e:
        print("Failed to fetch filing:", e)
        continue

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    print(f"Found {len(tables)} tables")

    for table in tables:
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            row_text = " ".join(cells)

            for fund_name, ticker in ETF_MAP.items():
                if fund_name.lower() not in row_text.lower():
                    continue

                roc = ""
                for c in cells:
                    if "%" in c:
                        try:
                            roc = float(c.replace("%", "").strip()) / 100
                        except:
                            pass

                rows.append([
                    ticker,
                    filing_date,
                    "",
                    roc,
                    filing_url
                ])

# Always write CSV so GitHub commit step succeeds
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

print(f"SUCCESS: wrote {len(rows)} rows to {OUTPUT_FILE}")

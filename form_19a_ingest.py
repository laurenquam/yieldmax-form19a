name: YieldMax Raw Extract

on:
  workflow_dispatch:

jobs:
  run-extract:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install requests beautifulsoup4

      - name: Run scraper
        run: |
          python form_19a_ingest.py

      - name: Upload CSV output
        uses: actions/upload-artifact@v4
        with:
          name: yieldmax-raw-extract
          path: yieldmax_raw_extract.csv

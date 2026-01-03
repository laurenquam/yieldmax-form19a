name: Form 19a-1 Ingestion (Manual)

on:
  workflow_dispatch:

jobs:
  ingest:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v3
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run ingestion
        run: python form_19a_ingest.py

      - name: Commit updated CSV
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add form19a_enriched.csv
          git commit -m "Manual Form 19a-1 update" || echo "No changes"
          git push

name: Form 19a-1 Ingestion (Manual)

on:
  workflow_dispatch:

permissions:
  contents: write
  actions: write

jobs:
  ingest:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run ingestion
        run: python form_19a_ingest.py

      - name: Verify CSV exists and preview
        run: |
          ls -la
          test -f form19a_enriched.csv
          echo "---- CSV preview ----"
          head -n 5 form19a_enriched.csv || true

      - name: Commit updated CSV
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add form19a_enriched.csv
          git status
          git commit -m "Manual Form 19a-1 update" || echo "No changes"
          git push

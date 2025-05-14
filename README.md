# 📊 Daily Research Impact Scraper

This project automatically collects and updates research impact metrics (e.g., citations, Altmetric data, open access status) for specified authors using the [Semantic Scholar API](https://api.semanticscholar.org/), [Altmetric](https://api.altmetric.com/), [CrossRef](https://api.crossref.org/), and [Unpaywall](https://unpaywall.org/).

Results are saved **daily** in structured CSV and JSON files and committed to the repository using a scheduled GitHub Actions workflow.

---

## 🚀 Features

- ✅ Daily scraping of research data (citations, open access, Altmetric mentions)
- ✅ Per-author CSV and JSON output
- ✅ Keyword tagging for:
  - Public health impact
  - Capacity building relevance
- ✅ Logging with timestamps
- ✅ Fully automated via GitHub Actions

---

## 📁 Directory Structure

```
├── csv/                       # Automatically generated CSVs per author
│   ├── jude_kong_impact_metrics.csv
│   └── nicola_l_bragazzi_impact_metrics.csv

├── json/                      # Automatically generated JSONs per author
│   ├── jude_kong_impact_metrics.json
│   └── nicola_l_bragazzi_impact_metrics.json

├── research_impact_batch.py  # Main Python script
├── requirements.txt          # Dependencies
├── research_impact_log.txt   # Daily logs
└── .github/
    └── workflows/
        └── research-impact-daily.yml   # GitHub Actions scheduler
```

---

## ⚙️ GitHub Actions Workflow

### 🔁 `.github/workflows/research-impact-daily.yml`

This workflow:

- Runs daily at **08:00 UTC**
- Executes the `research_impact_batch.py` script
- Automatically adds and commits any new or updated `.csv` and `.json` files

```yaml
on:
  schedule:
    - cron: '0 8 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update-impact-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python research_impact_batch.py
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add csv/*.csv json/*.json
          git commit -m "🔁 Daily update of research impact data: $(date -u '+%Y-%m-%d')" || echo "No changes"
          git push
```

---

## ✍️ Authors Tracked

You can update the `author_list` in `research_impact_batch.py`:

```python
author_list = [
    "Jude Kong",
    "Nicola L. Bragazzi"
]
```

---

## 📦 Setup (For Local Use)

1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/research-impact-scraper.git
   cd research-impact-scraper
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the script manually:
   ```bash
   python research_impact_batch.py
   ```

---

## 📜 License

This project is licensed under the MIT License.

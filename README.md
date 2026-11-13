# SNP-Disease Platform

An Arabic-supported bioinformatics platform for exploring SNP–disease associations from the
NHGRI-EBI GWAS Catalog, with an analysis of how Arab and Middle Eastern populations are
represented in genome-wide association studies.
Research and education use only: it is not a diagnostic tool.

**Diseases (10):** Type 2 Diabetes, Obesity, Hypertension, Coronary Artery Disease, Chronic
Kidney Disease, Asthma, Hypothyroidism, Rheumatoid Arthritis, Alzheimer's Disease, Breast Cancer.

**Features:** disease / variant / gene search in Arabic and English, evidence-based ranking,
flagging of Arab and Middle Eastern samples, disease comparison dashboard, plain-language
explanations, study summaries, Circos map, PRS teaching demo, admin dashboard, shareable links
(`?q=rs429358`, `?page=ranking`).

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
python -m pip install -r requirements.txt
python -m streamlit run app/main.py
```

On Windows you can also double-click `run.bat`. To create the first admin account, see
`docs/SECURITY.md` (settings `SNP_ADMIN_USERNAME` / `SNP_ADMIN_PASSWORD`).

## Research

| Study | Question | Report | Reproduce |
|---|---|---|---|
| 3.1 Representation | Share of GWAS studies and participants from Arab / Middle Eastern populations | `docs/research/01_representation.md` | `python -m analysis.representation` |
| 3.2 Classifier validation | Accuracy of detecting Arab / Middle Eastern samples in GWAS sample descriptions | `docs/research/02_classifier_validation.md` | `python -m analysis.classifier_validation score --sample B` |
| 3.3 Ranking validation | Do the evidence levels rank established disease genes first? | `docs/research/03_ranking_validation.md` | `python -m analysis.ranking_validation` |
| 3.4 Usability | SUS and task success with Arab users (protocol ready, data pending) | `docs/research/04_usability_study.md` | `python -m analysis.usability` |

Key findings so far: Arab participants are 0.04% of GWAS discovery participants and 0.91% of
studies include an Arab discovery sample; hypertension, chronic kidney disease and breast cancer
have no Arab or Middle Eastern discovery study in the catalog. The platform's classifier finds
these samples with high precision and recall. Associations carry an evidence level (Confirmed =
genome-wide significant in 2+ independent studies across the whole catalog; Strong = in one study) and
are ordered by statistical strength; this ranks established genes better than the former weighted
score (mean AUC 0.68 vs 0.62; difference 0.06, 95% CI 0.03-0.09).

The dataset is rebuilt from the GWAS Catalog with one command: `python -m pipeline.rebuild_dataset`.

## Project layout

```text
app/        Streamlit UI      main.py (entry), views/ (one file per page), ui/ (widgets, CSS)
core/       Business logic    search engine, diseases, regions, auth, i18n, PRS, summaries, ai/, admin/
pipeline/   Data preparation  extraction from the GWAS Catalog, cleaning, linking, ranking
analysis/   Research          analyses, annotations, reference loci, results and figures
tests/      Automated tests   (plus tests/load/ for load testing)
docs/       Documentation     ARCHITECTURE, SECURITY, research/, reports/
```

## Tests and quality

```bash
python -m pip install -r requirements-dev.txt
python -m pytest              # 220+ tests: data, search, security, every page, user flows, analyses
python -m ruff check .
```

Continuous integration runs ruff, pytest, bandit and pip-audit on every push
(`.github/workflows/ci.yml`). Performance and load results: `docs/reports/quality/QUALITY_REPORT.md`.

## Citation and licences

- Code: MIT (`LICENSE`). Data: derived from the NHGRI-EBI GWAS Catalog, see `DATA_SOURCES.md`.
- How to cite: `CITATION.cff`. Please also cite the GWAS Catalog (Sollis et al., NAR 2023).

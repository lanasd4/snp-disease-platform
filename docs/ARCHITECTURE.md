# Architecture

## Layers

```text
┌──────────────────────────────────────────────────────────────┐
│ app/            Presentation (Streamlit)                     │
│   main.py       entry point: page config, auth, routing      │
│   views/        one module per page  -> render_*_page()      │
│   ui/           shared widgets + styles.css                  │
├──────────────────────────────────────────────────────────────┤
│ core/           Business logic (used by the app)             │
│   paths.py      every file location (single source of truth) │
│   search_engine, auth, i18n, glossary, prs, study_summary    │
│   ai/           Ollama explanation agent + model management  │
│   admin/        ingestion, approval, final merge, GWAS sync  │
├──────────────────────────────────────────────────────────────┤
│ pipeline/       Offline data preparation (run by hand)       │
├──────────────────────────────────────────────────────────────┤
│ data/  database/  outputs/      Data the layers read/write   │
└──────────────────────────────────────────────────────────────┘
```

### Dependency rules

| Layer      | May import                    | Must not import          |
|------------|-------------------------------|--------------------------|
| `app/`     | `app.*`, `core.*`             | `pipeline.*`             |
| `core/`    | `core.*`                      | `app.*`                  |
| `pipeline/`| `core.paths`, `pipeline.*`    | `app.*`                  |

- Every path comes from `core/paths.py`. Do not compute
  `Path(__file__).parents[N]` in a module; import the constant instead.
- `app/main.py` is the only place that touches `sys.path` (it adds the
  project root so `app.*` and `core.*` resolve).
- The database location can be overridden with the `SNP_DATABASE_PATH`
  environment variable (used by the tests and useful for hosting).

## Folder map

```text
SNP_Disease_Platform/
├── app/
│   ├── main.py                 entry point + PAGES registry
│   ├── views/                  home, search, result_details, ranking,
│   │                           ai_explanation, study_summary, circos,
│   │                           prs, about, admin
│   ├── ui/components.py        cards, page header, CSS loader, DB counters
│   ├── ui/styles.css
│   └── assets/logo.png
├── core/
│   ├── paths.py                all project paths
│   ├── settings.py             env / Streamlit-secrets settings (admin bootstrap, registration)
│   ├── search_engine.py        disease / SNP / gene tri-search
│   ├── auth.py                 users, PBKDF2 hashing, login throttling
│   ├── i18n.py                 Arabic/English strings, t(), RTL switch
│   ├── glossary.py             glossary terms for explanations
│   ├── prs.py                  PRS prototype calculations
│   ├── study_summary.py        study summary builder
│   ├── ai/agent.py             local LLM (Ollama) explanations
│   ├── ai/model_manager.py     Ollama model checks / pulls
│   └── admin/                  common.py, data_ingestion.py,
│                               approval_merge.py, final_merge.py,
│                               gwas_connector.py
├── pipeline/                   see pipeline/README.md
├── tests/                      pytest suite
├── data/                       master lists, metadata, raw, processed
├── database/snp_platform.db    SQLite database
├── outputs/                    generated tables and trained models
├── docs/                       documentation (this file)
└── archive/                    local-only: old backups, legacy code, logs
```

## Request flow (Search page)

```text
user types "السكري"
  -> app/views/search.py           reads widgets, keeps session state
  -> core/search_engine.py          normalizes Arabic, detects rsID,
                                    filters data/processed/ranked_associations_initial.csv
  -> app/views/result_details.py    renders the selected result
       -> core/glossary.py, core/study_summary.py, core/ai/agent.py
```

## Data flow

```text
GWAS Catalog (online)  ──► pipeline/extract_data ──► data/raw/
data/raw/  ──► pipeline/clean_data ► normalize_* ► entity_linking ──► data/processed/
data/processed/  ──► pipeline/load_processed_data ──► database/snp_platform.db
database  ──► pipeline/extract_ranking_features ► association_ranking
          ──► data/processed/ranked_associations_initial.csv  (read by the app)
Admin uploads / GWAS sync ──► core/admin/* ──► staging ► approval ► final merge
```

## Adding a page

1. Create `app/views/<name>.py` exposing `render_<name>_page()`.
2. Put any logic that is not layout in `core/`.
3. Register it in `PAGES` in `app/main.py` and add its `nav.<name>` label in `core/i18n.py`.
4. The page is picked up by `tests/test_pages_smoke.py` automatically.

## Quality checks

```bash
python -m pytest            # imports, search engine, every page (guest + admin)
python -m ruff check .      # lint (config in pyproject.toml)
```

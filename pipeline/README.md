# Data pipeline

Offline scripts that build the data the app reads. The running app never calls
them. Run each stage from the project root as a module:

```bash
python -m pipeline.clean_data
```

| # | Stage | Reads | Writes |
|---|-------|-------|--------|
| 0 | `create_database` | `data/master_diseases.csv`, `data/disease_synonyms.csv` | `Disease`, `DiseaseSynonym` tables (drops and recreates them) |
| 0 | `load_sample_data` | `data/sample/*.csv` | demo tables (development only) |
| 1 | `extract_data` | GWAS Catalog (internet) | `data/raw/` |
| 2 | `clean_data` | `data/raw/` | `data/processed/cleaned_associations_v1.csv` |
| 3 | `normalize_diseases` | cleaned associations + DB diseases | disease-normalized associations |
| 4 | `normalize_genes_snps` | normalized associations | genes / SNPs CSVs |
| 5 | `entity_linking` | normalized entities | `associations_ready_for_db.csv` |
| 6 | `load_processed_data` | processed CSVs | `database/snp_platform.db` |
| 7 | `extract_ranking_features` | database | `ranking_features.csv` |
| 8 | `association_ranking` | ranking features | `ranked_associations_initial.csv` (used by the app) |
| 9 | `region_classifier` | ranked associations | `regional_tagged_associations.csv` |
| 10 | `prepare_regional_training_set` | regional tags | training set |
| 11 | `ml_region_classifier` | training set | `outputs/models/*.joblib` |
| – | `fuzzy_matching` | database | disease suggestion tables |

Stages 0 and 6 write to the database; back it up before running them.

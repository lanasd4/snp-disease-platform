# Data sources and attribution

## NHGRI-EBI GWAS Catalog
All association, variant, gene and study data in this repository are derived
from the NHGRI-EBI GWAS Catalog full associations file
(snapshot `gwas_online_snapshot_20260703_175831.zip`, downloaded July 2026).

Please cite:

> Sollis E, Mosaku A, Abid A, et al. The NHGRI-EBI GWAS Catalog: knowledgebase
> and deposition resource. *Nucleic Acids Research* 2023;51(D1):D977-D985.
> doi:10.1093/nar/gkac1010. PMID 36350656.

Licence: EMBL-EBI Terms of Use for the Catalog; most underlying datasets are
released under CC0, a few under their own terms (see the "Usage License"
column on the GWAS Catalog downloads page). This repository adds no further
restrictions to the data.

## Derived files
| Path | Content |
|---|---|
| `data/raw/gwas_catalog_platform_subset_raw.tsv` | Balanced subset for the ten diseases (pipeline/extract_from_catalog.py) |
| `data/processed/`, `database/snp_platform.db` | Cleaned, linked and ranked associations (pipeline/rebuild_dataset.py) |
| `analysis/results/` | Results of the analyses in docs/research/ |
| `analysis/reference/established_loci.csv` | Genes from the abstracts of the cited discovery papers (PubMed ids in the file) |
| `analysis/annotation/` | Manual annotations of GWAS sample descriptions (docs/research/02_*) |

## Other identifiers
- dbSNP rsIDs and PubMed ids are used as identifiers and links only.

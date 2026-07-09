# manual_supp_tables/ — committed curator-provided per-isolate tables

Drop a curator-downloaded **per-isolate supplementary table** here, named by **study accession**:

```
manual_supp_tables/<study_accession>.<ext>      # e.g. PRJEB28400.csv
```

Accepted extensions: `.xlsx .xls .csv .tsv .docx .pdf` (parsed by
`engine/local_supplements.py`, the same parser the open-access path uses).

## Why this folder exists (and is committed)

The per-sample stage fills `host` / `country` / `collection_date` / `isolation_source` per isolate
from a paper's supplementary table. When the table is paywalled, not mirrored in Europe PMC, or the
paper has **no PMCID**, the curator supplies it by hand. Historically that went to the *gitignored*
`data/sample_lv_attributes/manual_download_supp/`, so tables were **silently lost** in the
OneDrive→developer migration (this is what dropped PRJEB28400's table, taking its ~719-isolate
`isolation_source` to 0%). This folder is **version-controlled** so a hand-provided table can never be
lost again, and the orphan audit fails loud if a recoverable table is left unwired.

## How it is read

`engine/run_full_metadata_agent.py` passes `[manual_supp_tables/, manual_download_supp/]` to the
per-sample stage. **This committed folder has precedence**: a table here shadows a legacy one for the
same accession. Auto-read on every run — no extra step. `evaluation/audit_manual_curation.py` cross-
checks that every table here (and every recoverable `project_k/.../ENA_projects/<acc>/data.csv`) is
actually consumed.

## Provenance

Many tables come from `project_k/data/raw/metadata/study_level_metadata/ENA_projects/<acc>/data.csv`
(the curator's ENA per-study downloads). Copy the relevant `data.csv` in as `<acc>.csv`.

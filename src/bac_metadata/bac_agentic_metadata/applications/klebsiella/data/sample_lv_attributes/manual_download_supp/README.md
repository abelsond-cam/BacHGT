# manual_download_supp/ — curator-provided per-isolate tables (tracked in git)

The **single** home for hand-provided supplementary tables. Name each by **study accession**:

```
manual_download_supp/<study_accession>.<ext>   # e.g. PRJEB28400.csv, PRJNA675776.xlsx, PRJEB24085.pdf
```

Accepted extensions: `.xlsx .xls .csv .tsv .txt .docx .pdf` — parsed by `engine/local_supplements.py` with the
same parser the open-access path uses. A `.txt` has its delimiter sniffed (tab → comma → whitespace).

## Why it is version-controlled

The per-sample stage fills `host` / `country` / `collection_date` / `isolation_source` per isolate from a
paper's supplementary table. When the table is paywalled, absent from Europe PMC, or the paper has **no
PMCID**, the curator supplies it by hand. This folder used to be gitignored — so tables were **silently lost**
in the OneDrive→developer migration, which is what took PRJEB28400's ~719-isolate `isolation_source` to 0%.
Tracking them means a hand-provided table can never be lost again. They are small; losing one is worse than
storing it.

> Some files are publisher supplementary material. Keep that in mind if this repo is ever made public.

## Naming matters — the file must be `<accession>.<ext>`

Resolution is **by filename stem = study accession**. A file named after the paper (e.g.
`journal.pone.0231119.pdf`) will **not** link; rename it to its accession (`PRJDB6407.pdf`).

## What links, and what doesn't

A table must **parse** and **anchor** — some column's values must match this study's ENA sample identifiers
(matched *by value*, name-agnostic, so `Isolate` / `SPARK_ID` / `sample name` all work). Track it with:

```bash
uv run python -m bac_metadata.bac_agentic_metadata.evaluation.table_linkability --app klebsiella
# -> data/diagnostics/table_linkability.{md,tsv}
```

It reports `LINKED` / `NO_ID_MATCH` (keys on a strain name absent from ENA — a two-hop/linkage target) /
`WEAK_MATCH` / `PARSE_EMPTY` / `STUDY_NOT_IN_COHORT`, per file and format. `evaluation/audit_manual_curation.py`
additionally fails loud on any recoverable table left unwired.

## Provenance

Many tables come from `project_k/data/raw/metadata/study_level_metadata/ENA_projects/<acc>/data.csv` — copy the
relevant `data.csv` in as `<acc>.csv`.

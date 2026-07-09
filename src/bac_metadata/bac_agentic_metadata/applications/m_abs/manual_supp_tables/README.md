# manual_supp_tables/ — committed curator-provided per-isolate tables (M. abscessus)

Drop a curator-downloaded **per-isolate supplementary table** here, named by **study accession**:

```
manual_supp_tables/<study_accession>.<ext>      # accepted: .xlsx .xls .csv .tsv .docx .pdf
```

Same mechanism as the Klebsiella sibling — auto-read by the per-sample stage
(`engine/local_supplements.py`), **committed** so a hand-provided table can never be silently lost,
and cross-checked by `evaluation/audit_manual_curation.py --app m_abs`. This folder has precedence over
the legacy gitignored `data/sample_lv_attributes/manual_download_supp/`.

The M. abscessus manual-download loop was never serviced in earlier runs; papers/tables surfaced by
`run_health` go into `data/find_papers/manual_download/` (PDFs) and here (per-isolate tables).

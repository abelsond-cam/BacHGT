# M. abscessus input availability (structured pre-scan)

`ATB_metadata_Mabs_2025_release.xlsx` — **7217 records / 133 studies**. Structured availability per target field (fraction already filled by the spreadsheet, after stripping placeholders).

## Overall per-field availability

| field | structured % | answered_by_data | partial | needs_paper |
|---|---|---|---|---|
| country | 77% | 71 | 2 | 60 |
| collection_date | 68% | 61 | 4 | 68 |
| isolation_source | 65% | 49 | 5 | 79 |
| host | 76% | 58 | 7 | 68 |
| cf_status | 21% | 4 | 2 | 127 |
| smoking_status | 0% *(paper-only — no source column)* | 0 | 0 | 133 |
| ast | 0% *(paper-only — no source column)* | 0 | 0 | 133 |

## cf_status detail (the phenotype slot)

- human binary (CF / Non-CF): **1547** records (CF + non-CF)
- non-human (Animal / Environmental): 3
- unknown (`?`): 143
- blank: 5524

**Reading:** country / collection_date / isolation_source / host are largely answered by the data; cf_status is partly pre-filled (the agentic run fills the blanks from papers / whole-study); **smoking and AST are entirely paper-derived** (0% structured) — that is where the agentic run's value concentrates.

Per-(study x field) detail: `input_availability.tsv`.

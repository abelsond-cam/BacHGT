# Batch 2 (mabs_21_40) — manual fetch worklist

Download each supplementary FILE from the paper page below, save as `<accession>.xlsx` (or `.csv`) into
`applications/m_abs/data/sample_lv_attributes/manual_download_supp/`. Then I re-run (cache-backed) to fold them in.
Papers to download as PDFs go to `applications/m_abs/data/find_papers/manual_download/<accession>.pdf`.

## A. Downloadable supplementary FILES (highest value — a real supp table exists)

| study | missing fields | supp ref | paper (click → find the supp) | save as |
|---|---|---|---|---|
| PRJDB17850 | date, host, iso | Table S1 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10433864/ | `PRJDB17850.xlsx` |
| PRJDB13427 | date | Table S1 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10433864/ | `PRJDB13427.xlsx` |
| PRJEB57933 | iso | Supplementary Table S1 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10606986/ | `PRJEB57933.xlsx` |
| PRJNA523365 | iso | Supplementary Table 2 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8390669/ | `PRJNA523365.xlsx` |
| PRJNA1051626 | cf_status | Table S1 (spectrum.01056-24-s0001.xlsx) | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11619595/ | `PRJNA1051626.xlsx` |

> PRJDB17850 + PRJDB13427 share one paper (PMC10433864) — its Table S1 likely covers both.

## B. Per-isolate data is in the MAIN TEXT (Table 1/2, no separate supp file — copy the table by hand if worth it)

| study | missing fields | table | paper | save as |
|---|---|---|---|---|
| PRJNA718117 | cf_status, host | Table 1 (main text) | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10499228/ | `PRJNA718117.xlsx` |
| PRJEB61124 | cf_status | Table 1 (main text) | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10979023/ | `PRJEB61124.xlsx` |
| PRJNA315990 | cf_status, iso | Table 1 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5034138/ | `PRJNA315990.xlsx` |
| PRJEB6776 | date | Table 2 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4357290/ | `PRJEB6776.xlsx` |

## C. Papers to fetch (PDF) — only one is resolvable

| study | paper | save as |
|---|---|---|
| PRJNA1080355 | https://doi.org/10.1016/j.ijantimicag.2024.107223 | `PRJNA1080355.pdf` (paper has no per-isolate table though — low value) |

## D. No paper found (EBI record only — nothing to fetch)

PRJEB36331, PRJNA353361 (both large per-sample gaps but no locatable paper), plus EXHAUSTED PRJNA1123827.

## SKIP (paper checked, no per-isolate table — no action)

PRJNA1211657, PRJDB15290, PRJEB9515, PRJNA691364.

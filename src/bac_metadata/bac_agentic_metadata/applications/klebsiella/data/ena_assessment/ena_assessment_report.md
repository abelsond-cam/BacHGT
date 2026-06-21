# Stage 1 validation summary

## What this validates
For each of the **150 curated rows** we compare the **prior finding** (your Google Sheet curation: `prior_isolates_in_study`) against **what the engine independently found in ENA** (`ena_klebsiella_samples`, `ena_total_runs`, `n_child_studies` — all from the live ENA `read_run` interrogation, not the sheet). `coverage = prior_isolates / ena_klebsiella`. The `classification` + `note` columns in the TSV say, per row, how the two relate. This is the check that the engine reproduces the manual EBI-sizing step correctly.

## Verdict — classification breakdown
```
classification
whole_project                 67
subsample                     26
ena_underlabels_klebsiella    22
shared_accession              15
review_prior_exceeds_ena      13
no_curated_count               4
review_no_ena_records          2
umbrella                       1
```
- **whole_project** (67): engine confirms the prior paper ≈ the whole ENA project
- **subsample** (26): prior paper covers a subsample of a larger ENA project
- **shared_accession** (15): one ENA accession is split across several prior papers
- **umbrella** (1): one ENA accession is many substudies (needs splitting)
- **ena_underlabels_klebsiella** (22): ENA has the records but labels fewer as Klebsiella by scientific_name; curation more complete (taxon sizing is a lower bound) — not a curation error
- **review_prior_exceeds_ena** (13): prior curated MORE than ENA holds under this accession — review
- **review_no_ena_records** (2): ENA has no records under the accession — review
- **no_curated_count** (4): sheet has no isolates_in_study — nothing to compare

## Umbrella accessions (one accession aggregating many substudies)
Flagged via distinct child studies; one 'best paper' cannot describe these. `PRJEB74192` (One Health Norway) is the canonical training case.
```
study_accession  n_child_studies  ena_taxon_samples
     PRJEB74192                9               3261
```

## Lowest coverage (prior paper vs what ENA holds)
```
                 paper_short_title  prior_isolates_in_study  ena_klebsiella_samples  ena_total_samples  coverage                                                                                                                              note
                  cdc_surveillance                    322.0                   12456              51951  0.025851 paper is a subsample of a larger project (curated 322 of 12456 ENA Klebsiella, coverage 0.03) — e.g. rolling-surveillance deposit
                  ghana_one_health                    573.0                    6354               6368  0.090179                 accession shared by 2 curated papers; this paper is one slice (curated 573 of 6354 ENA Klebsiella, coverage 0.09)
                       CCRE survey                    313.0                    2904               3434  0.107782  paper is a subsample of a larger project (curated 313 of 2904 ENA Klebsiella, coverage 0.11) — e.g. rolling-surveillance deposit
cpe_surveillance_five_us_hospitals                    104.0                     730               1219  0.142466   paper is a subsample of a larger project (curated 104 of 730 ENA Klebsiella, coverage 0.14) — e.g. rolling-surveillance deposit
                      ghru_nigeria                    139.0                     778               2331  0.178663   paper is a subsample of a larger project (curated 139 of 778 ENA Klebsiella, coverage 0.18) — e.g. rolling-surveillance deposit
                     CC14 KP clone                    457.0                    1820               1820  0.251099  paper is a subsample of a larger project (curated 457 of 1820 ENA Klebsiella, coverage 0.25) — e.g. rolling-surveillance deposit
                 melb_surveillance                     16.0                      58                 58  0.275862     paper is a subsample of a larger project (curated 16 of 58 ENA Klebsiella, coverage 0.28) — e.g. rolling-surveillance deposit
                              None                    293.0                     948              14702  0.309072                  accession shared by 2 curated papers; this paper is one slice (curated 293 of 948 ENA Klebsiella, coverage 0.31)
                      vetinary_fda                    204.0                     630               1559  0.323810   paper is a subsample of a larger project (curated 204 of 630 ENA Klebsiella, coverage 0.32) — e.g. rolling-surveillance deposit
             japanese_surveillance                    168.0                     388                388  0.432990   paper is a subsample of a larger project (curated 168 of 388 ENA Klebsiella, coverage 0.43) — e.g. rolling-surveillance deposit
```

## Review queue — prior curated count exceeds / disagrees with ENA
```
                          paper_short_title  prior_isolates_in_study  ena_klebsiella_samples  ena_total_samples                                                                                                                                                                                                                                                                                        note
                                 icu_hannoi                   3153.0                     745               1950                                                                                                                                     prior curated 3153 > ENA total 1950 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
                             melb_superbugs                    190.0                       0                  0                                                                                                                                                                              prior curated 190 but ENA has no records under this accession (assembly-only / wrong accession) — manual check
       columbia_irvine_polymyxin_resistance                    388.0                     340                340                                                                                                                                       prior curated 388 > ENA total 340 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
bangladesh_child_heatlh_research_foundation                    599.0                     567                567                                                                                                                                       prior curated 599 > ENA total 567 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
                      uganda_and_malawi_amr                   6508.0                    1603               6168                                                                                                                                     prior curated 6508 > ENA total 6168 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
                        pakistan_klebsiella                    227.0                     221                221 prior curated 227 > ENA total 221 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check — paper_link is Pathogenwatch: count scraped from a Pathogenwatch/KlebNET collection, not this ENA accession (expected; do not chase)
                     dutch_cpe_surveillance                    307.0                      80                167                                                                                                                                       prior curated 307 > ENA total 167 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
                                       None                    356.0                      44                100 prior curated 356 > ENA total 100 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check — paper_link is Pathogenwatch: count scraped from a Pathogenwatch/KlebNET collection, not this ENA accession (expected; do not chase)
                         China colonisation                    241.0                       0                  0                                                                                                                                                                              prior curated 241 but ENA has no records under this accession (assembly-only / wrong accession) — manual check
                   Malawi_neonatal_outbreak                    898.0                       2                  2   prior curated 898 > ENA total 2 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check — paper_link is Pathogenwatch: count scraped from a Pathogenwatch/KlebNET collection, not this ENA accession (expected; do not chase)
                             Dutch plasmids                    479.0                     144                144                                                                                                                                       prior curated 479 > ENA total 144 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
                Desinfectant susceptibility                    241.0                     184                225                                                                                                                                       prior curated 241 > ENA total 225 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
                   India_enterobacteriaceae                    982.0                      14                 16  prior curated 982 > ENA total 16 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check — paper_link is Pathogenwatch: count scraped from a Pathogenwatch/KlebNET collection, not this ENA accession (expected; do not chase)
                   India_enterobacteriaceae                    608.0                      14                 16  prior curated 608 > ENA total 16 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check — paper_link is Pathogenwatch: count scraped from a Pathogenwatch/KlebNET collection, not this ENA accession (expected; do not chase)
                                 Swiss_kleb                    272.0                     261                261                                                                                                                                       prior curated 272 > ENA total 261 under this accession — isolates likely under other accessions / RefSeq-only / a multi-accession paper; manual check
```

## Completeness (engine-computed, three states)
Mean per-field completeness over the 150 accessions we hold, across the base ATB metadata, after the per-project ready_to_merge backfill, and after parse/categorise normalisation. The base→post-merge gain is the manual backfill the engine must reproduce.
```
field                 base  postmerge    norm  backfill(Δ)
country               0.77       0.93    0.93       +0.162
collection_date       0.73       0.83    0.79       +0.101
isolation_source      0.58       0.72    0.67       +0.139
host                  0.62       0.85    0.84       +0.234
```

## Completeness reconcile (vs parsed_per_project)
_parsed_per_project not read (no Google credentials configured) — set `BAC_GOOGLE_CLIENT_SECRET` to enable the per-project reconcile._

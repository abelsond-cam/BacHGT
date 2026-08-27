# metadata_v2 overwrite candidates — reviewable artefact (combine step ii)

_Read-only, deterministic. Blank-fills never overwrite; these are the per-sample stage's gated replacements of a **non-blank** ENA value — the only overwrites a v2 combine would apply. Review these before step iii (`combine.apply_gated_overwrites`). Nothing here is applied yet._

## Reconciliation to wrap-up §5c

| field | candidates | §5c of record | ✓ |
|---|--:|--:|:-:|
| country | 16 | 16 | ✅ |
| collection_date | 1014 | 1014 | ✅ |
| isolation_source | 2037 | 2037 | ✅ |
| host | 38 | 38 | ✅ |
| **TOTAL** | **3105** | **3105** | **✅** |

**Reconciliation: ✅ EXACT** (3015 of 3105 candidates genuinely change the value; the rest differ only in case/whitespace and are inert).

## Summary by field & class

| field | class | rows | flagged |
|---|---|--:|--:|
| collection_date | date_same_year_refinement | 1007 | 0 |
| collection_date | date_unparsed | 3 | 3 |
| collection_date | date_year_changed | 4 | 4 |
| country | categorical_change | 16 | 0 |
| host | categorical_change | 1 | 0 |
| host | no_change | 37 | 37 |
| isolation_source | categorical_change | 1984 | 29 |
| isolation_source | no_change | 53 | 53 |

## (b) collection_date — refinements

**1007 same-year refinements** (e.g. `2019` → `2019-11-28`): the sanctioned low-risk exception — the year is preserved and only granularity is added. Sample:

| study_accession | sample_accession | ena_value | applied_value | evidence |
|---|---|---|---|---|
| PRJEB48990 | SAMEA11350734 | 2019 | 2019-11-28 00:00:00 | mgen-9-1016-s001.xlsx:ERS8995927 |
| PRJEB48990 | SAMEA11350784 | 2020 | 2020-03-12 00:00:00 | mgen-9-1016-s001.xlsx:ERS8995977 |
| PRJEB48990 | SAMEA11350740 | 2015 | 2015-12-10 00:00:00 | mgen-9-1016-s001.xlsx:ERS8995934 |
| PRJEB48990 | SAMEA11351070 | 2017 | 2017-07-29 00:00:00 | mgen-9-1016-s001.xlsx:ERS8996262 |
| PRJEB48990 | SAMEA11350921 | 2017 | 2017-12-01 00:00:00 | mgen-9-1016-s001.xlsx:ERS8996113 |
| PRJEB48990 | SAMEA11350874 | 2018 | 2018-08-11 00:00:00 | mgen-9-1016-s001.xlsx:ERS8996067 |
| PRJEB48990 | SAMEA11350733 | 2018 | 2018-11-05 00:00:00 | mgen-9-1016-s001.xlsx:ERS8995925 |
| PRJEB48990 | SAMEA11350947 | 2019 | 2019-08-31 00:00:00 | mgen-9-1016-s001.xlsx:ERS8996141 |

### ⚠ 4 year-CHANGED (review — violates the same-year rule)

| study_accession | sample_accession | ena_value | applied_value | evidence | paper |
|---|---|---|---|---|---|
| PRJEB63361 | SAMEA114111058 | 2019 | 22/01/2020 | ppat.1013859.s006.xlsx:ERS16091783 | https://pmc.ncbi.nlm.nih.gov/articles/PMC12810914/ |
| PRJEB1271 | SAMEA2053953 | 1800/2014 | 2007 | 13059_2019_1785_MOESM2_ESM.xlsx:9776_8#80 | https://pmc.ncbi.nlm.nih.gov/articles/PMC6717969/ |
| PRJEB38898 | SAMEA6963083 | 2019 | 2020-08-01 00:00:00 | mgen-7-0519-s002.xlsx:ERS4672944 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8190610/ |
| PRJEB38898 | SAMEA6963084 | 2019 | 2020-08-01 00:00:00 | mgen-7-0519-s002.xlsx:ERS4672945 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8190610/ |

### ⚠ 3 unparseable year (review)

| study_accession | sample_accession | ena_value | applied_value | evidence |
|---|---|---|---|---|
| PRJEB6891 | SAMEA3357401 | 2014-02 | 17/02/14 | PRJEB6891.csv:ERR1023683 |
| PRJEB34643 | SAMEA11291420 | 2019 | 28/02/19 | spectrum02376-21_supp_1_seq6.xlsx:MVK-09F642 |
| PRJNA675776 | SAMN16721988 | 2018 | 2108-10-18 00:00:00 | PRJNA675776.xlsx:51615 |

## (a) categorical vague→specific — country / host / isolation_source

### country — 16 genuine changes, from 1 distinct ENA value(s)

_1 ENA value(s) fan out to several specifics (the healthy vague→specific pattern); 0 map one-to-one._

⚠ **All 16 rows shown** (concrete ENA value replaced — review each):

| study_accession | sample_accession | ena_value | applied_value | evidence | paper |
|---|---|---|---|---|---|
| PRJNA744003 | SAMN20064863 | Switzerland | Australia | 21-1265-Techapp-s1.pdf:N1130 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064867 | Switzerland | UAE | 21-1265-Techapp-s1.pdf:N1154 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064868 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1159 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064869 | Switzerland | Czechia | 21-1265-Techapp-s1.pdf:N1184 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064871 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1232 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064882 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1418 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064949 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1436 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064884 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1437 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064887 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1448 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064938 | Switzerland | USA | 21-1265-Techapp-s1.pdf:N1605 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064900 | Switzerland | USA | 21-1265-Techapp-s1.pdf:N1626 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064947 | Switzerland | USA | 21-1265-Techapp-s1.pdf:N1683 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064940 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1692 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064941 | Switzerland | China | 21-1265-Techapp-s1.pdf:N1694 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064942 | Switzerland | Australia | 21-1265-Techapp-s1.pdf:N1696 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |
| PRJNA744003 | SAMN20064944 | Switzerland | Myanmar | 21-1265-Techapp-s1.pdf:N1712 | https://pmc.ncbi.nlm.nih.gov/articles/PMC8462332/ |

### host — 1 genuine changes, from 1 distinct ENA value(s)

_0 ENA value(s) fan out to several specifics (the healthy vague→specific pattern); 1 map one-to-one._

⚠ **All 1 rows shown** (concrete ENA value replaced — review each):

| study_accession | sample_accession | ena_value | applied_value | evidence | paper |
|---|---|---|---|---|---|
| PRJEB48990 | SAMEA11351173 | environmental | environment_soil | mgen-9-1016-s001.xlsx:ERS8996365 (rescued 'Environmental') | https://pmc.ncbi.nlm.nih.gov/articles/PMC10272877/ |

### isolation_source — 1984 genuine changes, from 21 distinct ENA value(s)

_9 ENA value(s) fan out to several specifics (the healthy vague→specific pattern); 12 map one-to-one._

Top ENA values overwritten (by volume):

| ena_value | n_rows | n_distinct_new |
|---|---|---|
| clinical material | 1309 | 38 |
| human body sites or biosamples | 226 | 27 |
| clinical sample | 115 | 5 |
| surface | 98 | 17 |
| chicken meat | 80 | 9 |
| food | 62 | 21 |
| salad | 25 | 18 |
| sewage | 24 | 2 |
| blood_blood | 21 | 1 |
| environment | 12 | 9 |
| st4_stool_organism_2 | 2 | 1 |
| room_2_c_organism_2 | 1 | 1 |

Sample rows:

| study_accession | sample_accession | ena_value | applied_value | evidence |
|---|---|---|---|---|
| PRJEB36683 | SAMEA6531361 | Human body sites or biosamples | SCALP | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891098 |
| PRJEB36683 | SAMEA6531354 | Human body sites or biosamples | BLOOD | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891091 |
| PRJEB36683 | SAMEA6531286 | Human body sites or biosamples | URINE | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891023 |
| PRJEB36683 | SAMEA6531376 | Human body sites or biosamples | EAR | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891113 |
| PRJEB36683 | SAMEA6531312 | Human body sites or biosamples | LUNG | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891049 |
| PRJEB36683 | SAMEA6531307 | Human body sites or biosamples | ABDOMEN | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891044 |
| PRJEB36683 | SAMEA6531340 | Human body sites or biosamples | BLOOD | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891077 |
| PRJEB36683 | SAMEA6531323 | Human body sites or biosamples | URINE | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891060 |
| PRJEB36683 | SAMEA6531330 | Human body sites or biosamples | URINE | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891067 |
| PRJEB36683 | SAMEA6531333 | Human body sites or biosamples | BLOOD | 13073_2024_1332_MOESM1_ESM.xlsx:ERR3891070 |

## ⚠ Flagged for review (consolidated)

126 row(s) carry a review flag. `no_change` = case/whitespace-only (inert, not applied); `shortened` = new value is a shorter substring of the ENA one (typically a benign de-dup like `Blood_Blood`→`Blood` or an extract-from-token like `ST1_Stool_Organism_2`→`Stool`); `year_changed` / `date_unparsed` = the dates that break the same-year rule. Look before approving.

| review_flag | rows |
|---|--:|
| no_change | 90 |
| shortened | 29 |
| year_changed | 4 |
| date_unparsed | 3 |

| field | study_accession | ena_value | applied_value | review_flag | paper |
|---|---|---|---|---|---|
| collection_date | PRJEB63361 | 2019 | 22/01/2020 | year_changed | https://pmc.ncbi.nlm.nih.gov/articles/PMC12810914/ |
| collection_date | PRJEB6891 | 2014-02 | 17/02/14 | date_unparsed | https://pmc.ncbi.nlm.nih.gov/articles/PMC5850561/ |
| collection_date | PRJEB1271 | 1800/2014 | 2007 | year_changed | https://pmc.ncbi.nlm.nih.gov/articles/PMC6717969/ |
| collection_date | PRJEB34643 | 2019 | 28/02/19 | date_unparsed | https://pmc.ncbi.nlm.nih.gov/articles/PMC8865463/ |
| collection_date | PRJNA675776 | 2018 | 2108-10-18 00:00:00 | date_unparsed | https://pmc.ncbi.nlm.nih.gov/articles/PMC9047677/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | Blood_Blood | Blood | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST1_Stool_Organism_2 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST2_Stool_Organism_1 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST3_Stool_Organism_1 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST3_Stool_Organism_3 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST4_Stool_Organism_2 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST4_Stool_Organism_2 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST4_Stool_Organism_4 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| isolation_source | PRJNA741123 | ST4_Stool_Organism_6 | Stool | shortened | https://pmc.ncbi.nlm.nih.gov/articles/PMC9160058/ |
| collection_date | PRJEB38898 | 2019 | 2020-08-01 00:00:00 | year_changed | https://pmc.ncbi.nlm.nih.gov/articles/PMC8190610/ |
| collection_date | PRJEB38898 | 2019 | 2020-08-01 00:00:00 | year_changed | https://pmc.ncbi.nlm.nih.gov/articles/PMC8190610/ |

## How to approve (feeds combine step iii)

Review `v2_overwrite_candidates.tsv`, keep the rows to apply (a natural default: all `date_same_year_refinement` + the categorical rows you accept, minus anything flagged you reject), and pass that subset to `combine.apply_gated_overwrites` (B3). Blank-fills (step i) need no sign-off — they cannot overwrite.


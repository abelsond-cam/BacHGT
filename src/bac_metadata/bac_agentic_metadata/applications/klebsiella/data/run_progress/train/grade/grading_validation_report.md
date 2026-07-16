# study grading validation — grading vs trusted ground truth (train,val)

Graded rows in train,val: **109**.

Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no reliable ground truth and is **not scored** (spot-check only).

_Applied 13 David-verified amr_study GT corrections (gt_corrections.tsv)._

## amr_study  (accuracy 0.93 over n=86) — PRIMARY

```
predicted     amr  mixed  surveillance
ground_truth                          
amr            47      2             1
mixed           0      5             1
surveillance    1      1            28
```

## study_setting — PRIMARY

_Applied 6 David-verified study_setting GT corrections (gt_corrections.tsv)._

Accuracy 0.98 over n=95 (frozen sidecar).

```
predicted     community  hospital  mixed
ground_truth                            
community             7         0      0
hospital              0        78      1
mixed                 0         1      8
```

## Disagreements (verbatim; record, do not assume the sheet is right)


### amr_study (6 disagreements)

- `PRJEB39943` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Both resistant and comparator susceptible isolates were collected.'
- `PRJEB27256` grader=**mixed** sheet=**surveillance** (raw: 'Surveillance')
  - grader quote: 'All putative ESBL-producing KpSC blood (n=149) and urine isolates (n=91) from 2001–15 registered in the NORM database were included in the study. For comparison, a subset of non-ESBL blood culture iso'
- `PRJEB17615` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'sequencing of retrospective susceptible and resistant isolates (to be undertaken at The Sanger Institute)'
- `PRJNA789565` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: '44 of 85 (51.8%) of the clinical isolates from cases were pan-sensitive apart from intrinsic ampicillin resistance. ... Phenotypic AMR rates were low (<25%).'
- `PRJNA787062` grader=**surveillance** sheet=**amr** (raw: 'surveillance')
  - grader quote: 'Enterobacteriaceae isolates (n = 301) were subjected to whole-genome sequencing using Illumina HiSeq 2500. ... Among 301 Enterobacteriaceae, 22 Klebsiella pneumoniae, 2 Klebsiella variicola, and 3 Ent'
- `PRJNA395086` grader=**amr** sheet=**surveillance** (raw: 'Surveillance')
  - grader quote: 'Carbapenem resistance was defined as displaying resistance to ≥1 carbapenem following MIC testing with a Vitek2 system... Isolates that were not resistant to at least 1 carbapenem following the Etest '

### study_setting (2 disagreements)

- `PRJNA686897` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: '20 medical intensive care units (ICUs) in 20 short-term acute care hospitals, 7 LTACHs, and 8 vSNFs in the Chicago region were invited to participate in serial 1-day point-prevalence surveys'
- `PRJEB21277` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'Colonizing samples were detected on programmes of surveillance culture of rectal swabs or faeces from people admitted to healthcare facilities... samples were from hospitals in the following counties:'

## Spot-check (no clean ground truth — NOT scored)

### cohort_age (grader value vs free-text newborn_cohort)

- `PRJEB36683` grader=mixed (newborn_cohort raw: 'neonate, children, and adults; sample level age info availab')
- `PRJEB42462` grader=newborn_young_child (newborn_cohort raw: 'Adults and neonates. Sample level age bracket in table 1')
- `PRJNA475751` grader=adult (newborn_cohort raw: 'patient age not provided')
- `PRJEB29740` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults; sample level age data are ava')
- `PRJEB28400` grader=adult (newborn_cohort raw: 'Adults, median age of 50+ years, age info summarized in tabl')
- `PRJEB50614` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults; sample level age data are ava')
- `PRJNA845975` grader=newborn_young_child (newborn_cohort raw: 'Neonates, age info summarized in table S1, sample level age ')
- `PRJNA1028672` grader=adult (newborn_cohort raw: 'Adults only, age from 14-94, sample level age info available')
- `PRJNA855907` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJEB29143` grader=adult (newborn_cohort raw: 'patient age not provided')
- `PRJEB6891` grader=adult (newborn_cohort raw: 'Adult, has PatientAge and Sex and Hosp acquired')
- `PRJNA415194` grader=adult (newborn_cohort raw: 'Adults only, age 63-82; age info summarized in table S2, sam')
- `PRJEB46513` grader=newborn_young_child (newborn_cohort raw: 'neonatal meta-analysis')
- `PRJNA686897` grader=adult (newborn_cohort raw: 'Adults ~ 60 years old; age data are available in table 1')
- `PRJEB63361` grader=mixed (newborn_cohort raw: "Mix of adults and paeds but don't have age data")
- `PRJEB33565` grader=newborn_young_child (newborn_cohort raw: 'neonatal meta-analysis')
- `PRJEB17615` grader=mixed (newborn_cohort raw: 'Mixed by NICU enriched')
- `PRJNA557275` grader=adult (newborn_cohort raw: 'Adults aged 18-90, median of 61, age info summarized in tabl')
- `PRJNA789565` grader=adult (newborn_cohort raw: 'Adults ~ 60 years old; age data are available in table 1')
- `PRJEB39867` grader=adult (newborn_cohort raw: 'All age > 18 years, paeds excluded')
- `PRJNA549322` grader=adult (newborn_cohort raw: 'Adults, median age of 60+, age info summarized in table 1, s')
- `PRJNA789336` grader=adult (newborn_cohort raw: 'Adults, 40+; age info summarized in table 3, sample level ag')
- `PRJNA341927` grader=adult (newborn_cohort raw: 'patient age not provided')
- `PRJEB22252` grader=mixed (newborn_cohort raw: 'Name suggests neonates')
- `PRJEB24970` grader=newborn_young_child (newborn_cohort raw: 'neonatal')
- `PRJEB36486` grader=mixed (newborn_cohort raw: 'Children and adults aged 16-76, age info summarized in table')
- `PRJNA765801` grader=adult (newborn_cohort raw: 'Adults, median age of 68 years old; age info summarized in t')
- `PRJEB58216` grader=adult (newborn_cohort raw: 'Adults, median age of 49, sample level age info available in')
- `PRJEB30134` grader=mixed (newborn_cohort raw: 'Contains some neonatal data, but mostly adults, with median ')
- `PRJEB58018` grader=adult (newborn_cohort raw: 'Adults, median age of 40+; age info summarized in table, sam')
- `PRJEB1563` grader=mixed (newborn_cohort raw: '197 isolates from neonates and children (0-14 years) and 24 ')
- `PRJNA787062` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults')
- `PRJDB12075` grader=adult (newborn_cohort raw: 'Older adults, 90+ years old; age info summarized in table 5,')
- `PRJEB39293` grader=mixed (newborn_cohort raw: 'Linked mother-newborn child - provided on indiv basis?')
- `PRJEB21605` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJNA564992` grader=mixed (newborn_cohort raw: '41 isolates derived from children (<17 years) and 771 from a')
- `PRJNA646358` grader=mixed (newborn_cohort raw: 'Adults, median age of 40+; age info summarized in table 1, s')
- `PRJNA804332` grader=mixed (newborn_cohort raw: 'Neonates')
- `PRJNA1054115` grader=mixed (newborn_cohort raw: 'Children and adults, sample level age info not provided')
- `PRJNA1087366` grader=newborn_young_child (newborn_cohort raw: 'neonatal sepsis')
- `PRJNA885285` grader=mixed (newborn_cohort raw: 'Children, not neonates (2-14 years old), age info summarized')
- `PRJEB1800` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJNA978102` grader=mixed (newborn_cohort raw: 'included patients from 2 months to 96 years, median of 60+, ')
- `PRJEB74083` grader=adult (newborn_cohort raw: 'Adults, range 29-97 years old, summarized in text, sample le')
- `PRJEB19322` grader=newborn_young_child (newborn_cohort raw: 'neonatal meta-analysis')
- `PRJNA351909` grader=adult (newborn_cohort raw: 'Adult, has PatientAge and Sex and Hosp acquired')
- `PRJEB20799` grader=newborn_young_child (newborn_cohort raw: 'part Pathogenwatch neonatal collection')
- `PRJNA641987` grader=newborn_young_child (newborn_cohort raw: 'neonatal BSI (62) and paediatric (n=32)')

### amr_target / amr_method where amr_study in {amr,mixed}

- `PRJEB39943` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB36683` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB37378` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'ESBLs')
- `PRJDB10842` amr_target=other amr_method=pcr_gene_presence (gt has_AST_data raw: 'MIC for 4195 kleb and ecoli')
- `PRJEB27256` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'PRJEB42350, PRJEB48268 and PRJEB27256, all include')
- `PRJNA768622` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB28400` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA271899` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJDB5929` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'Not provided at sample level')
- `PRJEB29742` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'cpe')
- `PRJNA1028672` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB48990` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA564424` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA855907` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: 'no')
- `PRJNA603790` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA415194` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA686897` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE plus NDM focus (ST147 outbreak suspected)')
- `PRJEB63361` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB35685` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB5065` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB50822` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB17615` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA557275` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA996149` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB15226` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB39867` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA549322` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA278886` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJNA789336` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA341927` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA544438` amr_target=nan amr_method=nan (gt has_AST_data raw: '')
- `PRJEB24970` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB36486` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA765801` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB58216` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB30134` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB58018` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24082` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB21277` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJDB12075` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA396774` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'yes, 3200 results')
- `PRJNA1048341` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA767944` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA395086` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'yes')
- `PRJEB39293` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA626430` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB22890` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA634885` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB12699` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA564992` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB64895` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'no')
- `PRJEB58136` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA804332` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA246471` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA885285` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA648389` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'yes')
- `PRJNA820335` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB74083` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24085` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB19229` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB42331` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'blaOxa48-like/CPE')
- `PRJEB20799` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA398288` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB24086` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24084` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24083` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA565795` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')

## Whole-project backfill proposals (whole-field)

- **country**: 91/109 accessions proposed a whole-project value.
- **isolation_source**: 25/109 accessions proposed a whole-project value.
- **host**: 92/109 accessions proposed a whole-project value.
- **collection_date**: 31/109 accessions proposed a whole-project value.

## Coverage & retrieval sanity

- paper_coverage_for_taxon: median 1.00, >0.9 in 63/93 with a value.
- needs_manual_download: 4/109 accessions.
- fulltext source mix: {'europepmc_fulltext': 61, 'local_pdf': 37, 'pdf': 7, 'none': 4}

# Stage 2A validation — grading vs trusted ground truth (train+val)

Graded rows in train+val: **109**.

Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no reliable ground truth and is **not scored** (spot-check only).

_Applied 13 David-verified amr_study GT corrections (gt_corrections.tsv)._

## amr_study  (accuracy 0.94 over n=85) — PRIMARY

```
predicted     amr  mixed  surveillance
ground_truth                          
amr            49      2             1
mixed           0      4             2
surveillance    0      0            27
```

## study_setting — PRIMARY

_Applied 6 David-verified study_setting GT corrections (gt_corrections.tsv)._

Accuracy 0.98 over n=94 (frozen sidecar).

```
predicted     community  hospital  mixed
ground_truth                            
community             7         0      0
hospital              0        79      1
mixed                 0         1      6
```

## Disagreements (verbatim; record, do not assume the sheet is right)


### amr_study (5 disagreements)

- `PRJEB39943` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Both resistant and comparator susceptible isolates were collected.'
- `PRJEB28400` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'All patients admitted to the ICUs at the national Hospital for tropical Diseases and Bach Mai Hospital during a 6-month study period will be screened for MDRO.'
- `PRJEB17615` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Establishment of genomic background – sequencing of retrospective susceptible and resistant isolates (to be undertaken at The Sanger Institute)'
- `PRJNA789565` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'The goal of this project was to identify the Klebsiella factors that predict infections in colonized patients. Deposited sequences are those of Klebsiella strains isolated from patient rectal swabs or'
- `PRJEB58136` grader=**surveillance** sheet=**mixed** (raw: 'Surveilance')
  - grader quote: 'we used comparative genome analysis to compare clinical isolates of K. pneumoniae from a tertiary-care teaching hospital with non-clinical isolates collected from livestock and wastewater samples from'

### study_setting (2 disagreements)

- `PRJNA604975` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'All isolates causing BSI between September 15, 2008, and December 01, 2018 (de-duplicated to one BSI isolate per 90-day period per patient), were processed by the clinical microbiology laboratory at t'
- `PRJEB30134` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'Clinical diagnostic samples and screening (rectal swab or stool) samples from hospital inpatients as well as samples referred from local General Practices (GPs), were collected from 1 November 2014 to'

## Spot-check (no clean ground truth — NOT scored)

### cohort_age (grader value vs free-text newborn_cohort)

- `PRJEB36683` grader=mixed (newborn_cohort raw: 'neonate, children, and adults; sample level age info availab')
- `PRJEB29740` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults; sample level age data are ava')
- `PRJNA604975` grader=adult (newborn_cohort raw: 'Age data partially available, mostly adults ~ 60 years')
- `PRJEB50614` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults; sample level age data are ava')
- `PRJNA845975` grader=newborn_young_child (newborn_cohort raw: 'Neonates, age info summarized in table S1, sample level age ')
- `PRJNA855907` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJEB46513` grader=newborn_young_child (newborn_cohort raw: 'neonatal meta-analysis')
- `PRJEB63361` grader=mixed (newborn_cohort raw: "Mix of adults and paeds but don't have age data")
- `PRJEB33565` grader=newborn_young_child (newborn_cohort raw: 'neonatal meta-analysis')
- `PRJEB17615` grader=mixed (newborn_cohort raw: 'Mixed by NICU enriched')
- `PRJEB39867` grader=adult (newborn_cohort raw: 'All age > 18 years, paeds excluded')
- `PRJNA549322` grader=adult (newborn_cohort raw: 'Adults, median age of 60+, age info summarized in table 1, s')
- `PRJEB22252` grader=newborn_young_child (newborn_cohort raw: 'Name suggests neonates')
- `PRJEB24970` grader=newborn_young_child (newborn_cohort raw: 'neonatal')
- `PRJEB58216` grader=adult (newborn_cohort raw: 'Adults, median age of 49, sample level age info available in')
- `PRJEB30134` grader=mixed (newborn_cohort raw: 'Contains some neonatal data, but mostly adults, with median ')
- `PRJEB58018` grader=adult (newborn_cohort raw: 'Adults, median age of 40+; age info summarized in table, sam')
- `PRJDB12075` grader=adult (newborn_cohort raw: 'Older adults, 90+ years old; age info summarized in table 5,')
- `PRJNA767944` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJEB39293` grader=mixed (newborn_cohort raw: 'Linked mother-newborn child - provided on indiv basis?')
- `PRJNA646358` grader=adult (newborn_cohort raw: 'Adults, median age of 40+; age info summarized in table 1, s')
- `PRJNA804332` grader=mixed (newborn_cohort raw: 'Neonates')
- `PRJNA1054115` grader=mixed (newborn_cohort raw: 'Children and adults, sample level age info not provided')
- `PRJNA1087366` grader=newborn_young_child (newborn_cohort raw: 'neonatal sepsis')
- `PRJNA885285` grader=mixed (newborn_cohort raw: 'Children, not neonates (2-14 years old), age info summarized')
- `PRJEB1800` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJNA978102` grader=mixed (newborn_cohort raw: 'included patients from 2 months to 96 years, median of 60+, ')
- `PRJEB74083` grader=adult (newborn_cohort raw: 'Adults, range 29-97 years old, summarized in text, sample le')
- `PRJEB20799` grader=newborn_young_child (newborn_cohort raw: 'part Pathogenwatch neonatal collection')
- `PRJNA641987` grader=mixed (newborn_cohort raw: 'neonatal BSI (62) and paediatric (n=32)')
- `PRJNA565795` grader=mixed (newborn_cohort raw: 'Adults, median age of 65 (IQR 47-...), age info summarized i')

### amr_target / amr_method where amr_study in {amr,mixed}

- `PRJEB39943` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB36683` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB37378` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: 'ESBLs')
- `PRJDB10842` amr_target=other amr_method=ast_result (gt has_AST_data raw: 'MIC for 4195 kleb and ecoli')
- `PRJNA768622` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA271899` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJDB5929` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'Not provided at sample level')
- `PRJEB29742` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'cpe')
- `PRJNA1028672` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB48990` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA564424` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA855907` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'no')
- `PRJNA415194` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJNA686897` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE plus NDM focus (ST147 outbreak suspected)')
- `PRJEB63361` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB35685` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB5065` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB50822` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB17615` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA557275` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA996149` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB15226` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB39867` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA549322` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA278886` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJNA789336` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA544438` amr_target=nan amr_method=nan (gt has_AST_data raw: '')
- `PRJEB24970` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB36486` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA765801` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB58216` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB30134` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB58018` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24082` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA787062` amr_target=other amr_method=nan (gt has_AST_data raw: '')
- `PRJDB12075` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA396774` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: 'yes, 3200 results')
- `PRJNA1048341` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA767944` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB39293` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA626430` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB22890` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA634885` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB12699` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA564992` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: '')
- `PRJEB64895` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'no')
- `PRJNA804332` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA246471` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA885285` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA648389` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'yes')
- `PRJNA820335` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB74083` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24085` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB19229` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB42331` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'blaOxa48-like/CPE')
- `PRJNA398288` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB24086` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24084` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24083` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB22264` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB19435` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24087` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA565795` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')

## Whole-project backfill proposals (method a)

- **country**: 84/109 accessions proposed a whole-project value.
- **isolation_source**: 18/109 accessions proposed a whole-project value.
- **host**: 85/109 accessions proposed a whole-project value.
- **collection_date**: 20/109 accessions proposed a whole-project value.

## Coverage & retrieval sanity

- paper_coverage_for_taxon: median 1.00, >0.9 in 40/61 with a value.
- needs_manual_download: 33/109 accessions.
- fulltext source mix: {'europepmc_fulltext': 61, 'none': 37, 'pdf': 7, 'abstract': 4}

# Stage 2A validation — grading vs trusted ground truth (train+val)

Graded rows in train+val: **109**.

Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no reliable ground truth and is **not scored** (spot-check only).

_Applied 13 David-verified amr_study GT corrections (gt_corrections.tsv)._

## amr_study  (accuracy 0.97 over n=78) — PRIMARY

```
predicted     amr  mixed  surveillance
ground_truth                          
amr            46      1             0
mixed           0      5             1
surveillance    0      0            25
```

## study_setting — PRIMARY

_Applied 6 David-verified study_setting GT corrections (gt_corrections.tsv)._

Accuracy 0.98 over n=88 (frozen sidecar).

```
predicted     community  hospital  mixed
ground_truth                            
community             6         0      0
hospital              0        75      0
mixed                 0         2      5
```

## Disagreements (verbatim; record, do not assume the sheet is right)


### amr_study (2 disagreements)

- `PRJEB39943` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Both resistant and comparator susceptible isolates were collected.'
- `PRJNA789565` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'The goal of this project was to identify the Klebsiella factors that predict infections in colonized patients. Deposited sequences are those of Klebsiella strains isolated from patient rectal swabs or'

### study_setting (2 disagreements)

- `PRJNA604975` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'We sequenced bacterial isolates from bloodstream infections that are routinely stored by the John Radcliffe Hospital Microbiology laboratory.'
- `PRJEB36486` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'patients with sepsis admitted to Queen Elizabeth Central Hospital, Blantyre, Malawi'

## Spot-check (no clean ground truth — NOT scored)

### cohort_age (grader value vs free-text newborn_cohort)

- `PRJEB36683` grader=mixed (newborn_cohort raw: 'neonate, children, and adults; sample level age info availab')
- `PRJEB42462` grader=newborn_young_child (newborn_cohort raw: 'Adults and neonates. Sample level age bracket in table 1')
- `PRJEB29740` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults; sample level age data are ava')
- `PRJNA604975` grader=adult (newborn_cohort raw: 'Age data partially available, mostly adults ~ 60 years')
- `PRJEB50614` grader=mixed (newborn_cohort raw: 'Neonate, children, and adults; sample level age data are ava')
- `PRJNA845975` grader=newborn_young_child (newborn_cohort raw: 'Neonates, age info summarized in table S1, sample level age ')
- `PRJEB46513` grader=newborn_young_child (newborn_cohort raw: 'neonatal meta-analysis')
- `PRJEB63361` grader=mixed (newborn_cohort raw: "Mix of adults and paeds but don't have age data")
- `PRJEB39867` grader=adult (newborn_cohort raw: 'All age > 18 years, paeds excluded')
- `PRJNA549322` grader=adult (newborn_cohort raw: 'Adults, median age of 60+, age info summarized in table 1, s')
- `PRJEB24970` grader=newborn_young_child (newborn_cohort raw: 'neonatal')
- `PRJEB58216` grader=adult (newborn_cohort raw: 'Adults, median age of 49, sample level age info available in')
- `PRJEB30134` grader=mixed (newborn_cohort raw: 'Contains some neonatal data, but mostly adults, with median ')
- `PRJDB12075` grader=adult (newborn_cohort raw: 'Older adults, 90+ years old; age info summarized in table 5,')
- `PRJEB39293` grader=mixed (newborn_cohort raw: 'Linked mother-newborn child - provided on indiv basis?')
- `PRJNA646358` grader=adult (newborn_cohort raw: 'Adults, median age of 40+; age info summarized in table 1, s')
- `PRJNA804332` grader=mixed (newborn_cohort raw: 'Neonates')
- `PRJNA1054115` grader=mixed (newborn_cohort raw: 'Children and adults, sample level age info not provided')
- `PRJNA1087366` grader=newborn_young_child (newborn_cohort raw: 'neonatal sepsis')
- `PRJNA885285` grader=mixed (newborn_cohort raw: 'Children, not neonates (2-14 years old), age info summarized')
- `PRJEB1800` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJEB74083` grader=adult (newborn_cohort raw: 'Adults, range 29-97 years old, summarized in text, sample le')
- `PRJEB20799` grader=newborn_young_child (newborn_cohort raw: 'part Pathogenwatch neonatal collection')
- `PRJNA641987` grader=mixed (newborn_cohort raw: 'neonatal BSI (62) and paediatric (n=32)')

### amr_target / amr_method where amr_study in {amr,mixed}

- `PRJEB39943` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB36683` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB37378` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: 'ESBLs')
- `PRJDB10842` amr_target=nan amr_method=ast_result (gt has_AST_data raw: 'MIC for 4195 kleb and ecoli')
- `PRJNA768622` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB28400` amr_target=other amr_method=nan (gt has_AST_data raw: '')
- `PRJNA271899` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJDB5929` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'Not provided at sample level')
- `PRJEB29742` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'cpe')
- `PRJNA1028672` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB48990` amr_target=nan amr_method=nan (gt has_AST_data raw: '')
- `PRJNA564424` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA855907` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: 'no')
- `PRJNA415194` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB63361` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB35685` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB5065` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB50822` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJNA557275` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA996149` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB15226` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: '')
- `PRJEB39867` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA549322` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA789336` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA544438` amr_target=nan amr_method=nan (gt has_AST_data raw: '')
- `PRJEB24970` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB36486` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA765801` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB58216` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB58018` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24082` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJDB12075` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA396774` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: 'yes, 3200 results')
- `PRJNA1048341` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA767944` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB39293` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA626430` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB22890` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA634885` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA564992` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: '')
- `PRJEB64895` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'no')
- `PRJEB58136` amr_target=nan amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA804332` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA246471` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA885285` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA648389` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'yes')
- `PRJNA820335` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB74083` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24085` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB19229` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB42331` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'blaOxa48-like/CPE')
- `PRJNA398288` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB24086` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB24084` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB24083` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB22264` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB19435` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJEB24087` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJNA565795` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')

## Whole-project backfill proposals (method a)

- **country**: 81/109 accessions proposed a whole-project value.
- **isolation_source**: 17/109 accessions proposed a whole-project value.
- **host**: 78/109 accessions proposed a whole-project value.
- **collection_date**: 18/109 accessions proposed a whole-project value.

## Coverage & retrieval sanity

- paper_coverage_for_taxon: median 1.00, >0.9 in 43/63 with a value.
- needs_manual_download: 27/109 accessions.
- fulltext source mix: {'europepmc_fulltext': 61, 'none': 37, 'pdf': 7, 'abstract': 4}

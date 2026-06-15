# Stage 2A validation — grading vs trusted ground truth (train+val)

Graded rows in train+val: **109**.

Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no reliable ground truth and is **not scored** (spot-check only).

## amr_study  (accuracy 0.78 over n=86) — PRIMARY

```
predicted     amr  mixed  surveillance
ground_truth                          
amr            44      4             7
mixed           0      1             3
surveillance    3      2            22
```

## study_setting — PRIMARY

Accuracy 0.90 over n=94 (frozen sidecar).

```
predicted     community  hospital  mixed
ground_truth                            
community             3         1      0
hospital              1        78      2
mixed                 2         3      4
```

## Disagreements (verbatim; record, do not assume the sheet is right)


### amr_study (19 disagreements)

- `PRJEB39943` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Both resistant and comparator susceptible isolates were collected.'
- `PRJEB29740` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'The aim of this project is primarily to fund research around intelligent surveillance for important emerging bacterial pathogens and monitoring the spread of antimicrobial resistance in low- and middl'
- `PRJEB28400` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'All patients admitted to the ICUs at the national Hospital for tropical Diseases and Bach Mai Hospital during a 6-month study period will be screened for MDRO.'
- `PRJNA271899` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'For each resistant isolate, we also collected date- and species-matched meropenem-susceptible isolates. UCI submitted two carbapenem-susceptible isolates per resistant isolate; the other three hospita'
- `PRJEB50614` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'The bacterial isolates used for this study comprised 1072 putative K. pneumoniae isolates primarily sourced from hospital infections and obtained from the years 2014 to 2022 across India. This include'
- `PRJNA325243` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Laboratories were instructed to select only one isolate per client submission.'
- `PRJNA603790` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Study of Klebsiella pneumoniae transmission in a long-term acute care hospital'
- `PRJEB5065` grader=**amr** sheet=**surveillance** (raw: 'surveillance')
  - grader quote: 'Isolates were collected if they were resistant to at least one antibiotic in three of the following classes: penicillins, carbapenems, cephalosporins, tetracyclines, aminoglycosides, and fluoroquinolo'
- `PRJEB17615` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: '1)Establishment of genomic background – sequencing of retrospective susceptible and resistant isolates (to be undertaken at The Sanger Institute). 2)Prospective sequencing (within ARSRL) – isolates wi'
- `PRJNA557275` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Whole-genome sequencing was performed on 388 isolates, including 164 PR isolates.'
- `PRJNA789565` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'Deposited sequences are those of Klebsiella strains isolated from patient rectal swabs or clinical cultures.'
- `PRJNA857686` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Fastq files for HAI bacteria sequenced at the Nevada State Public Health Lab'
- `PRJEB30134` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'This project will explore the epidemiology of invasive infections within a typical large teaching hospital. To this end we will whole genome sequence representative bacteria as they are isolated in th'
- `PRJEB58018` grader=**amr** sheet=**surveillance** (raw: 'Surveillance')
  - grader quote: 'Between January and September 2022, the NRC received 330 non-duplicate NDM-1- and NDM-1/OXA-48-producing K. pneumoniae isolates. Of these, 200 isolates, comprising 66 NDM-1/OXA-48-producing and 134 ND'
- `PRJNA787062` grader=**amr** sheet=**surveillance** (raw: 'surveillance')
  - grader quote: 'the study aimed to determine the genomic epidemiology of ESBL, AmpC and carbapenemase producing and colistin resistance Enterobacteriaceae and characterise these strains at genomic level'
- `PRJNA396774` grader=**mixed** sheet=**surveillance** (raw: 'Surveillance')
  - grader quote: 'A project consisting of both ESBL and Non-ESBL Klebsiella pneumoniae strains.'
- `PRJEB58136` grader=**mixed** sheet=**surveillance** (raw: 'Surveilance')
  - grader quote: 'The selection of isolates for sequencing based on antimicrobial susceptibility profile may introduce bias. ... Klebsiella spp. isolated from livestock were highly susceptible to the tested antimicrobi'
- `PRJNA1087366` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: "For all analyses, the patient's first clinical isolate from blood or CSF was selected. In case of mixed infection, isolates belonging to different species were also included. To avoid analyzing replic"
- `PRJEB1800` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'We selected a random subset of 90 K. pneumoniae (using a random integer generator) from a collection of 135 K. pneumoniae that were isolated and stored in Patan Hospital between May and December 2012.'

### study_setting (9 disagreements)

- `PRJNA604975` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'The majority of Klebsiella spp. BSIs were HA-BSI (510/882 [missing data for 4 isolates], 59%). ... Klebsiella spp. CA-BSI cases were older (median age 76 years (IQR 65–85) vs 66 years (49–75) for HA-B'
- `PRJNA325243` grader=**hospital** sheet=**community** (raw: 'community')
  - grader quote: "from various animal hosts that presented to veterinary hospitals in the U.S. ... Isolates were collected from 26 states by a network of 30 Vet-LIRN veterinary diagnostic laboratories ('Source laborato"
- `PRJNA564424` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: '8 (1%) isolates from English outpatient/primary care settings (7 from the North West region, 1 from a southern UK location)...327 archived isolates (54%) from inpatients in the early stages of the obs'
- `PRJEB29143` grader=**community** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'Diversity and characteristics of Klebsiella pneumoniae strains from healthy carriers'
- `PRJEB35685` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'national laboratory surveillance'
- `PRJEB36486` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'patients with sepsis admitted to Queen Elizabeth Central Hospital, Blantyre, Malawi'
- `PRJDB12075` grader=**community** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'We also isolated 20 carbapenem-resistant GN-ARB from the oral cavity of 18 residents and 70 isolates from the rectum of 61 residents... residents of long-term-care facilities (LTCF)'
- `PRJNA1048341` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'The selected isolates came from 18 hospitals located in the eight provinces of Andalusia.'
- `PRJNA885285` grader=**community** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'Faecal samples were collected from community participants of Siem Reap, Cambodia in a cross-sectional study from August to November 2019. The study included two arms: a hospital-associated household ('

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
- `PRJEB21605` grader=mixed (newborn_cohort raw: 'patient age not provided')
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
- `PRJNA565795` grader=adult (newborn_cohort raw: 'Adults, median age of 65 (IQR 47-...), age info summarized i')

### amr_target / amr_method where amr_study in {amr,mixed}

- `PRJEB39943` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
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
- `PRJNA855907` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'no')
- `PRJNA415194` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA686897` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE plus NDM focus (ST147 outbreak suspected)')
- `PRJEB63361` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB35685` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
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
- `PRJEB58018` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24082` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA787062` amr_target=other amr_method=nan (gt has_AST_data raw: '')
- `PRJDB12075` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA396774` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: 'yes, 3200 results')
- `PRJNA1048341` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA767944` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB39293` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA626430` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB22890` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA634885` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB12699` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA564992` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB64895` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'no')
- `PRJEB58136` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA804332` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA246471` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA885285` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA648389` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'yes')
- `PRJNA820335` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB74083` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24085` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB19229` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB42331` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'blaOxa48-like/CPE')
- `PRJNA398288` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB24086` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24084` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB24083` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB19435` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJEB24087` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA565795` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')

## Whole-project backfill proposals (method a)

- **country**: 84/109 accessions proposed a whole-project value.
- **isolation_source**: 19/109 accessions proposed a whole-project value.
- **host**: 87/109 accessions proposed a whole-project value.
- **collection_date**: 21/109 accessions proposed a whole-project value.

## Coverage & retrieval sanity

- paper_coverage_for_taxon: median 1.00, >0.9 in 38/57 with a value.
- needs_manual_download: 38/109 accessions.
- fulltext source mix: {'europepmc_fulltext': 61, 'none': 37, 'pdf': 7, 'abstract': 4}

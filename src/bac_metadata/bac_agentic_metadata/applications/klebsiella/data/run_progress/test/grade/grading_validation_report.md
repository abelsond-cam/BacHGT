# study grading validation — grading vs trusted ground truth (test)

Graded rows in test: **47**.

Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no reliable ground truth and is **not scored** (spot-check only).

## amr_study  (accuracy 0.82 over n=39) — PRIMARY

```
predicted     amr  mixed  surveillance
ground_truth                          
amr            19      2             1
mixed           1      3             1
surveillance    1      1            10
```

## study_setting — PRIMARY

Accuracy 0.90 over n=42 (frozen sidecar).

```
predicted     community  hospital  mixed
ground_truth                            
community             8         0      1
hospital              1        26      2
mixed                 0         0      4
```

## Disagreements (verbatim; record, do not assume the sheet is right)


### amr_study (7 disagreements)

- `PRJEB10018` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'hospital laboratories were asked to submit the first ten consecutive carbapenem-non-susceptible clinical isolates of either K. pneumoniae or E. coli, together with one carbapenem-susceptible same-spec'
- `PRJNA529744` grader=**amr** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'Suspected CPE were defined as elevated meropenem MIC (≥0.5 mg/liter), reduced disc diffusion zones (meropenem, ≤24 mm [EUCAST/CLSI]), and/or positive phenotypic tests for carbapenemase detection (e.g.'
- `PRJEB2111` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'A total of 288 bacteria isolates, sampled to maximize diversity, were contributed from coauthors in six countries'
- `PRJNA543274` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'a computationally more manageable subset of these genomes (n = 999) was used for comparative genomic analyses, selected to represent the largest genomic diversity between and within species, and geogr'
- `PRJEB38540` grader=**mixed** sheet=**surveillance** (raw: 'surveillance')
  - grader quote: 'Most of them were isolated from SCAI agar (85%, n=215/253), enabling growth of all KP variants and generating an unbiased strain collection. Since we used four different media on all samples... antibi'
- `PRJNA825705` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Of these, 49 isolates were carbapenem-susceptible and 132 were carbapenem-resistant.'
- `PRJNA684006` grader=**amr** sheet=**surveillance** (raw: 'surveillance')
  - grader quote: 'Based on the presence of pLVPK-associated markers (rmpA, rmpA2, iroN, iucA, and iutA), 2 NDM-1-producing CR-hvKPs, EN5180 (ST15-K54) and EN5289 (ST11-K2) strains were selected for WGS analysis.'

### study_setting (4 disagreements)

- `PRJEB48268` grader=**community** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'Human faecal carriage isolates (n = 484) were collected from a general adult population in the Tromsø municipality in Norway during 2015–2016. From marine environments, KpSC isolates (n = 99) were rec'
- `PRJNA778230` grader=**mixed** sheet=**community** (raw: 'community')
  - grader quote: 'Of the 222 (79.6%) isolates associated with nosocomial infections, most of them were collected from patients hospitalized in medical wards (n = 110; 49.6%), intensive care units (n = 82; 36.9%), and e'
- `PRJEB56146` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'Most CPE isolates (285/389; 73%) were from patients admitted to hospital, whereas 23% (89/389) were obtained from outpatient settings, and 1% (2/389) from long-term care facilities.'
- `PRJEB37711` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'Urinary tract infections had the highest prevalence, likely because community samples were also included in this study... results had been reported by the responsible clinical microbiologist to the as'

## Spot-check (no clean ground truth — NOT scored)

### cohort_age (grader value vs free-text newborn_cohort)

- `PRJNA288601` grader=adult (newborn_cohort raw: 'Adults, median age of 60+, age info summarized in table 1, s')
- `PRJNA658369` grader=mixed (newborn_cohort raw: 'Adults aged 50-75, age info summarized in table 1, sample le')
- `PRJEB29738` grader=mixed (newborn_cohort raw: '145 out of 259 isolates are Newborns; 123 are neonates, 22 a')
- `PRJNA577535` grader=adult (newborn_cohort raw: 'patient age not provided')
- `PRJEB29424` grader=adult (newborn_cohort raw: 'patient age not provided')
- `PRJEB63349` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJEB42350` grader=adult (newborn_cohort raw: 'Adults only, 40+; age info summarized  in table S1, sample l')
- `PRJNA529744` grader=adult (newborn_cohort raw: 'Mostly adults, median age of 68 years')
- `PRJNA757551` grader=adult (newborn_cohort raw: 'Mostly adults, median age of 68 years')
- `PRJEB37504` grader=adult (newborn_cohort raw: 'Adults only, median age of 70+; sample level age info availa')
- `PRJEB56146` grader=mixed (newborn_cohort raw: 'neonates, children and adults, median age of 70+; age info s')
- `PRJNA548120` grader=newborn_young_child (newborn_cohort raw: 'Part Pathogenwatch neonatal collection')
- `PRJNA684006` grader=newborn_young_child (newborn_cohort raw: 'neonatal, sample level age info not provided')

### amr_target / amr_method where amr_study in {amr,mixed}

- `PRJNA288601` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB10018` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'Meropenem AST on 1700')
- `PRJNA376414` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA658369` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB29738` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA577535` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB29424` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB63349` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA529744` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'CPE but just 50% phenotypic susceptibility')
- `PRJNA757551` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE suspected')
- `PRJEB53835` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB37504` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA1133668` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB38540` amr_target=other amr_method=ast_result (gt has_AST_data raw: 'no')
- `PRJEB32655` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB1271` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA339843` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA532291` amr_target=carbapenem amr_method=nan (gt has_AST_data raw: '')
- `PRJNA433394` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB19226` amr_target=nan amr_method=nan (gt has_AST_data raw: '')
- `PRJNA633565` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA252957` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA547865` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE')
- `PRJEB56146` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA825705` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'not per sequence')
- `PRJEB1272` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'blaOXA-48')
- `PRJNA839691` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB1963` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'ESBLs (matched susceptible: 40S, 29 R)')
- `PRJNA548120` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA684006` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA514908` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')

## Whole-project backfill proposals (whole-field)

- **country**: 38/47 accessions proposed a whole-project value.
- **isolation_source**: 7/47 accessions proposed a whole-project value.
- **host**: 33/47 accessions proposed a whole-project value.
- **collection_date**: 13/47 accessions proposed a whole-project value.

## Coverage & retrieval sanity

- paper_coverage_for_taxon: median 1.00, >0.9 in 26/41 with a value.
- needs_manual_download: 3/47 accessions.
- fulltext source mix: {'europepmc_fulltext': 22, 'local_pdf': 17, 'none': 4, 'pdf': 4}

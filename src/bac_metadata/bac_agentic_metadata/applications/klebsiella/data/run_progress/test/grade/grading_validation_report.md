# study grading validation — grading vs trusted ground truth (test)

Graded rows in test: **47**.

Primary accuracy checks: **amr_study** and **study_setting**. `cohort_age` has no reliable ground truth and is **not scored** (spot-check only).

## amr_study  (accuracy 0.84 over n=37) — PRIMARY

```
predicted     amr  mixed  surveillance
ground_truth                          
amr            18      2             1
mixed           1      2             1
surveillance    1      0            11
```

## study_setting — PRIMARY

Accuracy 0.90 over n=42 (frozen sidecar).

```
predicted     community  hospital  mixed
ground_truth                            
community             8         0      1
hospital              0        27      2
mixed                 0         1      3
```

## Disagreements (verbatim; record, do not assume the sheet is right)


### amr_study (6 disagreements)

- `PRJEB10018` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'hospital laboratories were asked to submit the first ten consecutive carbapenem-non-susceptible clinical isolates of either K. pneumoniae or E. coli, together with one carbapenem-susceptible same-spec'
- `PRJNA529744` grader=**amr** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'Suspected CPE were defined as elevated meropenem MIC (≥0.5 mg/liter), reduced disc diffusion zones (meropenem, ≤24 mm [EUCAST/CLSI]), and/or positive phenotypic tests for carbapenemase detection (e.g.'
- `PRJEB2111` grader=**surveillance** sheet=**mixed** (raw: 'AMR plus control')
  - grader quote: 'A total of 288 bacteria isolates, sampled to maximize diversity, were contributed from coauthors in six countries ... collected from a range of human and animal sources, including infection, colonizat'
- `PRJNA543274` grader=**surveillance** sheet=**amr** (raw: 'AMR')
  - grader quote: 'In total, 261 Klebsiella spp. isolates were collected from various tissue sources (see Additional file 2: Table S1 for more details) at three routine diagnostic laboratories in Switzerland... we analy'
- `PRJNA825705` grader=**mixed** sheet=**amr** (raw: 'AMR')
  - grader quote: 'Of these, 49 isolates were carbapenem-susceptible and 132 were carbapenem-resistant.'
- `PRJNA684006` grader=**amr** sheet=**surveillance** (raw: 'surveillance')
  - grader quote: 'Based on the presence of pLVPK-associated markers (rmpA, rmpA2, iroN, iucA, and iutA), 2 NDM-1-producing CR-hvKPs, EN5180 (ST15-K54) and EN5289 (ST11-K2) strains were selected for WGS analysis.'

### study_setting (4 disagreements)

- `PRJNA778230` grader=**mixed** sheet=**community** (raw: 'community')
  - grader quote: 'Of the 222 (79.6%) isolates associated with nosocomial infections, most of them were collected from patients hospitalized in medical wards... Six were associated with community liver abscess (10.5% of'
- `PRJNA543274` grader=**hospital** sheet=**mixed** (raw: 'mixed')
  - grader quote: 'at three routine diagnostic laboratories in Switzerland including the University Hospital of Basel (USB; Basel, Switzerland), Mabritec AG (Riehen, Switzerland) and Labor Team W AG (LTW; Goldach, Switz'
- `PRJEB56146` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'Most CPE isolates (285/389; 73%) were from patients admitted to hospital, whereas 23% (89/389) were obtained from outpatient settings, and 1% (2/389) from long-term care facilities.'
- `PRJEB37711` grader=**mixed** sheet=**hospital** (raw: 'hospital')
  - grader quote: 'had been reported by the responsible clinical microbiologist to the associated hospital or requesting general practitioners'

## Spot-check (no clean ground truth — NOT scored)

### cohort_age (grader value vs free-text newborn_cohort)

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
- `PRJEB37711` grader=mixed (newborn_cohort raw: 'patient age not provided')
- `PRJNA548120` grader=newborn_young_child (newborn_cohort raw: 'Part Pathogenwatch neonatal collection')
- `PRJNA684006` grader=newborn_young_child (newborn_cohort raw: 'neonatal, sample level age info not provided')

### amr_target / amr_method where amr_study in {amr,mixed}

- `PRJEB10018` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'Meropenem AST on 1700')
- `PRJNA376414` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA658369` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB29738` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA577535` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB29424` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB63349` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA529744` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'CPE but just 50% phenotypic susceptibility')
- `PRJNA757551` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE suspected')
- `PRJEB53835` amr_target=third_gen_cephalosporin amr_method=nan (gt has_AST_data raw: '')
- `PRJEB37504` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA1133668` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB32655` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB1271` amr_target=other amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA339843` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA532291` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA433394` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA633565` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJNA252957` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA547865` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'CPE')
- `PRJEB56146` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA825705` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: 'not per sequence')
- `PRJEB1272` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: 'blaOXA-48')
- `PRJNA839691` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')
- `PRJEB1963` amr_target=third_gen_cephalosporin amr_method=ast_result (gt has_AST_data raw: 'ESBLs (matched susceptible: 40S, 29 R)')
- `PRJNA548120` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA684006` amr_target=carbapenem amr_method=pcr_gene_presence (gt has_AST_data raw: '')
- `PRJNA514908` amr_target=carbapenem amr_method=ast_result (gt has_AST_data raw: '')

## Whole-project backfill proposals (whole-field)

- **country**: 37/47 accessions proposed a whole-project value.
- **isolation_source**: 9/47 accessions proposed a whole-project value.
- **host**: 40/47 accessions proposed a whole-project value.
- **collection_date**: 13/47 accessions proposed a whole-project value.

## Coverage & retrieval sanity

- paper_coverage_for_taxon: median 1.00, >0.9 in 24/38 with a value.
- needs_manual_download: 1/47 accessions.
- fulltext source mix: {'europepmc_fulltext': 22, 'local_pdf': 17, 'none': 4, 'pdf': 4}

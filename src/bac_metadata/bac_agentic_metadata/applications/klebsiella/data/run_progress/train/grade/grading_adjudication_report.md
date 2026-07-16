# study grading adjudication — critique of grader-vs-sheet disagreements

Adjudicated **8** disagreements. Verdicts: {'sheet_correct': 2, 'model_correct': 5, 'undetermined': 1}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB39943` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All of the included 310 isolates were in the category R or I for at least one carbapenem as per inclusion criteria.'
- reasoning: Every isolate sequenced/included in this study met a non-susceptible carbapenem AST result (R or I); the susceptible comparator isolates were part of the parent EuSCAPE/CCRE survey design but were not included here, so per the rubric the deposited set is amr, not mixed.

## `PRJEB27256` — amr_study

- grader: **mixed**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'For comparison, a subset of non-ESBL blood culture isolates (n=667) were included.'
- reasoning: The deposited set combines AMR-selected putative ESBL producers with a deliberately added comparison group of non-ESBL isolates, which is the two-category contrast design the rubric classifies as mixed, not an all-isolates surveillance frame.

## `PRJEB17615` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'From 2295 ESBL-positive, and/or cephalosporin resistant, and/or carbapenem-resistant Klebsiella isolates referred to the Antimicrobial Resistance Surveillance Resistance Reference Laboratory in 2015–2017, 263 (11.5%) were selected for WGS'
- reasoning: Every sequenced isolate had to be ESBL-producing, cephalosporin-resistant, or carbapenem-resistant to be selected — a resistance gate on each isolate — and the paper describes no deliberately-added susceptible controls, so it is amr, not mixed; the grader's 'susceptible and resistant isolates' quote does not appear anywhere in the paper text.

## `PRJNA789565` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): '44 of 85 (51.8%) of the clinical isolates from cases were pan-sensitive apart from intrinsic ampicillin resistance'
- reasoning: The deposited set is 'clinical isolates from cases' with a majority pan-sensitive, so isolates were not gated on a resistant phenotype/genotype — all case clinical isolates were sequenced regardless of resistance, which is the surveillance sampling rule; nothing indicates a deliberately-added susceptible control arm that would make it 'mixed'.
- ⚠️ rule_gap: Rubric could clarify how to classify a case-based clinical-isolate collection where 'cases' are defined by infection/epidemiology rather than resistance: absent an explicit matched-susceptible-control arm, such a set is surveillance, not mixed.

## `PRJNA787062` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'surveillance')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Enterobacteriaceae isolates (n = 301) were subjected to whole-genome sequencing using Illumina HiSeq 2500. ... Among 301 Enterobacteriaceae, 22 Klebsiella pneumoniae, 2 Klebsiella variicola, and 3 Enterobacter cloacae isolates showed reduced susceptibility to meropenem (7% of tested isolates).'
- reasoning: All 301 isolates were sequenced and resistance (only ~7% meropenem-reduced) was characterised afterwards, so entry into the deposited set was not gated on an AMR phenotype/genotype — that is surveillance, not amr.

## `PRJNA395086` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text was provided, so I cannot independently verify the grader's cited exclusion rule or the sheet's classification against the source; the decision cannot be made from the material supplied.

## `PRJNA686897` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): '20 medical intensive care units (ICUs) in 20 short-term acute care hospitals, 7 LTACHs, and 8 vSNFs in the Chicago region were invited to participate'
- reasoning: The study deliberately samples both hospital settings (ICUs in acute-care hospitals, LTACHs) and genuine non-hospital long-term/skilled-nursing facilities (vSNFs), which the rubric classifies as community — a deliberate second-setting arm makes this mixed.
- ⚠️ rule_gap: Clarify how ventilator-capable skilled nursing facilities (vSNFs) and LTACHs map: skilled nursing facilities are long-term-care (community) while LTACHs are hospital, so a study spanning ICUs + LTACHs + vSNFs is mixed — worth stating explicitly.

## `PRJEB21277` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'samples were from hospitals in the following counties: Dublin (n=18), Kerry (n=2), Galway (n=2)'
- reasoning: The only available evidence describes rectal-swab/faeces surveillance of people admitted to healthcare facilities, with samples drawn from named hospitals — human inpatient care with no deliberate community/outpatient arm, which is 'hospital' per the rubric.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJNA789565`) Rubric could clarify how to classify a case-based clinical-isolate collection where 'cases' are defined by infection/epidemiology rather than resistance: absent an explicit matched-susceptible-control arm, such a set is surveillance, not mixed.
- [study_setting] (`PRJNA686897`) Clarify how ventilator-capable skilled nursing facilities (vSNFs) and LTACHs map: skilled nursing facilities are long-term-care (community) while LTACHs are hospital, so a study spanning ICUs + LTACHs + vSNFs is mixed — worth stating explicitly.

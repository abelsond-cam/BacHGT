# study grading adjudication — critique of grader-vs-sheet disagreements

Adjudicated **8** disagreements. Verdicts: {'sheet_correct': 1, 'model_correct': 6, 'undetermined': 1}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB39943` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All of the included 310 isolates were in the category R or I for at least one carbapenem as per inclusion criteria.'
- reasoning: Every isolate sequenced/included in this study met a non-susceptible carbapenem AST result (R or I); the susceptible comparator isolates were part of the parent EuSCAPE/CCRE survey design but were not included here, so per the rubric the deposited set is amr, not mixed.

## `PRJEB27256` — amr_study

- grader: **mixed**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All putative ESBL-producing KpSC blood (n=149) and urine isolates (n=91) ... were included in the study. For comparison, a subset of non-ESBL blood culture isolates (n=815) were included.'
- reasoning: The deposited set deliberately combines AMR-selected ESBL-producing isolates with a non-ESBL comparison subset, a two-category contrast design that the rubric explicitly classifies as mixed (ESBL + non-ESBL), not surveillance.

## `PRJEB17615` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: The supplied paper deposits its data under PRJEB29738 ('deposited in the European Nucleotide Archive under the project accession PRJEB29738') and describes an exclusively resistance-selected set (all 2295→263 isolates were ESBL-positive, cephalosporin-resistant, and/or carbapenem-resistant), whereas the disputed accession is PRJEB17615; the paper therefore does not describe the contents deposited under PRJEB17615, and the grader's 'susceptible and resistant isolates' quote is not present in the paper text, so neither value can be verified from the paper alone.
- ⚠️ rule_gap: Clarify how to adjudicate when the accessible paper's stated deposit accession differs from the accession being graded: specify whether such a paper may be used at all, and whether a project-level study description (e.g. PRJEB17615's 'retrospective susceptible and resistant isolates') should govern when the only available paper covers a resistant-only subset under a different accession.

## `PRJNA789565` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'patient rectal swabs were screened for the presence of Klebsiella. If a patient was colonized with Klebsiella, up to three rectal isolates were banked, and the patient was enrolled in the study.'
- reasoning: The sampling rule recovers all Klebsiella carriers regardless of resistance phenotype/genotype, with no per-isolate AMR gate and no deliberately-added susceptible controls — this is infection-control screening that defines a surveillance frame, not a mixed AMR-plus-control design.

## `PRJNA787062` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'surveillance')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All Enterobacteriaceae isolates (n = 301) were subjected to WGS regardless of their meropenem susceptibility status'
- reasoning: The sampling rule sequenced all isolates of the taxon irrespective of any resistance phenotype, which is the surveillance pattern; no per-isolate AMR gate governed entry, so the rubric's 'amr' criterion is not met. The sheet's own raw text reads 'surveillance', so the normalised 'amr' appears to be a mapping error.

## `PRJNA395086` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'identified as being resistant to at least one carbapenem by the clinical microbiology laboratory (Vitek2)'
- reasoning: Every deposited isolate had to be carbapenem-resistant to be selected — a non-susceptible AST result acting as a per-isolate AMR gate — which the rubric defines as amr, not surveillance.

## `PRJNA686897` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): '20 medical intensive care units (ICUs) in 20 short-term acute care hospitals, 7 LTACHs, and 8 vSNFs in the Chicago region were invited to participate'
- reasoning: The study deliberately samples both hospital ICUs (inpatient acute care) and long-term/skilled-nursing facilities (LTACHs and ventilator-capable skilled nursing facilities, vSNFs), which the rubric classifies as community — a genuine second-setting arm makes this mixed.
- ⚠️ rule_gap: Clarify that LTACHs ('long-term acute care hospitals') count as community/long-term-care rather than hospital despite 'hospital' in the name, so an LTACH+SNF+ICU survey is unambiguously mixed.

## `PRJEB21277` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'We sequenced the samples collected from 33 hospitals in Ireland during this period.'
- reasoning: All isolates came from surveillance rectal-swab/faeces screening of people admitted to hospitals/healthcare facilities, which the rubric classifies as hospital-based carriage screening; there is no evidence of a deliberate community/outpatient sampling arm to support 'mixed'.
- ⚠️ rule_gap: Clarify whether 'healthcare facilities' wording that may include long-term-care alongside acute hospitals should be read as hospital (inpatient screening) or trigger 'mixed'; here the explicit '33 hospitals' resolves it to hospital.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJEB17615`) Clarify how to adjudicate when the accessible paper's stated deposit accession differs from the accession being graded: specify whether such a paper may be used at all, and whether a project-level study description (e.g. PRJEB17615's 'retrospective susceptible and resistant isolates') should govern when the only available paper covers a resistant-only subset under a different accession.
- [study_setting] (`PRJNA686897`) Clarify that LTACHs ('long-term acute care hospitals') count as community/long-term-care rather than hospital despite 'hospital' in the name, so an LTACH+SNF+ICU survey is unambiguously mixed.
- [study_setting] (`PRJEB21277`) Clarify whether 'healthcare facilities' wording that may include long-term-care alongside acute hospitals should be read as hospital (inpatient screening) or trigger 'mixed'; here the explicit '33 hospitals' resolves it to hospital.

# study grading adjudication — critique of grader-vs-sheet disagreements

Adjudicated **10** disagreements. Verdicts: {'sheet_correct': 1, 'model_correct': 7, 'undetermined': 2}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB39943` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All of the included 310 isolates were in the category R or I for at least one carbapenem as per inclusion criteria.'
- reasoning: Every isolate actually sequenced/deposited in this study had to be carbapenem-resistant (R) or 'susceptible, increased exposure' (I) — a non-susceptible AST gate — which is amr; the grader's 'comparator susceptible isolates' belong to the parent EuSCAPE/CCRE collection design and were not sequenced here, so per the rubric they do not make it mixed.

## `PRJEB27256` — amr_study

- grader: **mixed**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'For comparison, a subset of non-ESBL blood culture isolates (n=815) were included.'
- reasoning: The deposited set combines AMR-selected isolates (all ESBL-producing KpSC) with deliberately-added non-ESBL comparison isolates — exactly the two-category ESBL + non-ESBL contrast design the rubric classifies as mixed, not a single non-AMR sampling frame (surveillance).
- ⚠️ rule_gap: Could clarify that drawing isolates from a national surveillance database (e.g. NORM) does not by itself make the deposit 'surveillance' when the deposited selection adds an AMR-defined contrast group; the deposit's own composition governs.

## `PRJEB17615` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'sequencing of retrospective susceptible and resistant isolates (to be undertaken at The Sanger Institute)'
- reasoning: The supplied paper deposits to a DIFFERENT accession ("deposited in the European Nucleotide Archive under the project accession PRJEB29738"), so it does not govern PRJEB17615; the only evidence specific to the disputed accession is its EBI study description (a rubric-permitted grading basis), which states the deposit comprises both susceptible AND resistant isolates — the rubric's definition of mixed.
- ⚠️ rule_gap: The paper text attached here describes PRJEB29738 (an all-resistant, amr-selective deposit), not the disputed PRJEB17615. The rubric should specify that when the attached paper's stated deposit accession differs from the accession under review, the paper cannot be used to grade it and adjudication must fall back to the EBI study title/description for the actual accession (here "susceptible and resistant isolates" => mixed).

## `PRJNA789565` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text was provided and the EBI metadata is not available here, so the per-isolate sampling rule that governed which isolates were sequenced under this accession cannot be established; the grader's snippet about pan-sensitive cases is unverifiable against any source I can read and cannot, on its own, distinguish an all-clinical-isolates surveillance frame from a deliberate case-plus-control mixed design.
- ⚠️ rule_gap: When a case-control framing is implied ('clinical isolates from cases' plus controls), clarify whether deliberately added non-AMR controls make the deposit 'mixed' versus an all-cases-sequenced 'surveillance' frame, and specify how to adjudicate when no paper text is accessible (default to not_gradeable/undetermined).

## `PRJNA787062` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'surveillance')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All Enterobacteriaceae isolates (n = 301) were subjected to WGS regardless of their meropenem susceptibility status'
- reasoning: The sampling rule sequenced every isolate "regardless of their meropenem susceptibility status," so no per-isolate AMR phenotype/genotype gate governed entry — this is the surveillance case, not amr.

## `PRJNA395086` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Eight of these isolates were excluded because Etest results did not confirm resistance to any of the carbapenems; thus, 166 CR-Kp isolates were included in the final analyses.'
- reasoning: Every sequenced isolate had to be confirmed carbapenem-resistant to enter the deposited set, and non-confirming isolates were excluded — a per-isolate AMR gate, which the rubric defines as amr.

## `PRJNA604975` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Healthcare-associated (HA) BSI were defined as occurring >48 h post-hospital admission or ≤30 days since hospital discharge; other cases were defined as community-associated (CA)'
- reasoning: All isolates are blood cultures processed by a single hospital microbiology laboratory; the HA/CA split is an onset/prior-hospitalisation classification (a risk-factor label), which the rubric explicitly says is not a community sampling source, and blood cultures default to hospital — so there is no deliberate second community sampling arm to make it 'mixed'.
- ⚠️ rule_gap: Could state explicitly that 'community-onset'/'community-associated' bloodstream-infection labels defined by admission/discharge timing are onset classifications, not sampling-setting arms, even when the collecting lab also serves community facilities.

## `PRJNA686897` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): '20 medical intensive care units (ICUs) in 20 short-term acute care hospitals, 7 LTACHs, and 8 vSNFs in the Chicago region were invited to participate in serial 1-day point-prevalence surveys of residents.'
- reasoning: The study deliberately samples ICUs in acute-care hospitals (and LTACHs, which are acute hospital care) alongside vSNFs — ventilator-capable skilled nursing facilities whose residents are long-term-care/nursing-home residents, which the rubric classifies as community; sampling both inpatient-hospital and nursing-facility arms makes this 'mixed'.
- ⚠️ rule_gap: Clarify the named US facility types against the rubric: a 'long-term acute care hospital' (LTACH) stays hospital despite 'long-term' in its name, while a '(ventilator-capable) skilled nursing facility' (vSNF/SNF) is a community/LTC source — so an SNF arm triggers 'mixed'.

## `PRJEB30134` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Nine isolates (from nine patients) were collected from GPs in the Cambridgeshire area. The remainder were collected from CUH inpatients.'
- reasoning: The study design deliberately included two sampling sources — hospital inpatients AND patients sampled via local General Practices (primary care/outpatient = community), with nine GP-referred isolates actually collected, which is a genuine second-setting arm and meets the rubric's 'mixed' threshold (any deliberate community arm, even a small %).
- ⚠️ rule_gap: Clarify that specimens originating from primary-care/GP patients but physically cultured in a hospital diagnostic lab count by patient sampling source (community), not by where the lab work happened — so such a referral arm triggers 'mixed' rather than 'hospital'.

## `PRJEB21277` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text was provided, so neither the grader's 'hospital' claim nor the sheet's 'mixed' can be verified against source text; the grader's cited quote does not appear in any available paper passage to confirm or refute.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJEB27256`) Could clarify that drawing isolates from a national surveillance database (e.g. NORM) does not by itself make the deposit 'surveillance' when the deposited selection adds an AMR-defined contrast group; the deposit's own composition governs.
- [amr_study] (`PRJEB17615`) The paper text attached here describes PRJEB29738 (an all-resistant, amr-selective deposit), not the disputed PRJEB17615. The rubric should specify that when the attached paper's stated deposit accession differs from the accession under review, the paper cannot be used to grade it and adjudication must fall back to the EBI study title/description for the actual accession (here "susceptible and resistant isolates" => mixed).
- [amr_study] (`PRJNA789565`) When a case-control framing is implied ('clinical isolates from cases' plus controls), clarify whether deliberately added non-AMR controls make the deposit 'mixed' versus an all-cases-sequenced 'surveillance' frame, and specify how to adjudicate when no paper text is accessible (default to not_gradeable/undetermined).
- [study_setting] (`PRJNA604975`) Could state explicitly that 'community-onset'/'community-associated' bloodstream-infection labels defined by admission/discharge timing are onset classifications, not sampling-setting arms, even when the collecting lab also serves community facilities.
- [study_setting] (`PRJNA686897`) Clarify the named US facility types against the rubric: a 'long-term acute care hospital' (LTACH) stays hospital despite 'long-term' in its name, while a '(ventilator-capable) skilled nursing facility' (vSNF/SNF) is a community/LTC source — so an SNF arm triggers 'mixed'.
- [study_setting] (`PRJEB30134`) Clarify that specimens originating from primary-care/GP patients but physically cultured in a hospital diagnostic lab count by patient sampling source (community), not by where the lab work happened — so such a referral arm triggers 'mixed' rather than 'hospital'.

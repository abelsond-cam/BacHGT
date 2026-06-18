# Stage 2A adjudication — critique of grader-vs-sheet disagreements

Adjudicated **4** disagreements. Verdicts: {'sheet_correct': 1, 'model_correct': 3}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB39943` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All of the included 310 isolates were in the category R or I for at least one carbapenem as per inclusion criteria.'
- reasoning: Every isolate actually sequenced/deposited here had to be carbapenem non-susceptible (R or I), so each met an AMR gate — that is the rubric's definition of amr; the grader cited the parent surveys' design, but the susceptible (S) comparators they collected were not included/sequenced in this study, exactly the case the rubric says does not make it mixed.

## `PRJNA789565` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Deposited sequences are those of Klebsiella strains isolated from patient rectal swabs or clinical cultures.'
- reasoning: The sampling rule for the deposited set is colonization (rectal swabs) and clinical cultures, a non-AMR frame; nothing indicates each isolate had to be resistant or that susceptible matched controls were deliberately added, so it is surveillance, not mixed.

## `PRJNA604975` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Healthcare-associated (HA) BSI were defined as occurring >48 h post-hospital admission or ≤30 days since hospital discharge; other cases were defined as community-associated (CA)'
- reasoning: All isolates are bloodstream-infection blood cultures processed by a single hospital microbiology lab (a deep-tissue specimen type the rubric defaults to hospital), and the CA/HA split is explicitly a risk-factor classification based on hospitalization timing — not a deliberate community sampling arm, so it does not make the study mixed.
- ⚠️ rule_gap: Clarify that an unselected all-BSI/blood-culture study whose single hospital lab serves a regional catchment including community healthcare facilities stays 'hospital', and that a community-associated (CA) onset category defined by admission/discharge timing is a risk-factor classification, not a second community sampling source.

## `PRJEB36486` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'patients with sepsis admitted to Queen Elizabeth Central Hospital, Blantyre, Malawi'
- reasoning: Sepsis patients admitted to a named hospital are human inpatient care, which the rubric classifies as 'hospital'; nothing in the available evidence indicates a deliberate community/outpatient sampling arm to justify 'mixed'.

## Rule gaps / lessons (candidate rubric tweaks)

- [study_setting] (`PRJNA604975`) Clarify that an unselected all-BSI/blood-culture study whose single hospital lab serves a regional catchment including community healthcare facilities stays 'hospital', and that a community-associated (CA) onset category defined by admission/discharge timing is a risk-factor classification, not a second community sampling source.

# Stage 2A adjudication — critique of grader-vs-sheet disagreements

Adjudicated **7** disagreements. Verdicts: {'sheet_correct': 2, 'both_defensible': 1, 'undetermined': 1, 'model_correct': 3}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB39943` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All of the included 310 isolates were in the category R or I for at least one carbapenem as per inclusion criteria.'
- reasoning: Every isolate actually sequenced/deposited here had to be carbapenem non-susceptible (R or I), so each met an AMR gate — that is the rubric's definition of amr; the grader cited the parent surveys' design, but the susceptible (S) comparators they collected were not included/sequenced in this study, exactly the case the rubric says does not make it mixed.

## `PRJEB28400` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: both_defensible** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All patients admitted to the ICUs at the national Hospital for tropical Diseases and Bach Mai Hospital during a 6-month study period will be screened for MDRO.'
- reasoning: The stated frame ('all patients ... screened') reads as MDRO carriage surveillance, which the rubric's infection-control-screening clause calls surveillance; yet every isolate recovered/deposited from an MDRO screen is by definition multidrug-resistant, which the rubric's AMR-selective-screening clause classifies as amr — and with no paper text I cannot establish whether susceptible carriers were also sequenced.
- ⚠️ rule_gap: The rubric is self-contradictory for MDRO selective screening: it lists CPE/carbapenemase selective media as amr ('the resistance gate decides') but routine MDRO/infection-control screening as surveillance ('recovers all carriers regardless of resistance'). Clarify whether 'screened for MDRO' that deposits only the recovered multidrug-resistant organisms counts as an AMR gate (amr) or as a surveillance frame (surveillance), since MDRO recovery inherently selects resistant isolates.

## `PRJEB17615` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: The provided paper explicitly states its sequenced cohort was "deposited in the European Nucleotide Archive under the project accession PRJEB29738" — a DIFFERENT accession from the disputed PRJEB17615 — so the paper describes a resistant-only Philippines sub-deposit (263/2295 selected because ESBL+/cephalosporin-R/carbapenem-R) and cannot characterize what was actually deposited under PRJEB17615; the grader's 'mixed' rests on the PRJEB17615 study description ("sequencing of retrospective susceptible and resistant isolates") which is not in this paper, while the sheet's 'amr' matches this paper but is misattributed to the wrong accession.
- ⚠️ rule_gap: Grading must confirm the paper used actually deposits under (or explicitly references) the accession being graded. Here the paper deposits under PRJEB29738, not PRJEB17615, so it is not valid evidence for PRJEB17615; when the linked paper's deposit accession differs from the graded accession, fall back to that accession's own ENA study description and do not import the paper's sampling rule.

## `PRJNA789565` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Deposited sequences are those of Klebsiella strains isolated from patient rectal swabs or clinical cultures.'
- reasoning: The sampling rule for the deposited set is colonization (rectal swabs) and clinical cultures, a non-AMR frame; nothing indicates each isolate had to be resistant or that susceptible matched controls were deliberately added, so it is surveillance, not mixed.

## `PRJEB58136` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'Surveilance')
- **verdict: sheet_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'the Klebsiella spp. isolated from livestock were highly susceptible to the tested antimicrobials'
- reasoning: The 146 deposited isolates include 71 livestock isolates that were largely susceptible alongside the resistant clinical/sewage isolates, and the paper states selection for sequencing was 'based on antimicrobial susceptibility profile' — a deliberate resistant-human + susceptible-livestock contrast, which is exactly the rubric's 'mixed' example, not an all-isolates surveillance frame.
- ⚠️ rule_gap: Clarify that a deliberately AST-selected multi-niche comparison framed as 'surveillance' (e.g. resistant clinical vs susceptible livestock) is mixed, not surveillance — the surveillance label and One-Health framing should not override the per-niche AST-based selection that puts both resistant and susceptible isolates in the deposit.

## `PRJNA604975` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Healthcare-associated (HA) BSI were defined as occurring >48 h post-hospital admission or ≤30 days since hospital discharge; other cases were defined as community-associated (CA)'
- reasoning: All isolates are BSI blood cultures processed by the John Radcliffe Hospital microbiology lab as routine clinical workup; the CA/HA split is a timing/onset risk-factor classification, not a deliberate community sampling arm, which the rubric says does not make a study mixed.
- ⚠️ rule_gap: The rubric only explicitly flags 'hospital-associated' onset labels as risk-factor classifications; it should state symmetrically that 'community-associated/community-onset' labels defined by infection timing are likewise risk-factor classifications, and that a hospital lab's broad catchment 'serving community healthcare facilities' does not by itself make an all-BSI clinical-isolate study 'mixed'.

## `PRJEB30134` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Nine isolates (from nine patients) were collected from GPs in the Cambridgeshire area.'
- reasoning: Alongside the hospital-inpatient samples, the study deliberately included isolates referred from local General Practices (primary care/community); per the rubric any deliberate second-setting community/outpatient arm, even a small %, makes the project 'mixed'.
- ⚠️ rule_gap: Clarify how to treat primary-care/GP samples that are physically processed by a hospital diagnostic laboratory but collected outside hospital: the rubric's 'judge by where actually collected' implies community, but the hospital-lab routing could be misread as a hospital source.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJEB28400`) The rubric is self-contradictory for MDRO selective screening: it lists CPE/carbapenemase selective media as amr ('the resistance gate decides') but routine MDRO/infection-control screening as surveillance ('recovers all carriers regardless of resistance'). Clarify whether 'screened for MDRO' that deposits only the recovered multidrug-resistant organisms counts as an AMR gate (amr) or as a surveillance frame (surveillance), since MDRO recovery inherently selects resistant isolates.
- [amr_study] (`PRJEB17615`) Grading must confirm the paper used actually deposits under (or explicitly references) the accession being graded. Here the paper deposits under PRJEB29738, not PRJEB17615, so it is not valid evidence for PRJEB17615; when the linked paper's deposit accession differs from the graded accession, fall back to that accession's own ENA study description and do not import the paper's sampling rule.
- [amr_study] (`PRJEB58136`) Clarify that a deliberately AST-selected multi-niche comparison framed as 'surveillance' (e.g. resistant clinical vs susceptible livestock) is mixed, not surveillance — the surveillance label and One-Health framing should not override the per-niche AST-based selection that puts both resistant and susceptible isolates in the deposit.
- [study_setting] (`PRJNA604975`) The rubric only explicitly flags 'hospital-associated' onset labels as risk-factor classifications; it should state symmetrically that 'community-associated/community-onset' labels defined by infection timing are likewise risk-factor classifications, and that a hospital lab's broad catchment 'serving community healthcare facilities' does not by itself make an all-BSI clinical-isolate study 'mixed'.
- [study_setting] (`PRJEB30134`) Clarify how to treat primary-care/GP samples that are physically processed by a hospital diagnostic laboratory but collected outside hospital: the rubric's 'judge by where actually collected' implies community, but the hospital-lab routing could be misread as a hospital source.

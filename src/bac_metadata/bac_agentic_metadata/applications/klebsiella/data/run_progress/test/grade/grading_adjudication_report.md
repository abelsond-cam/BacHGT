# study grading adjudication — critique of grader-vs-sheet disagreements

Adjudicated **10** disagreements. Verdicts: {'model_correct': 6, 'sheet_correct': 2, 'undetermined': 2}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB10018` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'the first ten consecutive carbapenem-non-susceptible clinical isolates of either K. pneumoniae or E. coli, together with one carbapenem-susceptible same-species clinical isolate (per non-susceptible isolate) to serve as a comparator'
- reasoning: The deposited set was built by pairing each carbapenem-non-susceptible (AMR-selected) isolate with a deliberately-added carbapenem-susceptible comparator (773/1717, 45%), which is exactly the mixed design of AMR cases plus matched susceptible controls; it is not amr because not every sequenced isolate had to be resistant.

## `PRJNA529744` — amr_study

- grader: **amr**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: sheet_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'As part of a quality assurance project, WGS was also performed on all PCR-negative isolates (regardless of phenotypic results) from 1 July 2015 to 31 December 2016.'
- reasoning: Beyond the carbapenemase-gene-positive (AMR-selected) isolates, the deposit deliberately includes 159 PCR-negative isolates sequenced 'regardless of phenotypic results' (78 confirmed carbapenemase-negative, many meropenem-susceptible), so the sequenced set contains both AMR-selected and non-AMR isolates — the rubric's definition of mixed. The grader's referral-gate quote is the parent screening frame, but WGS was not restricted to isolates meeting it.
- ⚠️ rule_gap: Clarify that quality-assurance/negative-fraction isolates sequenced 'regardless of phenotype' and deposited alongside an AMR-selected core push a project to mixed (not amr), even when the parent referral used an AMR screen; also note that a screening MIC threshold set below the clinical breakpoint (e.g. meropenem ≥0.5) is not itself a per-isolate non-susceptibility gate.

## `PRJEB2111` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'sampled to maximize diversity'
- reasoning: Isolates entered the project to maximize genetic diversity across human/animal/environmental sources, with selection criteria "mainly unrelated to core phylogeny" and no per-isolate resistance gate; there is no AMR-selected-cases-plus-matched-susceptible-controls contrast design, so it is not 'mixed' and not 'amr'.
- ⚠️ rule_gap: The three allowed values don't cleanly cover a diversity-maximizing convenience collection that is neither AMR-gated nor a systematic non-AMR sampling frame (e.g. all blood cultures). Clarify that 'surveillance' is the default bucket for any non-AMR-gated selection rule, including diversity-driven curated collections.

## `PRJNA543274` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: undetermined** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'a collection of 285 K. pneumoniae genomes (170 were CP-Kp) isolated in Switzerland from human and non-human sources'
- reasoning: The deposited set combines AMR-selected carbapenemase-producers (170 CP-Kp) with 115 non-carbapenemase-producing isolates, so it fails the amr gate (not every isolate is resistance-selected — refuting the sheet) yet is a curated CP-focused collection rather than all clinical isolates of the taxon (refuting the model's surveillance); the both-categories composition fits 'mixed', so neither disputed value is correct.
- ⚠️ rule_gap: Clarify how to grade a resistance-themed collection that deposits a defined resistant subset PLUS non-resistant isolates of the same taxon without stating whether the non-resistant strains were deliberately added as comparators (→ mixed) versus swept in from a broad convenience/surveillance frame (→ surveillance); the abstract-only selection rule here does not disambiguate the two.

## `PRJNA825705` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Of these, 49 isolates were carbapenem-susceptible and 132 were carbapenem-resistant.'
- reasoning: The deposited set was a benchmark panel for a WGS-AST method-comparison study that deliberately included both carbapenem-susceptible (49) and carbapenem-resistant (132) isolates, so isolates were not gated on a resistant phenotype/genotype — the 'amr' label fails because susceptible isolates were sequenced, and the two-category make-up fits 'mixed'.
- ⚠️ rule_gap: The rubric's 'mixed' examples are case/control or contrast designs; it should clarify that a deliberately assembled benchmark/validation panel spanning susceptible and non-susceptible isolates (for AST-method evaluation) also counts as mixed rather than amr or surveillance.

## `PRJNA684006` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'surveillance')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text was provided, so I cannot independently verify the sampling rule for the deposited set. The grader's lone quote refers to only 2 strains selected as NDM-1-producing carbapenem-resistant hypervirulent isolates, which would suggest an AMR/virulence gate, but I cannot confirm this governed the whole project versus a broader surveillance frame without the source text.

## `PRJNA778230` — study_setting

- grader: **mixed**  |  sheet: **community** (raw: 'community')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): '279 contemporaneous KpSC isolates were collected from patients admitted to the University Hospital of Guadeloupe, a 900-bed teaching hospital'
- reasoning: The project deliberately samples a human inpatient (hospital) arm collected at the University Hospital alongside genuine non-human community arms (farms, slaughterhouse, veterinary clinics, animal shelter, and the environment), so both a hospital and a community sampling setting are present, satisfying 'mixed'.
- ⚠️ rule_gap: Clarify how to treat One Health projects that pair a human-hospital clinical arm with deliberate non-human (animal/environmental) arms — confirm the non-human arm counts as the 'genuine community/second setting' that triggers 'mixed' rather than defaulting the whole project to 'community'.

## `PRJNA543274` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: sheet_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'isolated in Switzerland from human and non-human sources during 2006-2020'
- reasoning: The project deliberately samples both human clinical isolates (from diagnostic labs including a hospital → hospital) and non-human animal/environmental isolates (→ community per the rubric), so two genuine settings are combined, which is 'mixed'.

## `PRJEB56146` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Most CPE isolates (285/389; 73%) were from patients admitted to hospital, whereas 23% (89/389) were obtained from outpatient settings, and 1% (2/389) from long-term care facilities.'
- reasoning: This nationwide reference-lab surveillance deliberately collected isolates from genuine outpatient settings (23%) and long-term care facilities (1%) alongside hospital inpatients (73%), so per the rubric any deliberate community/outpatient arm makes the whole project 'mixed'.

## `PRJEB37711` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'encompassing isolates from hospitals and clinical practices'
- reasoning: The survey deliberately collected isolates reported to both hospitals and requesting general practitioners, and the authors state UTI prevalence was high 'likely because community samples were also included,' meaning both hospital and genuine community/outpatient arms were sampled — the definition of mixed.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJNA529744`) Clarify that quality-assurance/negative-fraction isolates sequenced 'regardless of phenotype' and deposited alongside an AMR-selected core push a project to mixed (not amr), even when the parent referral used an AMR screen; also note that a screening MIC threshold set below the clinical breakpoint (e.g. meropenem ≥0.5) is not itself a per-isolate non-susceptibility gate.
- [amr_study] (`PRJEB2111`) The three allowed values don't cleanly cover a diversity-maximizing convenience collection that is neither AMR-gated nor a systematic non-AMR sampling frame (e.g. all blood cultures). Clarify that 'surveillance' is the default bucket for any non-AMR-gated selection rule, including diversity-driven curated collections.
- [amr_study] (`PRJNA543274`) Clarify how to grade a resistance-themed collection that deposits a defined resistant subset PLUS non-resistant isolates of the same taxon without stating whether the non-resistant strains were deliberately added as comparators (→ mixed) versus swept in from a broad convenience/surveillance frame (→ surveillance); the abstract-only selection rule here does not disambiguate the two.
- [amr_study] (`PRJNA825705`) The rubric's 'mixed' examples are case/control or contrast designs; it should clarify that a deliberately assembled benchmark/validation panel spanning susceptible and non-susceptible isolates (for AST-method evaluation) also counts as mixed rather than amr or surveillance.
- [study_setting] (`PRJNA778230`) Clarify how to treat One Health projects that pair a human-hospital clinical arm with deliberate non-human (animal/environmental) arms — confirm the non-human arm counts as the 'genuine community/second setting' that triggers 'mixed' rather than defaulting the whole project to 'community'.

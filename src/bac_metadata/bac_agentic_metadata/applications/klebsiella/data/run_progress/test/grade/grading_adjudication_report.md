# study grading adjudication — critique of grader-vs-sheet disagreements

Adjudicated **11** disagreements. Verdicts: {'model_correct': 8, 'both_defensible': 1, 'sheet_correct': 1, 'undetermined': 1}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB10018` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'together with one carbapenem-susceptible same-species clinical isolate (per non-susceptible isolate) to serve as a comparator'
- reasoning: The deposited set contains both AMR-selected isolates (944 carbapenem-non-susceptible) and deliberately-added susceptible matched comparators (773 carbapenem-susceptible, one per resistant case), which is precisely the rubric's 'mixed' two-category/matched-control design.

## `PRJNA529744` — amr_study

- grader: **amr**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Suspected CPE were defined as elevated meropenem MIC (≥0.5 mg/liter), reduced disc diffusion zones (meropenem, ≤24 mm [EUCAST/CLSI]), and/or positive phenotypic tests for carbapenemase detection (e.g., Carba NP and carbapenemase-inactivation method [CIM] testing), and/or carbapenemase gene detection by PCR at the local laboratory.'
- reasoning: Every isolate entered the deposited set only by being a referred 'suspected CPE', a gate requiring a non-susceptible carbapenem AST result or a resistance-gene/phenotypic carbapenemase positive — an AMR-selective referral frame, which the rubric classifies as amr. The PCR-negative isolates also passed this AMR referral gate, so they are not deliberately-added susceptible controls and the sheet's 'mixed' is unsupported.
- ⚠️ rule_gap: Clarify that when a project later sequences a 'gene-negative' subset that nonetheless entered via the same AMR referral/phenotypic gate (here PCR-negative but phenotypically suspected CPE), it remains amr and does not become 'mixed' — 'mixed' requires deliberately-added susceptible controls/contrast arm, not within-gate isolates that fail a confirmatory genotype test.

## `PRJEB2111` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'A total of 288 bacteria isolates, sampled to maximize diversity, were contributed from coauthors in six countries'
- reasoning: Isolates entered the deposit via a diversity-maximizing, non-AMR sampling rule (spanning infection, colonization, and environment, human and animal), with no evidence of an AMR phenotype/genotype gate or of deliberately added susceptible matched controls; that is a non-AMR sampling frame, so surveillance, not mixed.
- ⚠️ rule_gap: The rubric lists concrete surveillance examples (all blood cultures, all rectal swabs, all clinical isolates) but does not explicitly cover diversity-maximizing / convenience research collections that mix sources without an AMR gate or a paired-control contrast; clarify that such diversity-driven sampling defaults to surveillance and that 'AMR plus control' requires actual deliberately-added susceptible controls, not merely that some isolates happen to carry resistance genes.

## `PRJNA543274` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: both_defensible** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'We analysed a collection of 285 K. pneumoniae genomes (170 were CP-Kp) isolated in Switzerland from human and non-human sources during 2006-2020.'
- reasoning: The deposited set mixes 170 carbapenemase-producing (AMR-gated) isolates with 115 non-CP K. pneumoniae across human and non-human sources — a deliberate two-category contrast (CP vs non-CP, human vs non-human), which the rubric defines as 'mixed'; therefore neither the sheet's pure 'amr' nor the grader's pure 'surveillance' is correct, though each captures one facet. (The grader's cited n=999 evidence is not in this paper, so its reasoning is unreliable.)
- ⚠️ rule_gap: Clarify how to grade a deposit that combines an AMR-selected subset (carbapenemase-producers) with a smaller non-AMR comparator set in one collection: this is 'mixed' under the two-category-contrast clause, but the binary amr/surveillance dispute framing forces a verdict where the true value matches neither party — the schema needs a 'neither, value is mixed' verdict path.

## `PRJEB38540` — amr_study

- grader: **mixed**  |  sheet: **surveillance** (raw: 'surveillance')
- **verdict: sheet_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'enabling growth of all KP variants and generating an unbiased strain collection'
- reasoning: All samples were plated on four media to recover an unbiased collection of all Klebsiella variants (85% from non-selective SCAI agar), so no per-isolate resistance gate governed entry — the selective media were added to maximize recovery, not to build a deliberate resistant-vs-susceptible contrast, which is surveillance, not mixed.
- ⚠️ rule_gap: Clarify that running ALL samples through multiple media (including antibiotic-enriched/selective plates) to maximize comprehensive recovery is surveillance, not 'mixed' — mixed requires a deliberate two-category contrast or added matched susceptible controls, not merely the incidental presence of selective media in a recovery protocol.

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

## `PRJEB48268` — study_setting

- grader: **community**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **community** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Human faecal carriage isolates (n = 484) were collected from a general adult population in the Tromsø municipality in Norway during 2015–2016.'
- reasoning: Isolates come from general-population faecal carriage, marine environments, and farm animals — all non-hospital sources (community by the rubric's carriage-survey and non-human-host rules), with no inpatient sampling.

## `PRJNA778230` — study_setting

- grader: **mixed**  |  sheet: **community** (raw: 'community')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'to determine the genomic features of a collection of isolated nonhuman K. pneumoniae strains regardless of the putative antibiotic resistance phenotype and to compare them with contemporaneous clinical isolates'
- reasoning: The project deliberately samples both genuine community/non-human sources (animals, vegetables, water, soil, plus community-acquired human infections) AND hospital inpatient isolates (222 nosocomial isolates from medical wards, ICUs, emergency units of the University Hospital), which is the definition of 'mixed'.

## `PRJEB56146` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Most CPE isolates (285/389; 73%) were from patients admitted to hospital, whereas 23% (89/389) were obtained from outpatient settings, and 1% (2/389) from long-term care facilities.'
- reasoning: This nationwide reference-lab surveillance deliberately collected isolates from genuine outpatient settings (23%) and long-term care facilities (1%) alongside hospital inpatients (73%), so per the rubric any deliberate community/outpatient arm makes the whole project 'mixed'.

## `PRJEB37711` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'thus encompassing isolates from hospitals and clinical practices'
- reasoning: Isolates were reported to "the associated hospital or requesting general practitioners," so the survey deliberately captured both inpatient hospital and primary-care/community (general-practice) sources, meeting the rubric's definition of mixed.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJNA529744`) Clarify that when a project later sequences a 'gene-negative' subset that nonetheless entered via the same AMR referral/phenotypic gate (here PCR-negative but phenotypically suspected CPE), it remains amr and does not become 'mixed' — 'mixed' requires deliberately-added susceptible controls/contrast arm, not within-gate isolates that fail a confirmatory genotype test.
- [amr_study] (`PRJEB2111`) The rubric lists concrete surveillance examples (all blood cultures, all rectal swabs, all clinical isolates) but does not explicitly cover diversity-maximizing / convenience research collections that mix sources without an AMR gate or a paired-control contrast; clarify that such diversity-driven sampling defaults to surveillance and that 'AMR plus control' requires actual deliberately-added susceptible controls, not merely that some isolates happen to carry resistance genes.
- [amr_study] (`PRJNA543274`) Clarify how to grade a deposit that combines an AMR-selected subset (carbapenemase-producers) with a smaller non-AMR comparator set in one collection: this is 'mixed' under the two-category-contrast clause, but the binary amr/surveillance dispute framing forces a verdict where the true value matches neither party — the schema needs a 'neither, value is mixed' verdict path.
- [amr_study] (`PRJEB38540`) Clarify that running ALL samples through multiple media (including antibiotic-enriched/selective plates) to maximize comprehensive recovery is surveillance, not 'mixed' — mixed requires a deliberate two-category contrast or added matched susceptible controls, not merely the incidental presence of selective media in a recovery protocol.
- [amr_study] (`PRJNA825705`) The rubric's 'mixed' examples are case/control or contrast designs; it should clarify that a deliberately assembled benchmark/validation panel spanning susceptible and non-susceptible isolates (for AST-method evaluation) also counts as mixed rather than amr or surveillance.

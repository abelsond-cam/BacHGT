# Stage 2A adjudication — critique of grader-vs-sheet disagreements

Adjudicated **28** disagreements. Verdicts: {'sheet_correct': 3, 'model_correct': 20, 'undetermined': 5}.

(verdict `sheet_correct` ⇒ likely grader error; `model_correct` ⇒ likely a sheet error.)


## `PRJEB39943` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All of the included 310 isolates were in the category R or I for at least one carbapenem as per inclusion criteria.'
- reasoning: Every sequenced/deposited isolate had to be carbapenem non-susceptible (R or I) to enter the set, which is an AMR selection gate; the susceptible 'S' comparators belonged to the parent EuSCAPE/CCRE collection design and were not included here, which the rubric says to disregard.
- ⚠️ rule_gap: Clarify explicitly that comparator susceptible isolates collected by a parent survey but excluded from the deposited/analysed set do not make the project 'mixed' — only comparators actually sequenced under this accession count.

## `PRJEB29740` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All sequenced isolates in our study represent unique patient infection episodes, with only one isolate per patient.'
- reasoning: The deposited set is all K. pneumoniae clinical isolates causing infection, one per patient/episode, across mixed specimen types (blood, urine, pus, sputum, ETA), with resistance characterised afterwards via Kleborate (12% carried no ESBL/carbapenemase) — matching the rubric's surveillance definition, with no per-isolate AMR gate and no evidence of deliberately added susceptible matched controls to support 'mixed'.

## `PRJEB28400` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All patients admitted to the ICUs at the national Hospital for tropical Diseases and Bach Mai Hospital during a 6-month study period will be screened for MDRO.'
- reasoning: The rubric states isolates recovered via routine MDRO screening of patients are surveillance because the screen is the sampling frame, not a per-isolate AMR-selection gate; screening all admitted ICU patients matches this exactly.

## `PRJNA271899` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'For each resistant isolate, we also collected date- and species-matched meropenem-susceptible isolates.'
- reasoning: The 347 isolates deposited under PRJNA271899 comprise 147 AMR-selected resistant isolates plus 200 deliberately-added matched carbapenem-susceptible controls, which is exactly the 'mixed' design (AMR-selected cases plus susceptible matched controls), not pure AMR selection.

## `PRJEB50614` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'All sequenced isolates in our study represent unique patient infection episodes, with only one isolate per patient.'
- reasoning: Isolates were all K. pneumoniae recovered from hospital infections, one per patient across mixed specimen types (blood, ETA, urine, pus, sputum), with AMR characterised afterwards by Kleborate — a non-AMR sampling frame, which the rubric defines as surveillance; the paper describes no AMR phenotype/genotype gate nor any deliberately-added susceptible matched controls to justify the sheet's 'AMR plus control' mixed value.

## `PRJNA325243` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Laboratories were instructed to select only one isolate per client submission.'
- reasoning: The sampling rule was one clinical Klebsiella isolate per submission from clinically ill animals — a non-AMR frame; resistance genes were characterized afterwards via AMRFinderPlus, with no requirement that each isolate be resistant, which the rubric classifies as surveillance (the 'AMR Monitoring Program' name does not imply AMR-based selection).

## `PRJNA603790` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text is available; the only evidence is the EBI study title "Study of Klebsiella pneumoniae transmission in a long-term acute care hospital," which describes a transmission study but does not state whether each isolate had to meet an AMR attribute (e.g. carbapenem resistance) to be sequenced or whether all patient/screening isolates were sequenced — so neither 'amr' nor 'surveillance' can be confirmed.
- ⚠️ rule_gap: Clarify how to grade LTACH/hospital transmission studies when only a title is available: such studies commonly either (a) sequence all K. pneumoniae from colonized/infected patients via MDRO screening (surveillance) or (b) restrict to a resistant phenotype such as carbapenem-resistant K. pneumoniae (amr). The word 'transmission' alone should not default to surveillance, since CRKP transmission cohorts apply a per-isolate resistance gate.

## `PRJEB5065` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'surveillance')
- **verdict: model_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Isolates were collected if they were resistant to at least one antibiotic in three of the following classes: penicillins, carbapenems, cephalosporins, tetracyclines, aminoglycosides, and fluoroquinolones.'
- reasoning: Each of the 250 deposited isolates had to meet an MDR (non-susceptible AST) selection gate to enter the set, which is the rubric's definition of 'amr'; the parent BSAC bacteraemia surveillance program is the broader collection design the rubric explicitly says to disregard.
- ⚠️ rule_gap: The rubric could add an explicit example that an AMR-selected (MDR) subset drawn FROM a bacteraemia surveillance program is 'amr', since the surveillance origin of the parent survey misled the sheet despite the per-isolate resistance selection gate on the deposited set.

## `PRJEB17615` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: The paper text provided describes isolates deposited under PRJEB29738 ('Raw sequence data generated were deposited in the European Nucleotide Archive under the project accession PRJEB29738'), NOT the disputed accession PRJEB17615; so the paper cannot establish what sampling rule governed the isolates actually deposited under PRJEB17615. Within the paper itself the selection is purely AMR-based (all 263 drawn from 'ESBL-positive, and/or cephalosporin resistant, and/or carbapenem-resistant' isolates, with no susceptible controls), which would read 'amr', while the grader's 'mixed' rests on an EBI study description ('retrospective susceptible and resistant isolates') that is absent from the paper — leaving the disputed accession unresolvable from the paper alone.
- ⚠️ rule_gap: Clarify how to grade when the paper's stated deposit accession differs from the accession under adjudication, and how to treat an umbrella/parent ENA project (e.g. PRJEB17615, whose own description spans susceptible + resistant retrospective plus prospective novel-antibiogram isolates) versus a narrower taxon-specific child deposit (e.g. PRJEB29738, an AMR-only Klebsiella subset): specify whether the parent accession is graded on its own deposited contents/description or whether a child-accession paper may be used as evidence for it.

## `PRJNA557275` — amr_study

- grader: **mixed**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Whole-genome sequencing was performed on 388 isolates, including 164 PR isolates.'
- reasoning: Of the 388 sequenced/deposited isolates only 164 met the AMR (polymyxin-resistant) attribute; the remaining ~224 are non-PR serial isolates from the same patients, so the set contains both AMR-selected and non-AMR isolates, which is 'mixed', not 'amr'.
- ⚠️ rule_gap: Clarify that longitudinal/serial polymyxin-susceptible isolates collected from AMR-positive patients (to study de novo emergence) count as the non-AMR component for 'mixed', the same as deliberately-added matched susceptible controls.

## `PRJNA789565` — amr_study

- grader: **surveillance**  |  sheet: **mixed** (raw: 'AMR plus control')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text was provided, so neither the grader's surveillance quote nor the sheet's 'AMR plus control' claim can be verified against the source; the dispute cannot be resolved from the evidence given.

## `PRJNA857686` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Fastq files for HAI bacteria sequenced at the Nevada State Public Health Lab'
- reasoning: The only available evidence (the EBI study description) frames the sampling as sequencing of healthcare-associated-infection bacteria at a state public health lab — a non-AMR sampling rule with no stated requirement that each isolate be resistant; per the rubric, MDRO/infection-control sequencing and the unsupported 'AMR' label do not establish per-isolate AMR selection.
- ⚠️ rule_gap: The description does not explicitly state the per-isolate selection gate; clarify whether a state-public-health-lab HAI sequencing project lacking any explicit resistance-selection statement should default to surveillance rather than being treated as not_gradeable.

## `PRJEB30134` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: sheet_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'we collected all carbapenemase-producing Gram-negative bacteria isolated in the diagnostic microbiology laboratory at Cambridge University Hospitals NHS Foundation Trust (CUH) between 2014 and 2020'
- reasoning: The project's single, explicit inclusion rule is that every isolate had to be a carbapenemase producer (a pre-defined resistance genotype, PCR-confirmed per Fig.1b, plus reduced carbapenem susceptibility on AST) — that is the per-isolate AMR-selection gate the rubric defines as amr, applied uniformly across both clinical and screening specimens, not a resistance trait characterised afterwards.
- ⚠️ rule_gap: The rubric's MDRO/infection-control screening carve-out (which deems screening-derived isolates surveillance) collides with resistance-selective screening such as CPE selective media, where only carbapenemase producers are ever recovered. Clarify that when the screen is itself an AMR-selective method AND the project's universal inclusion criterion is a resistance phenotype/genotype, the study is amr even if most isolates arrived via screening swabs; reserve the surveillance carve-out for screens that recover all carriers/flora regardless of resistance.

## `PRJEB58018` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): '200 isolates, comprising 66 NDM-1/OXA-48-producing and 134 NDM-1-producing K. pneumoniae, were subjected to Illumina (Illumina, San Diego, United States) whole genome sequencing'
- reasoning: Every sequenced isolate had to be NDM-1- or NDM-1/OXA-48-producing — i.e. positive for a pre-defined carbapenemase resistance gene — which is exactly the rubric's amr criterion (positive detection of a pre-defined antibiotic-resistance gene as the per-isolate selection gate); the subset of 200 from 330 was still drawn entirely from that NDM-positive pool.
- ⚠️ rule_gap: Clarify that a national-reference-centre carbapenemase collection (all isolates selected by carbapenemase-gene positivity) counts as amr even when some isolates originate from screening/stool specimens — the resistance-gene positivity, not the specimen-collection method, is the sampling gate, distinguishing it from the surveillance 'MDRO screening frame' case.

## `PRJNA787062` — amr_study

- grader: **amr**  |  sheet: **surveillance** (raw: 'surveillance')
- **verdict: model_correct** → correct_value: **amr** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'the study aimed to determine the genomic epidemiology of ESBL, AmpC and carbapenemase producing and colistin resistance Enterobacteriaceae'
- reasoning: The deposited set is defined by resistance phenotype/genotype — only ESBL-, AmpC-, carbapenemase-producing or colistin-resistant Enterobacteriaceae entered the project — so each sequenced isolate had to meet an AMR attribute, matching the rubric's 'amr' definition.
- ⚠️ rule_gap: Study-aim phrasing like 'genomic epidemiology of [resistant organisms]' is read here as a per-isolate AMR-selection gate, but it could also describe a surveillance frame in which all clinical isolates were collected and resistance characterised afterward; the rubric should clarify whether enumerating resistance categories as the study's target organism is sufficient to call 'amr' absent an explicit per-isolate selection statement.

## `PRJNA396774` — amr_study

- grader: **mixed**  |  sheet: **surveillance** (raw: 'Surveillance')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'A project consisting of both ESBL and Non-ESBL Klebsiella pneumoniae strains.'
- reasoning: The deposited set deliberately pairs AMR-selected ESBL-producing isolates with Non-ESBL isolates, which is exactly the rubric's 'mixed' design (AMR-selected cases plus non-AMR isolates), not a single non-AMR surveillance sampling rule.
- ⚠️ rule_gap: Clarify how to classify a set described as 'both ESBL and Non-ESBL' when it is unclear whether the Non-ESBL strains are a deliberately constructed susceptible-comparison arm (mixed) versus all isolates collected under one frame with ESBL status merely characterised afterwards (surveillance); the phrase 'consisting of both' here reads as a deliberate two-category design.

## `PRJEB58136` — amr_study

- grader: **mixed**  |  sheet: **surveillance** (raw: 'Surveilance')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'The selection of isolates for sequencing based on antimicrobial susceptibility profile may introduce bias.'
- reasoning: The authors explicitly state sequencing selection was gated on AST profile (so not pure non-AMR surveillance), yet the deposited 146 include 71 livestock isolates that were "highly susceptible to the tested antimicrobials" and predicted susceptible to last-resort drugs — so the set holds both AMR-selected (resistant clinical/sewage) and non-AMR (susceptible livestock) isolates, which is mixed, not all-resistant amr.
- ⚠️ rule_gap: The rubric frames 'mixed' around AMR cases plus deliberately-added susceptible matched controls; it should clarify that a contrast design selecting isolates 'based on susceptibility profile' across niches (resistant human/effluent vs. largely-susceptible livestock comparison group) also qualifies as mixed even when the susceptible arm is a source-defined comparison group rather than per-case matched controls.

## `PRJNA1087366` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): "For all analyses, the patient's first clinical isolate from blood or CSF was selected."
- reasoning: The sampling gate was a non-AMR rule (first clinical blood/CSF isolate per patient, deduplicated by genetic profile, species with ≥20 isolates); resistance was characterized afterwards, which the rubric explicitly states does not make it amr, and the project's AMR focus does not by itself imply AMR-based selection.

## `PRJEB1800` — amr_study

- grader: **surveillance**  |  sheet: **amr** (raw: 'AMR')
- **verdict: model_correct** → correct_value: **surveillance** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'We selected a random subset of 90 K. pneumoniae (using a random integer generator) from a collection of 135 K. pneumoniae that were isolated and stored in Patan Hospital between May and December 2012.'
- reasoning: Isolates entered the deposited set by random selection from all clinical K. pneumoniae across mixed specimen types (blood, urine, catheter tips, respiratory, pus, other), not by a per-isolate resistant phenotype/genotype gate; resistance was characterised afterwards, which the rubric says does not make it amr.

## `PRJNA604975` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'The microbiology laboratory serves all four hospitals and all community healthcare facilities within Oxfordshire'
- reasoning: Isolates were collected via a lab serving both hospital and community healthcare facilities, and the study explicitly partitions BSIs into healthcare-associated (e.g. 510/882, 59% HA) and community-associated cases, so the project specifically includes both hospital and community sources, which the rubric defines as 'mixed'.
- ⚠️ rule_gap: Clarify how BSI studies that span both healthcare-associated and community-associated cases should be graded: the rubric's 'all blood cultures -> hospital' default conflicts with the 'mixed' rule when a lab serves both hospital and community facilities. Specify whether the collection setting or the HA/CA acquisition classification governs the hospital/community/mixed call.

## `PRJNA325243` — study_setting

- grader: **hospital**  |  sheet: **community** (raw: 'community')
- **verdict: sheet_correct** → correct_value: **community** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'from various animal hosts that presented to veterinary hospitals in the U.S.'
- reasoning: The rubric assigns non-human host to community, and these isolates come from animal patients (canine, equine, feline, etc.); the hospital-precedence rule covers hospital-environment/wastewater isolates, not animal clinical isolates sampled at veterinary diagnostic labs, so 'veterinary hospital' does not convert a non-human host study to hospital.
- ⚠️ rule_gap: The rubric's hospital precedence ('hospital source wins over non-human -> community') does not address veterinary/animal-clinical settings. Clarify explicitly that 'hospital' means human inpatient care, and that animal hosts presenting to veterinary hospitals or veterinary diagnostic laboratories remain 'community' (the precedence applies only to human-hospital environment/wastewater isolates, not to non-human clinical isolates collected at animal clinics).

## `PRJNA564424` — study_setting

- grader: **mixed**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **mixed** (adjudicator: claude-opus-4-8)
- justification (verbatim): '8 (1%) isolates from English outpatient/primary care settings'
- reasoning: The study deliberately sampled both hospital inpatient isolates (~99%) and outpatient/primary care isolates (community per the rubric, as category (iv) in Methods: 'any KPC-E isolates from outpatient/primary care settings'), so it 'specifically includes some of both hospital and community sources' = mixed.
- ⚠️ rule_gap: Clarify the interaction between the 'mixed' definition (study includes some of both) and the gradeable >90% threshold: when one setting (here community) is a small but deliberately-sampled minority (1%), specify whether that triggers 'mixed' or whether the project should default to the >90% dominant value (hospital). State an explicit proportion cutoff or rule that any deliberate inclusion of a second setting makes it mixed.

## `PRJEB29143` — study_setting

- grader: **community**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **community** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Klebsiella pneumoniae strains from healthy carriers'
- reasoning: The rubric explicitly classes carriage surveys as community, and the study title describes the isolates as coming from healthy carriers, with no evidence of any hospital/inpatient sources to justify 'mixed'.

## `PRJEB35685` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text is available, and the grader's quote ('national laboratory surveillance') cannot be located or verified in any provided source; neither 'hospital' nor 'mixed' can be substantiated from the materials given.
- ⚠️ rule_gap: National laboratory surveillance schemes can aggregate isolates from both inpatient and community/clinic sources; the rubric should specify whether 'national surveillance' defaults to hospital (clinical referral) or must be treated as mixed/not_gradeable absent explicit source breakdown.

## `PRJEB36486` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: undetermined** → correct_value: **None** (adjudicator: claude-opus-4-8)
- justification (verbatim): ''
- reasoning: No paper text was provided, so neither the grader's 'hospital' quote nor the sheet's 'mixed' claim can be verified against the source; per instructions I must judge only from supplied paper text, which is absent.

## `PRJDB12075` — study_setting

- grader: **community**  |  sheet: **hospital** (raw: 'hospital')
- **verdict: model_correct** → correct_value: **community** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'both sets of isolates were obtained from the same 178 residents in LTCFs'
- reasoning: Isolates are oral and rectal carriage swabs from residents of long-term-care facilities, not acute-hospital inpatients; per the rubric this is a human carriage survey outside the hospital, i.e. community.
- ⚠️ rule_gap: The rubric lists hospital, clinics, and general community but does not explicitly place long-term-care facilities / nursing homes. Clarify that residential LTCF/nursing-home carriage sampling is 'community' (not 'hospital'), even when ethics oversight is via a university hospital.

## `PRJNA1048341` — study_setting

- grader: **hospital**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **hospital** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'The selected isolates came from 18 hospitals located in the eight provinces of Andalusia.'
- reasoning: All isolates derive from 18 hospitals via a healthcare-associated-infection surveillance program; the clinical, colonization, and (hospital-)environmental sub-sources are all hospital-based, so the whole-project value is hospital per the rubric (hospital environment wins over the non-human rule).
- ⚠️ rule_gap: Clarify that 'mixed' requires both hospital AND genuine community/outpatient settings, not merely a mix of specimen categories (clinical vs colonization vs environmental) that are all hospital-sourced; explicitly note that hospital-based colonization/carriage screening counts as hospital.

## `PRJNA885285` — study_setting

- grader: **community**  |  sheet: **mixed** (raw: 'mixed')
- **verdict: model_correct** → correct_value: **community** (adjudicator: claude-opus-4-8)
- justification (verbatim): 'Faecal samples were collected from community participants of Siem Reap, Cambodia in a cross-sectional study from August to November 2019.'
- reasoning: All 290 faecal samples were carriage specimens collected from household participants in the community (children approached 14–28 days after discharge); the 'hospital arm' denotes recent-hospitalization exposure history, not a hospital collection setting, so per the rubric this is a community carriage survey, not mixed.
- ⚠️ rule_gap: Clarify that a study 'arm' labelled hospital-associated based on participants' prior hospitalization history (a risk-factor classification) does NOT constitute a hospital sampling source; setting is judged by where/how isolates were actually collected, so such risk-factor stratification should not trigger 'mixed'.

## Rule gaps / lessons (candidate rubric tweaks)

- [amr_study] (`PRJEB39943`) Clarify explicitly that comparator susceptible isolates collected by a parent survey but excluded from the deposited/analysed set do not make the project 'mixed' — only comparators actually sequenced under this accession count.
- [amr_study] (`PRJNA603790`) Clarify how to grade LTACH/hospital transmission studies when only a title is available: such studies commonly either (a) sequence all K. pneumoniae from colonized/infected patients via MDRO screening (surveillance) or (b) restrict to a resistant phenotype such as carbapenem-resistant K. pneumoniae (amr). The word 'transmission' alone should not default to surveillance, since CRKP transmission cohorts apply a per-isolate resistance gate.
- [amr_study] (`PRJEB5065`) The rubric could add an explicit example that an AMR-selected (MDR) subset drawn FROM a bacteraemia surveillance program is 'amr', since the surveillance origin of the parent survey misled the sheet despite the per-isolate resistance selection gate on the deposited set.
- [amr_study] (`PRJEB17615`) Clarify how to grade when the paper's stated deposit accession differs from the accession under adjudication, and how to treat an umbrella/parent ENA project (e.g. PRJEB17615, whose own description spans susceptible + resistant retrospective plus prospective novel-antibiogram isolates) versus a narrower taxon-specific child deposit (e.g. PRJEB29738, an AMR-only Klebsiella subset): specify whether the parent accession is graded on its own deposited contents/description or whether a child-accession paper may be used as evidence for it.
- [amr_study] (`PRJNA557275`) Clarify that longitudinal/serial polymyxin-susceptible isolates collected from AMR-positive patients (to study de novo emergence) count as the non-AMR component for 'mixed', the same as deliberately-added matched susceptible controls.
- [amr_study] (`PRJNA857686`) The description does not explicitly state the per-isolate selection gate; clarify whether a state-public-health-lab HAI sequencing project lacking any explicit resistance-selection statement should default to surveillance rather than being treated as not_gradeable.
- [amr_study] (`PRJEB30134`) The rubric's MDRO/infection-control screening carve-out (which deems screening-derived isolates surveillance) collides with resistance-selective screening such as CPE selective media, where only carbapenemase producers are ever recovered. Clarify that when the screen is itself an AMR-selective method AND the project's universal inclusion criterion is a resistance phenotype/genotype, the study is amr even if most isolates arrived via screening swabs; reserve the surveillance carve-out for screens that recover all carriers/flora regardless of resistance.
- [amr_study] (`PRJEB58018`) Clarify that a national-reference-centre carbapenemase collection (all isolates selected by carbapenemase-gene positivity) counts as amr even when some isolates originate from screening/stool specimens — the resistance-gene positivity, not the specimen-collection method, is the sampling gate, distinguishing it from the surveillance 'MDRO screening frame' case.
- [amr_study] (`PRJNA787062`) Study-aim phrasing like 'genomic epidemiology of [resistant organisms]' is read here as a per-isolate AMR-selection gate, but it could also describe a surveillance frame in which all clinical isolates were collected and resistance characterised afterward; the rubric should clarify whether enumerating resistance categories as the study's target organism is sufficient to call 'amr' absent an explicit per-isolate selection statement.
- [amr_study] (`PRJNA396774`) Clarify how to classify a set described as 'both ESBL and Non-ESBL' when it is unclear whether the Non-ESBL strains are a deliberately constructed susceptible-comparison arm (mixed) versus all isolates collected under one frame with ESBL status merely characterised afterwards (surveillance); the phrase 'consisting of both' here reads as a deliberate two-category design.
- [amr_study] (`PRJEB58136`) The rubric frames 'mixed' around AMR cases plus deliberately-added susceptible matched controls; it should clarify that a contrast design selecting isolates 'based on susceptibility profile' across niches (resistant human/effluent vs. largely-susceptible livestock comparison group) also qualifies as mixed even when the susceptible arm is a source-defined comparison group rather than per-case matched controls.
- [study_setting] (`PRJNA604975`) Clarify how BSI studies that span both healthcare-associated and community-associated cases should be graded: the rubric's 'all blood cultures -> hospital' default conflicts with the 'mixed' rule when a lab serves both hospital and community facilities. Specify whether the collection setting or the HA/CA acquisition classification governs the hospital/community/mixed call.
- [study_setting] (`PRJNA325243`) The rubric's hospital precedence ('hospital source wins over non-human -> community') does not address veterinary/animal-clinical settings. Clarify explicitly that 'hospital' means human inpatient care, and that animal hosts presenting to veterinary hospitals or veterinary diagnostic laboratories remain 'community' (the precedence applies only to human-hospital environment/wastewater isolates, not to non-human clinical isolates collected at animal clinics).
- [study_setting] (`PRJNA564424`) Clarify the interaction between the 'mixed' definition (study includes some of both) and the gradeable >90% threshold: when one setting (here community) is a small but deliberately-sampled minority (1%), specify whether that triggers 'mixed' or whether the project should default to the >90% dominant value (hospital). State an explicit proportion cutoff or rule that any deliberate inclusion of a second setting makes it mixed.
- [study_setting] (`PRJEB35685`) National laboratory surveillance schemes can aggregate isolates from both inpatient and community/clinic sources; the rubric should specify whether 'national surveillance' defaults to hospital (clinical referral) or must be treated as mixed/not_gradeable absent explicit source breakdown.
- [study_setting] (`PRJDB12075`) The rubric lists hospital, clinics, and general community but does not explicitly place long-term-care facilities / nursing homes. Clarify that residential LTCF/nursing-home carriage sampling is 'community' (not 'hospital'), even when ethics oversight is via a university hospital.
- [study_setting] (`PRJNA1048341`) Clarify that 'mixed' requires both hospital AND genuine community/outpatient settings, not merely a mix of specimen categories (clinical vs colonization vs environmental) that are all hospital-sourced; explicitly note that hospital-based colonization/carriage screening counts as hospital.
- [study_setting] (`PRJNA885285`) Clarify that a study 'arm' labelled hospital-associated based on participants' prior hospitalization history (a risk-factor classification) does NOT constitute a hospital sampling source; setting is judged by where/how isolates were actually collected, so such risk-factor stratification should not trigger 'mixed'.

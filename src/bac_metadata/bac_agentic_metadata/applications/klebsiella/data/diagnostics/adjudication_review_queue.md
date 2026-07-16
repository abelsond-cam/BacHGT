# Adjudication review queue — residual agent-vs-manual disagreements

Only rows the Opus adjudicator did NOT rule for the agent (it sided with the manual sheet, called both defensible, or was undetermined). Walk with `engine.cli.review_adjudication --interactive`.

**16 rows** — find 9 · grade 7

| tag | source | study | field | agent | manual | verdict | adjudicator says |
|---|---|---|---|---|---|---|---|
| train | find | PRJNA855907 | paper | Characterization of Extensively  | Plasmid genomic epidemiology of  | both_describe | PRJNA855907 is the CNISP 'Carbapenemase Producin |
| train | find | PRJEB22252 | paper | Stunted microbiota and opportuni | Unpublished; Bioproject title: B | curated_correct | The ENA project PRJEB22252 ('Baby_Biome_Study_ga |
| train | find | PRJNA765801 | paper | Plasmid dynamics driving carbape | Whole genome sequencing reveals  | curated_correct | The ENA project PRJNA765801 is blaNDM-specific,  |
| train | find | PRJEB58018 | paper | International spread or local ou | Increase in NDM-1 and NDM-1/OXA- | curated_correct | ENA PRJEB58018 (201 taxon samples; title/descrip |
| train | find | PRJDB12075 | paper | Genomic epidemiology and tempera | Disinfectant Susceptibility of T | curated_correct | Paper A makes a primary deposit statement for PR |
| train | find | PRJNA564992 | paper | Comparison of phenotypic antimic | ESBL-positive Escherichia coli a | curated_correct | The ENA project PRJNA564992 is titled 'Character |
| train | grade | PRJEB39943 | amr_study | mixed | amr | sheet_correct | amr |
| train | grade | PRJEB17615 | amr_study | mixed | amr | sheet_correct | amr |
| train | grade | PRJNA395086 | amr_study | amr | surveillance | undetermined | No paper text was provided, so I cannot independ |
| test | find | PRJNA658369 | paper | Molecular and clinical epidemiol | Molecular and clinical epidemiol | both_describe | Both papers are primary CRACKLE-2 genome-sequenc |
| test | find | PRJEB48268 | paper | A genome-wide One Health study o | Risk of death in Klebsiella pneu | curated_correct | ENA project PRJEB48268 (title NORKAB, 1110 sampl |
| test | find | PRJEB37504 | paper | Genomic surveillance reveals dif | Genomic analysis of the initial  | curated_correct | Paper B explicitly names PRJEB37504 as the depos |
| test | grade | PRJNA529744 | amr_study | amr | mixed | sheet_correct | mixed |
| test | grade | PRJNA543274 | amr_study | surveillance | amr | undetermined | mixed |
| test | grade | PRJNA684006 | amr_study | amr | surveillance | undetermined | No paper text was provided, so I cannot independ |
| test | grade | PRJNA543274 | study_setting | hospital | mixed | sheet_correct | mixed |

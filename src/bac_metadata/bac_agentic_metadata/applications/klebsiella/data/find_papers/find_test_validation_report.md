# paper finding validation — paper-finding vs curated paper_link (test)

Found rows in test: **47**.

## Find-accuracy: 0.65  (30/46 matched among accessions with a curated link)

Category counts: {'exact_match': 22, 'mismatch': 9, 'title_match': 8, 'not_found': 7, 'no_curated_link': 1}

## Winning channel (matched finds)

```
chosen_found_via
europepmc_accession                        15
europepmc_accession,ncbi_bioproject         5
web_search                                  4
europepmc_accession,europepmc_secondary     1
published_version,web_search                1
europepmc_secondary,ncbi_bioproject         1
europepmc_accession,europepmc_title         1
ncbi_bioproject                             1
europepmc_secondary,europepmc_title         1
```

## Grounded-verify: 22/47 picks had the accession confirmed in the paper text.
Confidence mix: {'high': 30, 'medium': 10, 'low': 7}

## Mismatches (found ≠ any curated paper)

- `PRJNA658369` found=10.1016/s1473-3099(19)30755-8 (via ncbi_bioproject, verified=nan) vs 1 curated: ['https://pubmed.ncbi.nlm.nih.gov/32151332/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC8882129/']
- `PRJEB48268` found=10.1186/s13073-025-01466-0 (via europepmc_accession, verified=True) vs 1 curated: ['https://www.sciencedirect.com/science/article/pii/S0163445324000896#sec0105']
- `PRJEB37504` found=10.1186/s13756-025-01553-2 (via europepmc_accession, verified=False) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC10327503/#sec15. , https://pmc.ncbi.nlm.nih.gov/articles/PMC10111884/']
- `PRJNA543274` found=10.1186/s13073-021-00960-5 (via ncbi_bioproject, verified=False) vs 1 curated: ['https://pubmed.ncbi.nlm.nih.gov/35085791/']
- `PRJEB32655` found=10.1099/mgen.0.001035 (via web_search, verified=False) vs 1 curated: ['https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJEB32655']
- `PRJEB43870` found=10.3389/fmicb.2021.725414 (via web_search, verified=False) vs 1 curated: ['https://doi.org/10.3389/fmicb.2023.1193274']
- `PRJNA532291` found=10.1038/s41598-019-55008-x (via web_search, verified=False) vs 1 curated: ['Could not find']
- `PRJEB57159` found=10.1186/s13073-025-01466-0 (via web_search, verified=False) vs 1 curated: ['https://doi.org/10.3389/fmicb.2023.1193274']
- `PRJNA548120` found=10.1128/msphere.01156-20 (via ncbi_bioproject, verified=False) vs 1 curated: ['https://pathogen.watch/collection/klebnet-neonatal-sepsis; https://journals.asm.org/doi/full/10.1128/spectrum.05215-22']

## Abstained (not_found, with a curated link)

- `PRJNA288601` (n_candidates=25) curated=['https://www.microbiologyresearch.org/content/journal/mgen/10.1099/mgen.0.001119']
- `PRJEB21081` (n_candidates=0) curated=['https://www.ebi.ac.uk/ena/browser/view/PRJEB21081']
- `PRJEB29739` (n_candidates=13) curated=['https://pmc.ncbi.nlm.nih.gov/articles/PMC8634535/; https://pathogen.watch/collection/klebnet-neonatal-sepsis']
- `PRJEB53835` (n_candidates=3) curated=['-']
- `PRJNA810752` (n_candidates=2) curated=['Could not find']
- `PRJNA339843` (n_candidates=6) curated=['https://journals.asm.org/doi/epub/10.1128/aac.01127-24']
- `PRJNA433394` (n_candidates=5) curated=['https://journals.asm.org/doi/10.1128/aac.01127-24']

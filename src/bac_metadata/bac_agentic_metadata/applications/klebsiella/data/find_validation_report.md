# Stage 2B validation — paper-finding vs curated paper_link (train+val)

Found rows in train+val: **109**.

## Find-accuracy: 0.62  (63/102 matched among accessions with a curated link)

Category counts: {'exact_match': 54, 'not_found': 20, 'mismatch': 19, 'title_match': 9, 'no_curated_link': 7}

## Winning channel (matched finds)

```
chosen_found_via
europepmc_accession                      47
europepmc_accession,europepmc_title       6
europepmc_accession,ncbi_bioproject       4
ncbi_bioproject                           3
europepmc_accession,published_version     2
europepmc_title                           1
```

## Grounded-verify: 61/109 picks had the accession confirmed in the paper text.
Confidence mix: {'high': 70, 'medium': 27, 'low': 12}

## Mismatches (found ≠ any curated paper)

- `PRJEB39943` found=10.1016/j.lanmic.2025.101320 (via europepmc_accession, verified=True) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC10668257/']
- `PRJNA475751` found=10.1101/2024.02.16.24302955 (via europepmc_accession, verified=nan) vs 2 curated: ['https://academic.oup.com/cid/advance-article/doi/10.1093/cid/ciaf216/8122482?login=true', 'https://journals.asm.org/doi/10.1128/mbio.01945-19#tabS1']
- `PRJNA768622` found=10.1093/jacamr/dlae140 (via europepmc_accession,published_version, verified=True) vs 1 curated: ['https://pubmed.ncbi.nlm.nih.gov/32094139/']
- `PRJDB5929` found=10.1128/aac.01520-18 (via ncbi_bioproject, verified=False) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC9453063/']
- `PRJNA1028672` found=10.1038/s41564-024-01612-1 (via europepmc_accession, verified=True) vs 1 curated: ['https://www.nature.com/articles/s41564-024-01612-1#:~:text=In%20conclusion%2C%20we%20describe%20a,characteristics%20of%20the%20CRKP%20strains.']
- `PRJNA855907` found=10.1128/spectrum.00975-22 (via europepmc_accession, verified=True) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC11261825/']
- `PRJEB38289` found=10.1038/s41598-021-85724-2 (via europepmc_accession, verified=True) vs 1 curated: ['https://pubmed.ncbi.nlm.nih.gov/35963896/']
- `PRJEB46513` found=10.1371/journal.pgph.0005965 (via europepmc_accession, verified=True) vs 1 curated: ['https://www.medrxiv.org/content/10.1101/2025.06.28.25330253v1.full; https://pathogen.watch/collection/klebnet-neonatal-sepsis']
- `PRJEB63361` found=10.1371/journal.ppat.1013859 (via europepmc_accession, verified=True) vs 1 curated: ['https://www.ncbi.nlm.nih.gov/bioproject/?term=PRJEB63361']
- `PRJEB5065` found=10.1101/gr.205245.116 (via europepmc_accession,ncbi_bioproject, verified=True) vs 1 curated: ['https://pubmed.ncbi.nlm.nih.gov/28223459/']
- `PRJEB15226` found=10.1128/jcm.01648-16 (via europepmc_accession,europepmc_title, verified=nan) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC8549354/#sec27']
- `PRJNA278886` found=10.1128/aac.02040-18 (via europepmc_accession, verified=True) vs 1 curated: ['https://pubmed.ncbi.nlm.nih.gov/38157139/']
- `PRJNA544438` found=10.1371/journal.pone.0239924 (via europepmc_accession, verified=True) vs 1 curated: ['https://www.sciencedirect.com/science/article/pii/S0924857923002467']
- `PRJNA765801` found=10.1038/s41467-025-64515-7 (via europepmc_accession, verified=False) vs 1 curated: ['https://www.nature.com/articles/s41467-022-30637-5#data-availability']
- `PRJEB58018` found=10.2807/1560-7917.es.2026.31.1.2500378 (via europepmc_accession, verified=False) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC9808319/']
- `PRJNA395086` found=10.1128/msystems.00194-21 (via europepmc_accession, verified=True) vs 1 curated: ['https://academic.oup.com/jac/article/77/2/356/6403927']
- `PRJNA626430` found=10.1038/s41564-021-00879-y (via europepmc_accession, verified=True) vs 1 curated: ['https://pmc.ncbi.nlm.nih.gov/articles/PMC10433420/']
- `PRJNA246471` found=10.1128/aac.00464-16 (via europepmc_accession, verified=True) vs 1 curated: ['https://journals.asm.org/doi/10.1128/aac.00464-16 ; https://journals.asm.org/doi/full/10.1128/aac.04292-14?rfr_dat=cr_pub++0pubmed&url_ver=Z39.88-2003&rfr_id=ori%3Arid%3Acrossref.org']
- `PRJEB19322` found=10.1099/mgen.0.000703 (via europepmc_accession, verified=nan) vs 1 curated: ['https://www.medrxiv.org/content/10.1101/2025.06.28.25330253v1.full; https://pathogen.watch/collection/klebnet-neonatal-sepsis']

## Abstained (not_found, with a curated link)

- `PRJEB37378` (n_candidates=1) curated=['https://journals.plos.org/plosntds/article?id=10.1371/journal.pntd.0012413']
- `PRJEB42462` (n_candidates=5) curated=['https://www.medrxiv.org/content/10.1101/2025.06.28.25330253v1.full.pdf', 'https://www.medrxiv.org/content/10.1101/2025.06.28.25330253v1.full; https://pathogen.watch/collection/klebnet-neonatal-sepsis']
- `PRJEB28400` (n_candidates=1) curated=['https://www.thelancet.com/journals/lanmic/article/PIIS2666-5247(22)00181-1/fulltext?uuid=uuid%3Ab233fac2-1f11-4aa3-9653-d84ae67c113e']
- `PRJNA271899` (n_candidates=2) curated=['https://genomemedicine.biomedcentral.com/articles/10.1186/s13073-022-01040-y']
- `PRJNA845975` (n_candidates=0) curated=['https://www.medrxiv.org/content/10.1101/2025.06.11.25329357v1.full']
- `PRJNA777643` (n_candidates=1) curated=['https://pmc.ncbi.nlm.nih.gov/articles/PMC10564454/#sa1']
- `PRJNA549322` (n_candidates=11) curated=['https://pmc.ncbi.nlm.nih.gov/articles/PMC10200298/']
- `PRJNA789336` (n_candidates=1) curated=['https://link.springer.com/article/10.1007/s10096-022-04425-4']
- `PRJEB22252` (n_candidates=3) curated=['https://www.nature.com/articles/s41467-021-26041-0']
- `PRJEB6574` (n_candidates=0) curated=['https://pathogen.watch/collection/klebnet-neonatal-sepsis']
- `PRJEB1563` (n_candidates=1) curated=['https://www.sciencedirect.com/science/article/pii/S1438422117301121']
- `PRJEB21277` (n_candidates=1) curated=['https://www.sciencedirect.com/science/article/pii/S016041202100091X?via%3Dihub#t0010']
- `PRJNA982859` (n_candidates=0) curated=['https://pubmed.ncbi.nlm.nih.gov/38819130/']
- `PRJNA396774` (n_candidates=4) curated=['https://www.nature.com/articles/s41598-017-18972-w']
- `PRJNA767944` (n_candidates=0) curated=['https://journals.asm.org/doi/10.1128/msphere.00143-22']
- `PRJEB22890` (n_candidates=0) curated=['https://pubmed.ncbi.nlm.nih.gov/33188415/']
- `PRJNA564992` (n_candidates=1) curated=['https://academic.oup.com/jac/article/76/11/2815/6347675']
- `PRJNA351909` (n_candidates=5) curated=['https://www.nature.com/articles/s41467-022-30717-6 |. https://pmc.ncbi.nlm.nih.gov/articles/PMC5850561/']
- `PRJEB20799` (n_candidates=0) curated=['https://pathogen.watch/collection/klebnet-neonatal-sepsis']
- `PRJNA398288` (n_candidates=3) curated=['https://academic.oup.com/jac/article/73/3/634/4745835#supplementary-data']

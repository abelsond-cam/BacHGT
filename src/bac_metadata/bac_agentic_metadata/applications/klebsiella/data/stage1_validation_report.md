# Stage 1 validation summary

## Umbrella accessions (one accession aggregating many substudies)
Flagged via distinct child studies; one 'best paper' cannot describe these. `PRJEB74192` (One Health Norway) is the canonical training case.
```
study_accession paper_short_title  n_child_studies  ena_taxon_samples
     PRJEB74192 One Health Norway                9               3261
```

## Sizing (curation holding vs ENA project taxon count, per curation row)
`ena_taxon_samples` is the project's Klebsiella size (paper-coverage denominator); `isolates_in_study` is what the curation covered. `coverage = isolates / ena_taxon`.
- rows compared: 146
- median coverage: 1.00
- whole-project (coverage >= 0.9): 75%; subsample (< 0.5): 7%
- anomalies (holding > project taxon count): 37

### Lowest coverage (most subsampled)
```
                 paper_short_title  isolates_in_study  ena_taxon_samples_sum  coverage
                  cdc_surveillance              322.0                  12456  0.025851
                  ghana_one_health              573.0                   6354  0.090179
                       CCRE survey              313.0                   2904  0.107782
cpe_surveillance_five_us_hospitals              104.0                    730  0.142466
                      ghru_nigeria              139.0                    778  0.178663
                     CC14 KP clone              457.0                   1820  0.251099
                 melb_surveillance               16.0                     58  0.275862
                              None              293.0                    948  0.309072
                      vetinary_fda              204.0                    630  0.323810
             japanese_surveillance              168.0                    388  0.432990
```

### Anomalies — holding exceeds ENA project taxon count
```
                          paper_short_title  isolates_in_study  ena_taxon_samples_sum
                                 icu_hannoi             3153.0                    745
                               thailand_cpe              747.0                    707
                             melb_superbugs              190.0                      0
                                    CRE_NYC              437.0                    315
 malawi_ceftriaxone_esbl_enterobacteriaceae             1485.0                    238
                      portuguese_klebsiella              509.0                    508
       columbia_irvine_polymyxin_resistance              388.0                    340
bangladesh_child_heatlh_research_foundation              599.0                    567
                 capsule_depolymerase_study              422.0                    185
          klebsiella_diversity_in_Argentina              932.0                    926
                             baby_biomes_uk              805.0                    237
                      uganda_and_malawi_amr             6508.0                   1603
                        pakistan_klebsiella              227.0                    221
                australian_cpe_surveillance             1252.0                    456
                            chigago_cpe_ndm              486.0                    452
                 singapore_cpe_surveillance              532.0                    375
                          nevada_health_lab             1345.0                    313
                     dutch_cpe_surveillance              307.0                     80
                                       None              160.0                    143
                                       None              356.0                     44
                         China colonisation              241.0                      0
                   Malawi_neonatal_outbreak              898.0                      2
                             Dutch plasmids              479.0                    144
                    Norway population study              391.0                    155
                Desinfectant susceptibility              241.0                    184
                               Thailand_CRE              200.0                    187
                             polymixin B KP              275.0                    237
   cephalosporin Autralia, NZ and Singapore              294.0                     36
                            Netherlands CPK              479.0                    412
                               Viet Nam MDR             1316.0                    713
                          India KP antigens             1072.0                    930
                   India_enterobacteriaceae              982.0                     14
                   India_enterobacteriaceae              608.0                     14
                                 Swiss_kleb              272.0                    261
                           CUH_longitudinal              464.0                    229
                           Manchester_TRACE              569.0                    537
                         Philipines_network             1290.0                    365
```

## Completeness
_parsed_per_project not read (no credentials) — sizing only._

# `metadata_v2` — README

*Snapshot: 2026-06-02 · `metadata_v2_all_samples_and_columns.tsv` · 86,398 rows × 505 columns*

*(505 columns span: ENA Portal metadata, NCBI Datasets assembly info, Kleborate v3.2.4 typing
(species/MLST/virulence/AMR/Kaptive/wzi), ISEScan IS-family counts, CheckM2 QC, Bakta annotation
stats, parsed/categorised clinical metadata, file-path pointers, cohort flags, and
`EBI_*_AST` binary truth values for 22 antibiotics (BacPredict step 9).)*

Authoritative description of the Klebsiella **metadata_v2** table for BacHGT, BacPredict, and
external collaborators. Read this before consuming the table — it explains how rows are keyed,
what each flag means, where each column came from, and what to do if the data needs to change.

The canonical TSV lives on HPC at:
```
/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv
```
*(That's `<project_k>/david/final/`. See `~/.claude/hpc_storage_overview.md` for storage roots.)*

---

## 1. The cohort

- **~90,000** Klebsiella-annotated assemblies were curated from **All The Bacteria (ATB)** as the
  starting set (downloaded by `bac_data` via the bakrep + ENA pipelines).
- Extra QC was performed with **CheckM2** and specialist scripts. The final QC whitelist for the
  short-read cohort lives in the QC Excel (`klebsiella_qc_NCTC.xlsx`, sheet `FINAL_LIST`), now at
  `<project_k>/david/raw/klebsiella_qc_NCTC.xlsx` on HPC (migrated 2026-06-03; a safety copy is
  preserved on the Weimann shared OneDrive).
- In addition to ATB, **long-read assemblies from RefSeq** were downloaded plus the **NCTC**
  historic Klebs set (`is_nctc=97`).
- Species had to match Klebsiella via **Kleborate v3.2.4**. The Kp species complex (KPSC) covers
  the 7 phylogroups Kp1-Kp7 per Long et al. 2017:
  - **Kp1** — *Klebsiella pneumoniae*
  - **Kp2 / Kp4** — *K. quasipneumoniae* subsp. similipneumoniae / quasipneumoniae
  - **Kp3** — *K. variicola* subsp. *variicola*
  - **Kp5** — *K. variicola* subsp. *tropica* (also known as *K. tropica*)
  - **Kp6** — *K. quasivariicola*
  - **Kp7** — *K. africana*

  Implementation rule (`_is_kpsc` in `merge_kleborate_into_metadata_v2.py`): species name
  **contains** `variicola` OR **contains** `quasi`, OR starts with *Klebsiella pneumoniae* /
  *africana* / *tropica*. Catches all 7 phylogroups including hyphenated subspecies.

  v2 `is_kpsc=True` = **79,153**; curated final list `kpsc_final_list=True` = **79,153**
  (orphan additive rule recovers RefSeq complete-genomes whose CheckM2 was missing — see §3).
- **~7,246** non-KPSC Klebsiella (e.g. *K. oxytoca*, *K. aerogenes*) are present in v2 but **not**
  in `is_kpsc`. They were not put through the full extra QC.

**Snapshot counts** (2026-06-02 — post `rebuild_v2.sh` with the column-rename + kpsc-additive + is_variant_called cascade):

| | rows |
|---|---:|
| Total v2 rows | **86,398** |
| `is_kpsc=True` | 79,153 |
| `kpsc_final_list=True` | **79,153** |
| `is_variant_called=True` *(NEW)* | **76,574** |
| `lra_final_list=True` | **5,519** |
| `is_complete=True` | 4,017 |
| `is_hybrid=True` | 2,618 |
| `is_reference_genome=True` | **1,777** (1,681 KPSC + 96 non-KPSC) |
| `is_nctc=True` | 97 |
| `is_mgh78578=True` | 1 |
| Paired (LR + SR partner) | 3,075 |
| Orphan LR-only | 2,581 |
| SR-only | 80,742 |

---

## 2. Structure of the table — **the important bit for most users**

Each v2 row refers to **one biosample**. The `Sample` column resolves as:

- **Long-read assembly** when one exists (the LR is the canonical row key for that isolate).
  Long-read `Sample` is a **versioned** NCBI assembly accession (`GCF_…\.\d+` for RefSeq,
  `GCA_…\.\d+` for GenBank). Zero bare GC accessions. Most are `.1` (5,444 of 5,771);
  `.2`/`.3`/`.4` appear when NCBI has reissued an assembly (327 rows, mostly `.2`).
- **Short-read BioSample** otherwise (e.g. `SAMN…`, `SAME…`, `SAMD…`). These are SR-only rows.

### Quick column families

Full lists + descriptions in §4 and §5.

- **SR columns** — refer to the short-read partner:
  `sample_accession`, `run_accession`, `sr_run_accession`, `fastq_ftp`, `fastq_md5`,
  `sr_assembly_file`, `sr_gff_file`, `instrument_platform`, `instrument_model`,
  `study_accession`, `secondary_sample_accession`, `sr_biosample`.
- **LR columns** — refer to the long-read assembly:
  `lra_gca`, `lra_gcf`, `lr_assembly_file`, `lr_gff_file`, `lr_run_accession`,
  `lr_instrument_platform`, `lr_instrument_model`, `level`, `library_class`,
  `scoring_accession`, `checkm2_*`.

### Three row archetypes

| Archetype | `Sample` is… | rows | SR columns | LR columns | `sr_biosample` |
|---|---|---:|---|---|---|
| **SR-only** | a BioSample (`SAMN…`/`SAME…`/`SAMD…`) | **80,742** | filled | empty | empty |
| **Paired LR+SR** | an LR accession (`GCF_…`/`GCA_…`) | **3,075** | filled (SR partner's values copied in) | filled | original SR BioSample |
| **LR-only / orphan LRA** | an LR accession (`GCF_…`/`GCA_…`) | **2,581** | empty | filled | empty |

Per-archetype KPSC and variant-call breakdown:

| Archetype | rows | `is_kpsc=T` | `kpsc_final_list=T` | `is_variant_called=T` |
|---|---:|---:|---:|---:|
| SR-only | 80,742 | 73,754 | 73,754 | 73,754 |
| Paired LR+SR | 3,075 | 2,820 | 2,820 | 2,820 |
| Orphan LR-only | 2,581 | 2,579 | 2,579 | **0** *(no SR data → no variant calls)* |

Sample-prefix breakdown: SAME 38,913 / SAMN 38,542 / GCF_ 4,363 / SAMD 3,287 / GCA_ 1,293.

---

## 3. Key flags

| Flag | Definition | Count |
|---|---|---:|
| `is_kpsc` | Kp species complex (Kp1-Kp7): species **contains** `variicola` OR `quasi`, OR starts with *K. pneumoniae* / *africana* / *tropica*. See §1. | **79,153** |
| `kpsc_final_list` | Curated KPSC cohort. **Additive rule** (post-2026-06-03 cascade): paired LR rows = `kpsc_v1 OR (lra_final_list ∧ is_kpsc)` — preserves v1's SR-side QC pass even if LR fails CheckM2. Orphan LR rows = `is_kpsc ∧ (kpsc_v1 OR lra_final_list)` — requires Kleborate-confirmed KPSC then admits if either v1 had it on the curated list OR the LR passed CheckM2 (recovers ~99 RefSeq complete-genomes whose CheckM2 score was missing). SR-only rows = unchanged from v1. | **79,153** |
| `is_variant_called` *(NEW)* | True iff the row has SR data that passed v1's KPSC QC (the cohort variant calling was performed against). Computed as `(NOT orphan LRA) AND v1's kpsc_final_list=True`. Always False on orphan LRA rows. | **76,574** |
| `is_mgh78578` | The historic *K. pneumoniae* MGH 78578 reference used for variant calling (Sample `GCF_000016305.1`, ST38). **Complete but NOT hybrid-assembled** → not in `is_reference_genome` | 1 |
| `lra_final_list` | LR assemblies passing CheckM2 (completeness ≥ 99.0%, contamination ≤ 5.0%, genome size ≤ max RefSeq observed). Derivation: [`build_lra_set.py:120`](../bac_data/lr_data/build_lra_set.py#L120) | 5,519 |
| `is_complete` | NCBI `assembly_level == "Complete Genome"` (chromosome + plasmids closed/circular) | 4,017 |
| `is_hybrid` | NCBI `library_class == "hybrid"` — **any LR sequenced with both long and short read tech**. Includes drafts; NOT gated on `is_complete`. Derivation: [`build_lra_set.py:123`](../bac_data/lr_data/build_lra_set.py#L123) | 2,618 |
| `is_reference_genome` | **Strict** intersection: `is_complete ∧ is_hybrid ∧ Sample starts with GCF_` (RefSeq). Highest-confidence reference set. Derivation: [`build_lra_set.py:126-127`](../bac_data/lr_data/build_lra_set.py#L126-L127) | 1,777 |
| `is_nctc` | Historic NCTC Klebs assembly | 97 |

**Important nuances:**

- `is_hybrid` does **not** require `is_complete`. A draft assembly built with hybrid technology is
  `is_hybrid=True`, `is_complete=False`, `is_reference_genome=False`.
- `is_reference_genome` requires **RefSeq** (`GCF_` prefix) — GenBank-only hybrids (`GCA_`) are
  excluded even if complete.
- `is_mgh78578` is `is_complete=True` but `is_hybrid=False`, so it is **not** a reference genome
  under this scheme.
- `is_reference_genome` species composition: 1,681 KPSC + 96 non-KPSC. Non-KPSC includes
  *K. aerogenes* (31), *K. michiganensis* (21), *K. oxytoca* (15), *K. grimontii* (12), and a tail
  of other Klebsiella species (~14 more, ≤ 3 each).

---

## 4. Short-read assembly columns

Populated on SR-only rows and paired rows (copied from the SR partner during the v2 build).
Empty on LR-only orphan rows.

| Column | Source | Notes |
|---|---|---|
| `sample_accession` | ENA Portal | BioSample (SAMN/SAME/SAMD) |
| `run_accession` | ENA Portal | SR Illumina run accession. On paired rows this is the SR partner's run (the LR run lives in `lr_run_accession`). |
| `sr_run_accession` | renamed from v1 `related_sr_accession` | Mirror of the SR run on paired rows for unambiguous SR pickup |
| `fastq_ftp`, `fastq_md5` | ENA Portal | SR fastq URLs + checksums. ⚠ NOT copied onto the ~957 merged paired rows during the SR↔RefSeq merge — those rows have `run_accession` but no `fastq_ftp`. Resolve via the ENA API from `run_accession` if needed. |
| `sr_assembly_file` | `add_paths_gff_fna_to_metadata.py` | SR assembly FASTA path on HPC. ⚠ Renamed from legacy `assembly_file` in `build_metadata_v2.py`'s `RENAMED_COLUMNS` (2026-06-02); current on-disk v2 TSV still uses `assembly_file` until next `rebuild_v2.sh` run. |
| `sr_gff_file` | `add_paths_gff_fna_to_metadata.py` | SR GFF path. ⚠ Renamed from legacy `gff_file` (same rename pass). |
| `instrument_platform`, `instrument_model` | ENA Portal | SR sequencer info |
| `study_accession`, `secondary_sample_accession` | ENA Portal | Standard ENA accessions |

The LR↔SR pairing logic lives in [`build_metadata_v2.py`](pp/build_metadata_v2.py) — see
`_pair_refseq_sr` and the merge of 957 SR+RefSeq pairs at lines 565-589.

---

## 5. Long-read assembly columns

Populated on `lra_final_list=True` rows (and on the LR-only orphan rows).

| Column | Source | Notes |
|---|---|---|
| `lra_gca`, `lra_gcf` | NCBI Datasets | The LR assembly's GCA / GCF accessions (versioned). One of these is the row's `Sample`. |
| `lr_assembly_file` | `add_paths_gff_fna_to_metadata.py --mode lra` | LR FASTA path on HPC. ⚠ Renamed from legacy `lra_assembly_file` in `build_metadata_v2.py`'s `RENAMED_COLUMNS` (2026-06-02); current on-disk v2 TSV still uses `lra_assembly_file` until next `rebuild_v2.sh` run. **Path-relative rewrite (drop `<project_k>` prefix) is still pending — see §12.** |
| `lr_gff_file` | `add_paths_gff_fna_to_metadata.py --mode lra` | LR GFF path. ⚠ Renamed from legacy `lra_gff_file` (same rename pass). Path-relative rewrite still pending. |
| `lr_run_accession` | ENA / NCBI Datasets | LR run accession (ONT/PacBio); separate from SR's `run_accession` |
| `lr_instrument_platform`, `lr_instrument_model` | ENA / NCBI Datasets | LR sequencer info |
| `level` | NCBI Datasets | NCBI `assembly_level` (used to derive `is_complete`) |
| `library_class` | NCBI Datasets (derived) | hybrid / long-read / short-read (used to derive `is_hybrid`) |
| `scoring_accession` | `build_lra_discovery.py` | The assembly used for CheckM2 scoring (GCF preferred, else GCA) |
| `checkm2_completeness`, `checkm2_contamination`, `checkm2_genome_size`, `checkm2_*` (~13 cols) | `bac_data/checkm2/` | CheckM2 v1.x results on the LR FASTA |

---

## 6. Kleborate columns

All from **Kleborate v3.2.4** run on the LR assembly via
[`run_kleborate_lra.py`](../bac_kleborate/run_kleborate_lra.py) with `-p kpsc` preset, then merged
into v2 by [`merge_kleborate_into_metadata_v2.py`](pp/merge_kleborate_into_metadata_v2.py).

| Column | Notes |
|---|---|
| `species` (lowercase) | Kleborate species call |
| `scientific_name` | mirror of `species` |
| `ST` | Kp 7-locus MLST sequence type (e.g. `ST258`) |
| `gapA`, `infB`, `mdh`, `pgi`, `phoE`, `rpoB`, `tonB` | MLST allele numbers |
| `Sublineage`, `Clonal group`, `LINcode`, `Phylogroup` | **From v1 QC Excel LINcode sheet (Pasteur BIGSdb LIN-typing)** — NOT Kleborate v3 output. See §12 note on the 124-row gap. |
| `K_locus`, `K_type`, `K_locus_confidence`, `K_Missing_expected_genes` | Kaptive K typing |
| `O_locus`, `O_type`, `O_locus_confidence`, `O_Missing_expected_genes` | Kaptive O typing |
| `wzi` | wzi-type K-antigen prediction |
| Virulence MLSTs + loci | `YbST`, `CbST`, `AbST`, `SmST`, `RmST`, `Yersiniabactin`/`Colibactin`/`Aerobactin`/`Salmochelin`/`RmpADC`, per-locus genes (`ybt*`, `clb*`, `iuc*`, `iro*`, `rmp*`, `rmpA2`), `virulence_score`, `spurious_virulence_hits` |
| AMR — acquired | `<class>_acquired` (AGly, Col, Fcyn, Flq, Gly, MLS, Phe, Rif, Sul, Tet, Tgc, Tmt, Bla, Bla_inhR, Bla_ESBL, Bla_ESBL_inhR, Bla_Carb) |
| AMR — chromosomal + mutations | `Bla_chr`, `SHV_mutations`, `Omp_mutations`, `Col_mutations`, `Flq_mutations`, `truncated_resistance_hits`, `spurious_resistance_hits` |
| AMR — scores + predictions | `resistance_score`, `num_resistance_classes`, `num_resistance_genes`, `Ciprofloxacin_prediction`, `Ciprofloxacin_profile`, `Ciprofloxacin_MIC_prediction` |

**Parsing helpers** — virulence and AMR call strings can be parsed with
[`src/bac_kleborate/parsing.py`](../bac_kleborate/parsing.py) (Kleborate's `;`-separated /
`-`-no-hit syntax → structured tokens).

> **Note:** the Kleborate Sublineage call is missing from **~124** rows — 121 newly-added orphan
> LRA + Norway rows, 3 SR with a v1 LINcode-sheet gap. Closing this requires the Pasteur BIGSdb
> LIN-typing service (Kleborate v3.2.4 does **not** include a LIN-coding module). Tracked in §12.

---

## 7. Bakta annotation columns

Bakta annotation outputs from the bakrep pipeline (`<project_k>/bakrep/`), joined into v1 via
[`qc_add_metadata.py`](pp/qc_add_metadata.py) (`bakrep` sheet of the QC Excel) and carried into v2.

| Column | Notes |
|---|---|
| `bakta.genome.genus` | Bakta-classified genus |
| `bakta.genome.species` | Bakta-classified species |
| `bakta.genome.strain` | Bakta-classified strain identifier |
| `bakta.stats.no_sequences` | Number of contigs |
| `bakta.stats.size` | Total genome size (bp) |
| `bakta.stats.gc` | GC content |
| `bakta.stats.n_ratio` | Fraction of N bases |
| `bakta.stats.n50` | Assembly N50 |
| `bakta.stats.coding_ratio` | Coding density |
| `bakta_gbff_downloaded` | Flag — whether the Bakta `.gbff` is on disk for the SR row |

---

## 8. ISEScan IS-family columns (`IS_*`)

Per-genome IS-family copy counts from **ISEScan**, run on LR assemblies via
[`run_isescan_lra.py`](../bac_isescan/run_isescan_lra.py) and merged into v2 by
[`merge_isescan_into_metadata_v2.py`](pp/merge_isescan_into_metadata_v2.py).

- One `IS_<family>` column per family detected across the LRA cohort (e.g. `IS_IS1`, `IS_IS3`,
  `IS_IS5`, `IS_IS6`, `IS_IS21`, `IS_IS66`, `IS_IS110`, `IS_IS200/IS605`, `IS_ISKRA4`, … ~24 families).
- Value = copy count from ISEScan; `0` on matched LR rows with no detection of that family;
  `NaN` on non-LR rows.

---

## 9. Paired long+short read subset

Of the LR rows in `lra_final_list` (and within those, `is_complete` / `is_hybrid` /
`is_reference_genome`), a subset have **pre-curated short-read partner assemblies** from ATB.
The paired cohort in `paired_index.tsv` totals **2,919** rows (snapshot from G.4.5). After the
2026-06-02 cascade rebuild, the equivalent v2 archetype count is **3,075** — `paired_index.tsv`
predates the latest Norway-pair merger and is mildly stale; re-run `build_paired_features.py`
to refresh.

*Note: although `is_hybrid` and `is_reference_genome` rows were all sequenced with combined SR+LR
data, the SR fastq/assembly is **not always retained** as a separate paired SR row in ATB.*

### Quick join file — `paired_index.tsv`

Shortcut for working with the paired cohort:

```
<project_k>/david/processed/complete_vs_sr_genomes/paired_index.tsv
```

23 columns covering LR-side identity + QC + flags, keyed by both `lra_sample` and
`sr_biosample`. Most useful columns:

| Column | Meaning |
|---|---|
| `lra_sample` | LR-side Sample (`GCF_…` / `GCA_…`, versioned) — joins to v2 `Sample` |
| `sr_biosample` | SR partner's BioSample (`SAMN`/`SAME`/`SAMD`) — joins to v2 `sr_biosample` |
| `lra_gca`, `lra_gcf` | LR assembly accessions (versioned) |
| `lra_assembly_level` | NCBI level (`Complete Genome` / `Chromosome` / `Scaffold` / `Contig`) |
| `lra_tier` | `GCF` (RefSeq) vs `GCA` (GenBank) |
| `lra_library_class` | `hybrid` / `short_only` / `long_only` / `unknown` |
| `lra_is_complete`, `lra_is_hybrid`, `lra_is_reference_genome` | LR cohort flags |
| `lra_checkm2_*` | CheckM2 QC metrics on the LR assembly |
| `lra_species`, `lra_is_kpsc`, `kpsc_final_list` | LR-side species + KPSC membership |

### LR-side breakdown of the 2,919 paired pairs

**By assembly quality** (`lra_assembly_level`):

| Level | Pairs |
|---|---:|
| Complete Genome | **1,574** (54%) |
| Contig (draft) | 1,205 (41%) |
| Chromosome | 91 |
| Scaffold | 49 |

**By library class** (`lra_library_class`):

| Class | Pairs |
|---|---:|
| `hybrid` | **1,546** (53%) |
| `short_only` | 807 |
| `long_only` | 412 |
| `unknown` | 154 |

**By cohort flags:**

| Subset | Pairs | Definition |
|---|---:|---|
| `lra_is_complete=True` | 1,574 | NCBI Complete Genome |
| `lra_is_hybrid=True` | 1,546 | hybrid library |
| Complete ∧ Hybrid (any tier) | 1,093 | LR closed AND hybrid-assembled |
| `lra_is_reference_genome=True` | **748** | complete ∧ hybrid ∧ GCF — highest-confidence reference subset |
| **None of complete/hybrid/reference** | **892** (31%) | draft LR paired with SR — useful for LR-vs-SR comparison but not a reference |

**By tier:**

| Tier | Pairs |
|---|---:|
| `GCF` (RefSeq) | 1,748 |
| `GCA` (GenBank) | 1,171 |

### Companion paired artefacts (same directory)

- `lra_features.tsv` — 2,919 × 115 — LR-side typing + IS + AMR features extracted from v2.
- `sr_features.tsv` — 2,523 × 172 — SR-side mirror (superset; 109 cols overlap with LR; ~410 SR
  rows have no extant LR partner).
- `sr_shadow_for_lra.tsv` — frozen SR-side typing snapshot keyed on `sr_biosample`, used so v2's
  overwrite of LR-side fields doesn't lose the SR-side state.

Consumed by analyses in [`src/bac_complete_genomes/`](../bac_complete_genomes/).

---

## 10. Curated clinical metadata

The four primary fields curated for research, processed in
[`metadata_curation.py`](pp/metadata_curation.py):

`collection_date` · `country` · `host` · `isolation_source`

Each goes through (1) **parse** (regex + lookup tables for spelling, language, synonyms — e.g.
*Homo sapiens* → `"human"`) and then (2) **categorise**.

### Parsed columns (cleaned canonical strings)

`country_parsed` · `host_parsed` · `isolation_source_parsed` · `collection_date_parsed` ·
`collection_year` ⚠ *(renamed from legacy `year_parsed` in `build_metadata_v2.py`'s `RENAMED_COLUMNS`,
2026-06-02; current on-disk v2 still has `year_parsed` until next `rebuild_v2.sh`. `metadata_curation.py`
now also emits `collection_year` directly for future v1 rebuilds. The legacy `Collection.Year` v1 column
is unrelated and unchanged.)*

### Category columns (categorical buckets)

#### `region` (WHO/geographic regions)

| Region | Rows |
|---|---:|
| W. Europe | 25,287 |
| N. America | 19,177 |
| E. Asia | 15,119 |
| Africa | 7,062 |
| M. East, Central Asia | 4,967 |
| Oceania | 3,018 |
| Central & S. America | 2,787 |
| E. Europe | 2,451 |
| (NaN) | 6,650 |

#### `host_category`

| Category | Rows |
|---|---:|
| human | 66,351 |
| wastewater & water | 2,129 |
| grazing livestock & horses | 1,350 |
| poultry livestock | 598 |
| domestic animals | 558 |
| vegetable, plant or soil | 466 |
| clinical environment or surface | 409 |
| meat products | 405 |
| wild animals | 307 |
| insect | 157 |
| wild birds | 46 |
| (NaN) | 13,742 |

#### `isolation_source_category`

| Category | Rows |
|---|---:|
| blood | 13,339 |
| urine | 13,100 |
| faeces & rectal swabs | 12,702 |
| lower respiratory, endotracheal | 6,821 |
| wound & pus, abscess, surgical drain, body tissue, bone, biopsy | 3,175 |
| wastewater & water | 2,129 |
| invasive gut & organs | 1,160 |
| body fluid (ascites / peritoneal / pleural) | 636 |
| vegetable, plant or soil | 466 |
| urinary catheter | 438 |
| upper airway | 423 |
| clinical environment or surface | 409 |
| meat products | 405 |
| skin swabs (skin, groin, vaginal, genital, eye, ear) | 303 |
| insect | 157 |
| (NaN) | 30,760

### Category composition notes

A few categories are heterogeneous — worth knowing what each rolls up:

- **`wound & pus, abscess, surgical drain, body tissue, bone, biopsy`** — wound, pus, abscess,
  surgical drain, bone/biopsy tissue. **Liver abscess** lands here (66/67 rows).
- **`body fluid (ascites / peritoneal / pleural)`** — separate from wound. **CSF** lands here
  (24/25 rows; not in wound).
- **`urine`** (13,100) vs **`urinary catheter`** (438) — separate categories. The catheter
  bucket is matched via `(?=.*catheter)(?=.*urin)` regex in `metadata_curation.py:1525`.
- **`lower respiratory, endotracheal`** — tracheal aspirates, tracheostomy, sputum, bronchial
  lavage. **`upper airway`** is a separate category (423 rows).
- **`skin swabs (skin, groin, vaginal, genital, eye, ear)`** — dedicated category for surface
  swabs; not in wound.

### Study-level columns

Annotated manually during study review (see §11):

- **`amr_study`** — what the study selected for:

  | Value | Rows |
  |---|---:|
  | `AMR` | 41,056 |
  | (NaN) | 19,121 |
  | `Surveillance` | 16,447 |
  | `AMR plus control` | 9,894 |

- **`study_setting`** — where the samples were collected:

  | Value | Rows |
  |---|---:|
  | `Hospital` | 51,245 |
  | (NaN) | 23,688 |
  | `Mixed` | 7,883 |
  | `Community` | 3,702 |

- **`study_accession`, `secondary_study_accession`, `study_alias`, `study_title`** — ENA-side
  identifiers and titles for the source study; carried from the ENA Portal collation step.

---

## 11. How the metadata was collected + study-level annotation

For the ~90,000 ATB samples, **ENA project accessions** were screened: studies with > 130
samples were reviewed manually (nearly 75% of the assembly set). Reviewed studies had:

- Number of Klebsiella samples in the study (vs other species) checked.
- Country, host, isolation source, collection dates verified against the publication / metadata.
- **`amr_study`** — what the study selected for (AMR / `AMR plus control` / Surveillance / NaN),
  based on whether sequencing was limited to AMR-resistant samples (typically 3rd-gen cephalosporins
  or carbapenems detected by AST or ARG PCR). Annotated on ~80% of reviewed studies. See §10 counts.
- **`study_setting`** — Hospital / Community / Mixed (current column; see §10 counts).
- For studies without per-sample metadata: if all samples were from one country, isolation
  source, host, or within a two-year window, the key variables were back-filled from that
  study-level assumption.

**Sources** (per pipeline stage):

| Source | Used for | Joined in |
|---|---|---|
| ENA Portal API + ready_to_merge patches | SR sample/run metadata, fastq URLs, study fields | [`metadata_collation.py`](pp/metadata_collation.py) |
| NCBI Datasets API | RefSeq/GenBank LR assemblies, NCTC, assembly_level, library_class | [`bac_data/lr_data/`](../bac_data/lr_data/) |
| Bakrep | Bakta annotation stats (`bakta.*`) | [`qc_add_metadata.py`](pp/qc_add_metadata.py) (`bakrep` sheet of QC Excel) |
| QC Excel `LINcode` sheet (Pasteur BIGSdb) | `Sublineage`, `LINcode`, `Clonal group`, `Phylogroup` | [`qc_add_metadata.py`](pp/qc_add_metadata.py) |
| Kleborate v3.2.4 (run on LR) | Species, MLST, virulence, AMR, Kaptive, wzi | [`merge_kleborate_into_metadata_v2.py`](pp/merge_kleborate_into_metadata_v2.py) |
| ISEScan (run on LR) | `IS_<family>` copy counts | [`merge_isescan_into_metadata_v2.py`](pp/merge_isescan_into_metadata_v2.py) |
| Google Sheet (study-level review) | `amr_study`, `study_setting` | [`metadata_curation.py`](pp/metadata_curation.py) |
| CheckM2 (run on LR) | `checkm2_*` QC stats; cohort gate | [`bac_data/checkm2/`](../bac_data/checkm2/) |

---

## 12. Known issues + open To Do

### Known data issues

- **`Sublineage` missing on 124 KPSC rows** (121 LRA orphan/Norway + 3 SR with v1 LINcode-sheet
  gaps). Kleborate v3.2.4 does not emit `Sublineage`/`LINcode` — those came from a separate
  Pasteur BIGSdb LIN-typing layer in v1. Closing this requires running BIGSdb LIN-typing or a
  manual LIN-typing pass. **Not currently scheduled.**
- **~957 paired rows lack `fastq_ftp`/`fastq_md5`** even though `run_accession` is populated.
  The SR↔RefSeq merge in [`build_metadata_v2.py:570-574`](pp/build_metadata_v2.py#L570-L574)
  doesn't copy fastq columns onto the merged row. Workaround: resolve via the ENA API from
  `run_accession`.

### Code / schema cleanups (deferred — to apply when v2 is next rebuilt)

- ~~**Rename** `year_parsed` → `collection_year`~~ ✅ **Applied 2026-06-02** — column gone from
  v2 on disk; `metadata_curation.py` forward-fix emits `collection_year` directly.
- ~~**Rename** `gff_file` → `sr_gff_file` and `assembly_file` → `sr_assembly_file`~~ ✅ **Applied 2026-06-02**.
- ~~**Rename** `lra_gff_file` → `lr_gff_file` and `lra_assembly_file` → `lr_assembly_file`~~
  ✅ **Applied 2026-06-02** — cascade-internal scripts updated; 20 downstream consumer files
  swept ([`run_kleborate_lra.py`](../bac_kleborate/run_kleborate_lra.py), [`run_isescan_lra.py`](../bac_isescan/run_isescan_lra.py),
  [`panaroo_run_strain.py`](../bac_panaroo/run_panaroo/panaroo_run_strain.py),
  [`run_genomad.py`](../bac_genomad/run_genomad.py), bac_data/lr_data/* scripts).
- **Path-relative rewrite** *(groundwork landed 2026-06-02; activation deferred)* — helper
  module [`src/bac_metadata/path_resolve.py`](path_resolve.py) provides
  `resolve_v2_path(value, root=None)` (back-compat: absolute paths pass through unchanged) +
  `to_relative_v2_path(absolute, root=None)`. The cascade's `add_paths_gff_fna --mode lra` step
  now strips the `<project_k>` prefix from `lr_*` / `sr_*` path columns at write time. **NOT yet
  activated** because that requires updating the 7 consumers that open these paths
  (`run_kleborate_lra.py`, `run_isescan_lra.py`, `panaroo_run_strain.py`, `run_genomad.py`,
  `stage_lra_extras_for_tf.py`, `download_lra_gffs.py`, `stage_sr_for_related_lr.py`) to call
  `resolve_v2_path`. **Trigger activation by**: (1) sweeping the 7 consumers, (2) re-running
  `rebuild_v2.sh` to lay down relative paths. Without (1), the rebuild would produce relative
  paths that consumers can't open directly.
- ~~**Downstream consumer sweep**~~ ✅ **Applied 2026-06-02** — 20 BacHGT files updated via
  word-boundary regex: bac_kleborate, bac_isescan, bac_panaroo runners; bac_genomad; bac_data/lr_data
  staging + downloads; relevant slurm scripts + CLAUDE.mds. The v1-only readers
  ([`build_sr_shadow_for_lra.py`](pp/build_sr_shadow_for_lra.py),
  [`slim_metadata.py`](pp/slim_metadata.py),
  [`count_gff_features.py`](pp/count_gff_features.py),
  [`merge_gff_feature_counts_into_metadata.py`](pp/merge_gff_feature_counts_into_metadata.py),
  [`plot_completeness_after_curation_and_collation.py`](pp/plot_completeness_after_curation_and_collation.py))
  intentionally kept on legacy names — they read v1 directly and will follow when v1 is next rebuilt.
  BacPredict rename batch (7 files) handed off to that repo's agent.
- ~~**Drop** `is_complete_norway_genome`~~ ✅ **Applied 2026-06-02** — code complete + cascade
  re-run. Column is gone from v2 on disk; `merge_norway_pairs_into_v2.py` identifies Norway
  LR-extras from the integration TSV / Table S1 xlsx directly.
- **`is_refseq` legacy sweep** — six modules in `bac_isescan`, `bac_panaroo` (mgefinder
  selector), and `bac_ariba` still read the dropped `is_refseq` flag and the slimmed v1 TSV.
  Repoint by intent: cohort-arm → `lra_final_list`; reference-bucket → `is_reference_genome`;
  SR-exclusion → SR-side signal (e.g. `run_accession` populated).
- ~~**OneDrive decommission**~~ ✅ **Applied 2026-06-03** — QC Excel (`klebsiella_qc_NCTC.xlsx`,
  112 MB) rsync'd to `<project_k>/david/raw/`; metadata/ (481 MB: ENA TSVs + KlebNET-GSP CSV +
  study_level_metadata/ENA_projects/) rsync'd to `<project_k>/david/raw/metadata/`. Six obsolete
  OneDrive items deleted (`bakrep/`, `ISEscan/`, `archive/`, `atb_files/`, `klebs_snippy_pilot*`,
  `assembly_qc/`). Hardcoded OneDrive paths in ~25 code files repointed to the HPC equivalents
  (`/home/dca36/rds/.../david/...`); Google OAuth credentials intentionally kept on OneDrive
  (not pushed to shared HPC filesystem). Weimann shared-drive copies of `metadata/` and the QC
  Excel preserved as safety duplicates.

### Recently added: Bacformer-predicted AST + EBI ground-truth columns ✅ (2026-05-31)

Three column families per panel drug, populated by
[`merge_predicted_and_ebi_ast_into_metadata_v2.py`](pp/merge_predicted_and_ebi_ast_into_metadata_v2.py)
(rebuild_v2 step 9 — see §13).

| Column | Type | Source | Domain |
|---|---|---|---|
| `predicted_{drug}_AST` | str | BacPredict (Bacformer Stage C) | `"R"` / `"S"` / NaN |
| `predicted_{drug}_AST_prob` | float | same | `[0, 1]` or NaN |
| `EBI_{drug}_AST` | str | BacPredict's `binary_ast.csv` (curated EBI / publication AST), translated 1→R / 0→S | `"R"` / `"S"` / NaN |

**Panel (22 drugs):** `gentamicin, ceftazidime, meropenem, ciprofloxacin,
trimethoprim-sulfamethoxazole, amikacin, ceftriaxone, piperacillin-tazobactam,
cefoxitin, aztreonam, cefazolin, tobramycin, cefepime, imipenem, levofloxacin,
cefotaxime, cefuroxime, ampicillin-sulbactam, ertapenem, tetracycline,
azithromycin, colistin`. (Top-23 by EBI-labelled count, minus ampicillin —
intrinsic Kp resistance — and `pentizidone` — unverified drug-name parsing
artefact — plus colistin, the canonical chromosomal-mechanism bellwether.)

**Coverage.** `predicted_*` columns are populated for every `kpsc_final_list` row
that has an ESM-C embedding on disk; NaN otherwise (~5 % of `kpsc_final_list`
lacks embeddings as of the 2026-05-29 snapshot, per `find_missing_embeddings.py`).
`EBI_*` columns are populated only for the subset that has curated EBI AST
testing — a few thousand isolates, mostly post-2010.

**R/S threshold.** Per drug, the **Youden-J operating point** (max sens+spec)
selected on the model's validation fold and recorded in
`<checkpoint>/eval_results.json::operating_point.threshold`. This is the unbiased
threshold; AUROC/AUPRC are threshold-independent and live in the same JSON.
Six drugs have **extreme thresholds** at deployment (worth knowing when
interpreting `predicted_*`):

| Drug | Youden threshold | Interpretation |
|---|---|---|
| meropenem | 0.000 | model probabilities cluster near zero; tiny cut separates R/S |
| amikacin | 0.058 | likewise |
| colistin | 0.066 | likewise — also the chromosomal-mechanism floor (AUROC 0.81) |
| cefuroxime | 1.000 | model overconfident; only top tail called R |
| cefazolin | 1.000 | likewise |
| imipenem | 1.000 | likewise |

For these, `predicted_<drug>_AST_prob` is the more nuanced signal than the R/S
call. Reasoning: in the panel evaluation the Youden-tuned call still beats the
0.5 default for balanced accuracy on the held-out evaluate set; we keep the
same calibration in deployment for consistency.

**See also:** per-drug rolling resistance-rate-over-time plots
(predicted thick + EBI dashed) live at
`<project_k>/david/processed/train_kleb_ast/predicting_AST_over_time/<drug>.png`,
produced by BacPredict's
[`src/kleb_ast/plot_resistance_over_time.py`](../../../BacPredict/src/kleb_ast/plot_resistance_over_time.py)
(login-node CPU). Default rolling window is 100 samples by `collection_date_parsed`.

---

## 13. Changing metadata — full rebuild pipeline

**Don't run the rebuild ad-hoc.** Contact David first. Changes should land in the production
pipeline so the table is reproducible.

The chain:

1. **Collate ENA metadata** — [`metadata_collation.py`](pp/metadata_collation.py). Reads ENA TSV
   exports + per-project `ready_to_merge` patches → writes
   `intermediate_collated_metadata_wo_qc_or_kleborate.tsv`.
2. **Run QC + KPSC pipeline** — [`qc_add_metadata.py`](pp/qc_add_metadata.py). Joins the QC Excel
   sheets (`bakrep`, `Refseq`, `NCTC`, `kleborate`, `LINcode`, `FINAL_LIST`).
3. **Curate** — [`metadata_curation.py`](pp/metadata_curation.py). Parse + categorise `host` /
   `isolation_source` / `country` / `collection_date`; emit
   `metadata_final_curated_all_samples_and_columns.tsv` (= "v1").
4. **Add file paths** — [`add_paths_gff_fna_to_metadata.py`](pp/add_paths_gff_fna_to_metadata.py).
   Walks HPC paths to fill `gff_file` / `assembly_file` for SR and `lra_gff_file` /
   `lra_assembly_file` for LR.
5. **Rebuild v2** — [`rebuild_v2.sh`](pp/rebuild_v2.sh) (8-step cascade, all idempotent; each
   merge step renames the existing TSV to `.bak.<UTC>.tsv` before writing):
   1. `build_metadata_v2.py` — **always rebuilds from v1** (no auto-skip if a v2 file already
      exists; the existing v2 is renamed to `.bak.<UTC>.tsv` before write). Ingests orphan LRAs,
      drops `is_refseq`, adds LR/SR pairing columns.
   2. `merge_norway_pairs_into_v2.py`
   3. `merge_kleborate_into_metadata_v2.py` ← Kleborate output
   4. `merge_isescan_into_metadata_v2.py` ← ISEScan output
   5. `import_sr_kleborate.py`
   6. `import_sr_isescan.py`
   7. `build_sr_shadow_for_lra.py` ← writes `sr_shadow_for_lra.tsv`
   8. `add_paths_gff_fna_to_metadata.py --mode lra`
   9. `merge_predicted_and_ebi_ast_into_metadata_v2.py` ← BacPredict-side Bacformer AST
      predictions (Youden-tuned R/S calls + probabilities) and EBI ground-truth AST,
      joined onto v2 by `Sample`. See §12 for column families. Prereq: the BacPredict GPU
      array `predict_amr_panel_on_slurm.sh` has produced per-drug parquets under
      `<project_k>/david/processed/train_kleb_ast/predictions_for_metadata/<drug>.parquet`.
      Idempotent (drops `predicted_*` / `EBI_*` columns before each merge); safe to re-run
      against a stale or partial parquet directory.

   Use `--skip-g1` / `--skip-isescan` / `--skip-sr-import` / `--skip-predicted-ast` to skip
   subsections when only downstream changes are needed.

---

## 14. Downloading assemblies / GFFs / reads

See [`src/bac_data/`](../bac_data/) — scripts that automate downloads from v2 metadata:

- `download_bakrep_gbff_files.py` — Bakta `.gbff` fetcher.
- `download_lra_gffs.py` — LR GFF backfill.
- `download_related_lr_complete_genomes.py` — LR FASTA fetcher for the related-LR cohort.
- `gca_to_gcf_lookup.py` — accession resolver.
- Slurm scripts: `slurm_scripts/collect_bakrep_samples.py`,
  `slurm_scripts/collect_ncbi_datasets_samples.py`, `slurm_scripts/download_bakrep.sh`,
  `slurm_scripts/download_ncbi_datasets.sh`.

---

## 15. Reference scripts (one-look index)

| Script | Purpose |
|---|---|
| [`metadata_collation.py`](pp/metadata_collation.py) | ENA TSV + ready_to_merge → intermediate |
| [`qc_add_metadata.py`](pp/qc_add_metadata.py) | + QC Excel sheets (bakrep, Refseq, NCTC, kleborate, LINcode, FINAL_LIST) |
| [`metadata_curation.py`](pp/metadata_curation.py) | parse + categorise (host, isolation source, country, date) |
| [`add_paths_gff_fna_to_metadata.py`](pp/add_paths_gff_fna_to_metadata.py) | fill assembly/gff path columns |
| [`build_metadata_v2.py`](pp/build_metadata_v2.py) | v1 → v2 scaffold + pairing |
| [`merge_kleborate_into_metadata_v2.py`](pp/merge_kleborate_into_metadata_v2.py) | Kleborate overlay |
| [`merge_isescan_into_metadata_v2.py`](pp/merge_isescan_into_metadata_v2.py) | ISEScan overlay |
| [`build_paired_features.py`](pp/build_paired_features.py) | paired_index + lra_features + sr_features |
| [`rebuild_v2.sh`](pp/rebuild_v2.sh) | 8-step cascade orchestrator |
| [`run_kleborate_lra.py`](../bac_kleborate/run_kleborate_lra.py) | LRA Kleborate Slurm runner |
| [`run_isescan_lra.py`](../bac_isescan/run_isescan_lra.py) | LRA ISEScan Slurm runner |
| [`parsing.py`](../bac_kleborate/parsing.py) | Kleborate virulence/AMR call-string parsers |

History of the v2 build is archived in
[`bac_data/completed_pipelines/`](../bac_data/completed_pipelines/).

---

## 16. Contact

For metadata changes: **contact David**. Pipeline edits should land in the canonical scripts
above; ad-hoc TSV edits will be overwritten on the next cascade run.

---

## 17. Where this file lives + cross-refs (for maintenance)

**Canonical source of truth** (the file you're reading):

- Local repo: `~/developer/BacHGT/src/bac_metadata/METADATA_v2_README.md`
- HPC checkout (mirrored via git push/pull): `~/workspace/BacHGT/src/bac_metadata/METADATA_v2_README.md`

**Mirror sitting next to the data** (so colleagues landing on HPC find it):

- HPC sibling of the TSV: `<project_k>/david/final/METADATA_v2_README.md`
  *(= `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/METADATA_v2_README.md`)*
- HPC stub (short pointer file): `<project_k>/david/final/README.md` — directs readers here.

**Cross-references** (places that link to this README — update these if the README is renamed
or moved):

| File | Section / context |
|---|---|
| [`~/.claude/CLAUDE.md`](~/.claude/CLAUDE.md) | global BacHGT ecosystem block — link to canonical |
| [`~/developer/BacHGT/CLAUDE.md`](~/developer/BacHGT/CLAUDE.md) | monorepo CLAUDE.md — "Metadata" section |
| [`~/developer/BacHGT/src/bac_metadata/CLAUDE.md`](~/developer/BacHGT/src/bac_metadata/CLAUDE.md) | subpackage CLAUDE.md — "Read first" callout |
| [`~/developer/BacPredict/CLAUDE.md`](~/developer/BacPredict/CLAUDE.md) | sibling repo — §0.3 "Metadata source" |
| `<project_k>/david/final/README.md` (HPC stub) | HPC-side discoverability — points at this canonical doc |

**Maintenance flow.** If the README is **edited in place**: re-rsync to the HPC sibling
(`<project_k>/david/final/METADATA_v2_README.md`) so colleagues see the latest. If the README is
**renamed or moved**: update each of the cross-refs above. If a new cross-ref is added (e.g. a
new sibling repo's CLAUDE.md), append it to this table so future moves stay synchronised.
